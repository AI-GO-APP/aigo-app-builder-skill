"""
aigo_auth.py — AI GO Custom App Builder 認證與配置管理模組

提供登入、設定檔管理、App 資訊查詢等功能。
"""

import json
import os
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

# === 常數 ===
# 平台主域。**所有**前台與 API 一律走租戶空間 `https://{tenant}.ai-go.app/*`，
# apex `https://ai-go.app` 不再是合法入口——見 `resolve_base_url()` 的說明。
AIGO_BASE_DOMAIN = "ai-go.app"
APEX_BASE_URL = f"https://{AIGO_BASE_DOMAIN}"

# 租戶前綴（= 工作區名）形狀：單層 DNS label，小寫英數 ＋ 連字號。
# 平台側解析端的下限是 3（`^[a-z0-9]{3,63}$`），寫入端下限是 4；這裡取**解析端**口徑，
# 因為既有租戶可能是 3 字元的舊值，用寫入端下限會把它們誤判成非法。
TENANT_PREFIX_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")

# 設定檔目錄與檔名
CONFIG_DIR = ".aigo"
CONFIG_FILE = "config.json"

# 憑證檔與 Token 快取（皆位於 .aigo/，已被 .gitignore 忽略）
#
# 憑證檔預設放**機器級**的 `~/.aigo/.env`：它與 Skill 安裝目錄無關，
# 因此 `npx skills update`（會 rm -rf 整個 skill 目錄再複製）或重裝都不會洗掉。
# 專案級的 `<專案>/.aigo/.env` 仍然有效且優先，供「不同專案用不同帳號」的情境。
CREDENTIALS_FILE = ".env"
TOKEN_CACHE_FILE = "token.json"

# Token 剩餘不到這個秒數就視為過期，提前換新（避免長流程中途 401）
TOKEN_REFRESH_MARGIN = 300

# 匯入當下的 shell 環境變數快照——**必須在任何 load_env_file() 之前取**。
# `load_env_file` 會把 `.env` 的鍵 setdefault 進 os.environ，之後就再也分不出
# 「使用者這次在 shell 明確指定的」與「從 .env 檔讀進來的機器預設」。
# 這個區別是 `resolve_base_url()` 優先序的基礎：臨時覆寫必須贏過專案設定，
# 但機器級 `.env` 的預設值不該贏過專案自己的 config.json。
_SHELL_ENV = {k: (os.environ.get(k) or "").strip() for k in ("AIGO_BASE_URL", "AIGO_TENANT")}

# 設定檔必填欄位
REQUIRED_FIELDS = ["base_url", "email", "app_id", "app_slug"]


def init_config(project_path: str) -> dict:
    """
    建立 .aigo/config.json 骨架。

    若檔案已存在則直接讀取並回傳，不覆寫。

    Args:
        project_path: 專案根目錄路徑

    Returns:
        config 字典
    """
    config_dir = Path(project_path) / CONFIG_DIR
    config_file = config_dir / CONFIG_FILE

    if config_file.exists():
        return load_config(project_path)

    # 建立骨架。
    # `base_url` 刻意留空：它是**租戶專屬**的（`https://{tenant}.ai-go.app`），
    # 沒有一個對全部租戶都成立的預設值。填 apex 當預設會讓使用者以為不用改。
    config: dict[str, Any] = {
        "base_url": "",
        "email": "",
        "app_id": "",
        "app_slug": "",
        "app_name": "",
        "access_mode": "internal",
    }

    config_dir.mkdir(parents=True, exist_ok=True)
    config_file.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✅ 已建立設定檔：{config_file}")
    return config


def load_config(project_path: str) -> dict:
    """
    讀取 .aigo/config.json。

    Args:
        project_path: 專案根目錄路徑

    Returns:
        config 字典

    Raises:
        FileNotFoundError: 設定檔不存在
        json.JSONDecodeError: JSON 格式錯誤
    """
    config_file = Path(project_path) / CONFIG_DIR / CONFIG_FILE

    if not config_file.exists():
        raise FileNotFoundError(
            f"❌ 找不到設定檔：{config_file}\n"
            f"   請先執行 init_config() 或手動建立設定檔。"
        )

    raw = config_file.read_text(encoding="utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(
            f"❌ 設定檔 JSON 格式錯誤：{e.msg}",
            e.doc,
            e.pos,
        )


def validate_config(config: dict) -> list[str]:
    """
    檢查必填欄位，回傳缺少的欄位名稱清單。

    Args:
        config: 設定字典

    Returns:
        缺少的欄位名稱列表（空列表表示全部通過）
    """
    missing: list[str] = []
    for field in REQUIRED_FIELDS:
        value = config.get(field, "")
        if not value or (isinstance(value, str) and not value.strip()):
            missing.append(field)
    return missing


# === 租戶空間網址（★ 平台規則，不可繞過）===


def tenant_base_url(tenant: str, base_domain: str = AIGO_BASE_DOMAIN) -> str:
    """由租戶前綴組出 base_url：`urfit` → `https://urfit.ai-go.app`。"""
    prefix = (tenant or "").strip().lower().strip(".")
    if not TENANT_PREFIX_RE.match(prefix):
        raise ValueError(
            f"❌ 租戶前綴「{tenant}」形狀不合法。\n"
            f"   規則：單層小寫英數 ＋ 連字號，不以連字號開頭或結尾（例如 urfit、demo）。"
        )
    return f"https://{prefix}.{base_domain.strip().lower().lstrip('.')}"


def validate_base_url(base_url: str) -> str:
    """
    檢查 base_url 是否為合法的**租戶空間**根 URL，回傳正規化後的值（去尾斜線）。

    平台自 workspace 子網域上線後，租戶是由 **Host header** 解出來的
    （backend `core/workspace_host.py`：`{tenant}.ai-go.app/api/*` 同源代理到後端且保留 Host），
    因此 base_url 打哪個 host 就等於宣告「我要登入哪個租戶」。apex `https://ai-go.app`
    推不出任何租戶：

    - 前台 `https://ai-go.app/login` 已被收斂成 workspace finder（找工作區的頁面），不是登入頁。
    - API `https://ai-go.app/api/v1/auth/login` 實測（2026-08-08，正確帳密）**已回
      `401 {"detail":"帳號或密碼錯誤"}`**——與密碼真的打錯**完全同形**（反帳號列舉），
      症狀會偽裝成憑證問題。同一組帳密打 `https://urfit.ai-go.app` 則 200。

    故本函式直接把 apex 擋在最前面：與其讓使用者去查一個無解的「密碼錯誤」，不如當場說清楚。

    Raises:
        ValueError: 空值、非 https、apex、或 `*.apps.ai-go.app`（那是 app 沙箱域，不是 API host）
    """
    value = (base_url or "").strip().rstrip("/")
    if not value:
        raise ValueError("❌ base_url 未設定")

    parts = urlsplit(value if "://" in value else f"https://{value}")
    host = (parts.hostname or "").lower()
    if not host:
        raise ValueError(f"❌ base_url「{base_url}」不是合法的 URL")
    if parts.scheme != "https" and host not in ("localhost", "127.0.0.1"):
        raise ValueError(f"❌ base_url 必須是 https：{base_url}")

    # 本機／UAT／自架環境不套租戶規則（沒有 ai-go.app 這層命名空間）。
    # ⚠️ 必須比對 **label 邊界**：`uat-ai-go.app` 的尾字串含 `ai-go.app`，
    # 用裸 endswith 會把 `urfit.uat-ai-go.app` 誤判成兩層前綴而擋掉。
    if host != AIGO_BASE_DOMAIN and not host.endswith(f".{AIGO_BASE_DOMAIN}"):
        return f"{parts.scheme}://{parts.netloc}"

    prefix = host[: -len(AIGO_BASE_DOMAIN)].rstrip(".")
    if not prefix or prefix == "www":
        raise ValueError(
            f"❌ `{value}` 是主站 apex，不是租戶空間，不能當 base_url。\n"
            f"   規則：https://[tenant].ai-go.app/*（例如 https://urfit.ai-go.app）\n"
            f"   租戶前綴 = 你平時登入時網址列上的第一段。"
        )
    if "." in prefix:
        raise ValueError(
            f"❌ `{value}` 不是租戶空間（租戶前綴只有一層）。\n"
            f"   `*.apps.ai-go.app` 是 Custom App 的沙箱域，不是 API host。\n"
            f"   規則：https://[tenant].ai-go.app/*"
        )
    return f"https://{host}"


_BASE_URL_SETUP_HINT = (
    "   AI GO 的登入與 API 一律走租戶子網域：https://[tenant].ai-go.app/*\n"
    "   （主站 apex https://ai-go.app 已不是登入入口）\n"
    "   租戶前綴 = 你平時登入時網址列上的第一段，例如 urfit / demo。\n"
    "   擇一設定：\n"
    "     - ~/.aigo/.env 填 AIGO_TENANT=urfit        ← 建議，整台機器設定一次\n"
    "     - 該專案 .aigo/config.json 填 \"base_url\": \"https://urfit.ai-go.app\"\n"
    "       （跨租戶工作時用這個，會蓋過機器級的 AIGO_TENANT）\n"
    "     - 臨時覆寫：AIGO_TENANT=demo 或 AIGO_BASE_URL=https://demo.ai-go.app"
)


def resolve_base_url(project_path: str = ".") -> str:
    """
    決定本次 API 呼叫要打哪個租戶空間。

    優先序（由高到低）——**特定性越高越優先**：

    | # | 來源 | 定位 |
    |---|------|------|
    | 1 | shell 環境變數 `AIGO_BASE_URL` → `AIGO_TENANT` | 臨時覆寫、CI |
    | 2 | `<專案>/.aigo/config.json` 的 `base_url` | 這個專案綁定的租戶 |
    | 3 | `.env` 的 `AIGO_BASE_URL` → `AIGO_TENANT` | 機器級預設（`~/.aigo/.env`） |

    `AIGO_TENANT` 只給前綴（`urfit`），由 `tenant_base_url()` 組成完整網址——
    一台機器多半只服務一個租戶，寫前綴比每次抄整串網址不容易錯。

    ⚠️ **第 2 層必須贏過第 3 層**：機器級 `.env` 是「預設值」不是「唯一值」。若讓
    `~/.aigo/.env` 的 `AIGO_TENANT` 蓋過專案的 `config.json`，同一台機器就再也無法
    開另一個租戶的專案——而那個錯誤會以 401（與密碼錯同形）浮現，極難查。
    shell 環境變數則相反：使用者當下明確打出來的東西，理應贏過任何檔案。
    兩者的區分靠 `_SHELL_ENV`（匯入時的快照），見該常數說明。

    **沒有預設值**——三層都沒有就拋 `RuntimeError` 並附設定指引。
    刻意不 fallback 到 apex：apex 實測已回與密碼錯**同形**的 401（見 `validate_base_url`），
    留一個會把使用者導向錯誤方向的預設值，比直接報錯糟得多。

    Raises:
        RuntimeError: 三層都沒有值，或值不合法（訊息內含規則與設定方式）
    """
    return resolve_base_url_with_source(project_path)[0]


def resolve_base_url_with_source(project_path: str = ".") -> tuple[str, str]:
    """同 `resolve_base_url()`，但一併回傳**值是從哪一層來的**。

    供 `status` 指令顯示：租戶打錯時症狀是同形 401，
    「現在生效的是哪個網址、它來自哪個檔案」是最快的定位資訊。
    """
    load_env_file(project_path)

    def _from_tenant(prefix: str) -> str:
        try:
            return tenant_base_url(prefix)
        except ValueError as e:
            raise RuntimeError(f"{e}") from e

    # 1. shell 環境變數（匯入時的快照——不含 .env 讀進來的值）
    if _SHELL_ENV["AIGO_BASE_URL"]:
        candidate, source = _SHELL_ENV["AIGO_BASE_URL"], "環境變數 AIGO_BASE_URL"
    elif _SHELL_ENV["AIGO_TENANT"]:
        candidate, source = _from_tenant(_SHELL_ENV["AIGO_TENANT"]), "環境變數 AIGO_TENANT"
    else:
        candidate = source = ""

    # 2. 專案的 config.json
    if not candidate:
        try:
            candidate = (load_config(project_path).get("base_url") or "").strip()
            source = f"{project_path}/.aigo/config.json 的 base_url"
        except (FileNotFoundError, json.JSONDecodeError):
            candidate = ""

    # 3. `.env`（load_env_file 已把專案級優先於機器級合併進 os.environ）
    if not candidate:
        if os.environ.get("AIGO_BASE_URL", "").strip():
            candidate = os.environ["AIGO_BASE_URL"].strip()
            source = ".env 的 AIGO_BASE_URL"
        elif os.environ.get("AIGO_TENANT", "").strip():
            candidate = _from_tenant(os.environ["AIGO_TENANT"].strip())
            source = ".env 的 AIGO_TENANT"

    if not candidate:
        raise RuntimeError("❌ 找不到租戶空間網址（base_url）。\n" + _BASE_URL_SETUP_HINT)

    try:
        return validate_base_url(candidate), source
    except ValueError as e:
        raise RuntimeError(f"{e}\n   （來源：{source}）") from e


def login(base_url: str, email: str, password: str) -> dict:
    """
    呼叫 POST /api/v1/auth/login 取得 JWT Token。

    ⚠️ **租戶由 base_url 的 host 決定**（平台以 Host header 解租戶）：
    打 `https://urfit.ai-go.app` 就只會在 urfit 這個租戶裡找帳號，
    同 email 在別的租戶的帳號一律視為不存在（回 401，與密碼錯同形）。

    Args:
        base_url: 租戶空間根 URL（例如 https://urfit.ai-go.app）
        email: 使用者 Email
        password: 使用者密碼

    Returns:
        包含 access_token, refresh_token, expires_in 的字典

    Raises:
        httpx.HTTPStatusError: 登入失敗（401 等）
    """
    url = f"{base_url}/api/v1/auth/login"
    payload = {"email": email, "password": password}

    with httpx.Client(timeout=30) as client:
        resp = client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()

    return {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token", ""),
        "expires_in": data.get("expires_in", 0),
        "token_type": data.get("token_type", "Bearer"),
    }


def refresh_token(base_url: str, refresh: str) -> dict | None:
    """
    嘗試以 refresh_token 換發新的 access_token。

    平台端點若不存在或已失效一律回 None，由呼叫端退回帳密登入——
    這條路徑是最佳化，不是必要條件。

    Args:
        base_url: API 根 URL
        refresh: 先前登入取得的 refresh_token

    Returns:
        同 login() 的字典；無法刷新時回 None
    """
    if not refresh:
        return None

    url = f"{base_url}/api/v1/auth/refresh"
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(url, json={"refresh_token": refresh})
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, json.JSONDecodeError, KeyError):
        return None

    if not data.get("access_token"):
        return None

    return {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token", refresh),
        "expires_in": data.get("expires_in", 0),
        "token_type": data.get("token_type", "Bearer"),
    }


# === 憑證與 Token 快取 ===


def _secure_write(path: Path, content: str) -> None:
    """寫入檔案並盡可能收斂權限為僅擁有者可讀寫（Windows 上為 best-effort）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def credentials_path(project_path: str | None = None) -> Path:
    """
    憑證檔位置。

    - 給定 `project_path` → `<專案>/.aigo/.env`（該專案專用）
    - 不給 → `~/.aigo/.env`（機器級，預設；符合「每台機器設定一次」的設計，
      且不會因為 Skill 更新／重裝而消失）

    Args:
        project_path: 專案根目錄路徑；None 表示機器級

    Returns:
        憑證檔路徑
    """
    base = Path(project_path) if project_path is not None else Path.home()
    return base / CONFIG_DIR / CREDENTIALS_FILE


def _read_env_into(env_file: Path, values: dict[str, str]) -> None:
    """把單一 .env 的鍵值讀進 values 並注入 os.environ，兩者都不覆寫既有值。"""
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, raw = line.partition("=")
        key = key.strip()
        if not key:
            continue
        values.setdefault(key, raw.strip().strip("'\""))
        os.environ.setdefault(key, values[key])


def load_env_file(project_path: str = ".") -> dict:
    """
    讀取憑證檔並注入 os.environ（不覆寫已存在的環境變數）。

    依序讀 `<專案>/.aigo/.env` → `~/.aigo/.env`，**先讀到的優先**，
    因此專案級設定會蓋過機器級。格式為每行 `KEY=VALUE`，`#` 開頭為註解，
    值可用單/雙引號包住。兩個檔案都不存在時回空字典——環境變數本來就是
    合法的替代來源。

    Args:
        project_path: 專案根目錄路徑

    Returns:
        從檔案讀到的鍵值字典（專案級優先）
    """
    values: dict[str, str] = {}
    seen: set[str] = set()

    for env_file in (credentials_path(project_path), credentials_path()):
        key = str(env_file.expanduser().absolute()).lower()
        if key in seen or not env_file.exists():
            continue
        seen.add(key)
        _read_env_into(env_file, values)

    return values


def write_credentials_template(project_path: str | None = None) -> Path:
    """
    建立 `.aigo/.env` 憑證檔範本（已存在則不覆寫）。

    預設寫**機器級**的 `~/.aigo/.env`——填一次全機器通用，且 Skill 更新／重裝
    （`npx skills update` 會刪除整個 skill 目錄）不會波及。只有明確給了
    `project_path` 才會寫進該專案。

    範本刻意留空 AIGO_PASSWORD——密碼由使用者自己填入，
    任何工具或 agent 都不應該代為寫入。

    Args:
        project_path: 專案根目錄路徑；None（預設）表示機器級

    Returns:
        憑證檔路徑
    """
    env_file = credentials_path(project_path)
    scope = "專案級" if project_path is not None else "機器級"
    if env_file.exists():
        print(f"ℹ️  憑證檔已存在，未覆寫：{env_file}")
        return env_file

    template = (
        "# AI GO Builder 憑證與租戶（機器級；不要放進任何 repo，也不要放進 Skill 安裝目錄）\n"
        "# 填好之後這台機器就不必再輸入密碼；Token 會自動快取與換新。\n"
        "AIGO_EMAIL=\n"
        "AIGO_PASSWORD=\n"
        "\n"
        "# 租戶前綴：登入時網址列的第一段。填 urfit 即組出 https://urfit.ai-go.app。\n"
        "# 規則 https://[tenant].ai-go.app/*——主站 apex https://ai-go.app 已不是登入入口。\n"
        "# 跨多個租戶工作時，改在各專案的 .aigo/config.json 填完整 base_url 即可覆寫此值。\n"
        "AIGO_TENANT=\n"
    )
    _secure_write(env_file, template)
    print(f"✅ 已建立憑證檔範本（{scope}）：{env_file}")
    print("   請自行填入 AIGO_EMAIL 與 AIGO_PASSWORD 後重新執行。")
    return env_file


def _load_token_cache(project_path: str) -> dict:
    """讀取 `.aigo/token.json`，不存在或毀損時回空字典。"""
    cache_file = Path(project_path) / CONFIG_DIR / TOKEN_CACHE_FILE
    if not cache_file.exists():
        return {}
    try:
        return json.loads(cache_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_token_cache(project_path: str, result: dict, base_url: str = "") -> None:
    """把登入結果連同絕對到期時間與**發證的租戶空間**寫入 `.aigo/token.json`。

    記 `base_url` 是因為 Token 綁租戶：切到另一個租戶空間後沿用舊快取，
    會拿 A 租戶的 Token 去打 B 租戶的 API，錯誤會以 403／查無資料的形式出現，
    比重登一次難查得多。見 `_load_token_cache` 的比對。
    """
    cache_file = Path(project_path) / CONFIG_DIR / TOKEN_CACHE_FILE
    payload = {
        "access_token": result["access_token"],
        "refresh_token": result.get("refresh_token", ""),
        "expires_at": time.time() + float(result.get("expires_in") or 0),
        "base_url": base_url,
    }
    _secure_write(cache_file, json.dumps(payload, indent=2))


def clear_token_cache(project_path: str = ".") -> None:
    """刪除 Token 快取（登出）。憑證檔不動。"""
    cache_file = Path(project_path) / CONFIG_DIR / TOKEN_CACHE_FILE
    cache_file.unlink(missing_ok=True)
    print("✅ 已清除 Token 快取")


def get_token(project_path: str = ".", force: bool = False) -> str:
    """
    取得可用的 access_token——Skill 內所有 API 呼叫的統一入口。

    依序嘗試：未過期的快取 → refresh_token 換發 → 帳密登入。
    憑證來源為 `.aigo/.env` 或環境變數（AIGO_EMAIL / AIGO_PASSWORD）；
    **租戶空間**來源見 `resolve_base_url()`（config.json 的 `base_url` 或 AIGO_BASE_URL／AIGO_TENANT）。

    Args:
        project_path: 專案根目錄路徑
        force: 略過快取，強制重新登入

    Returns:
        access_token 字串

    Raises:
        RuntimeError: 找不到憑證或租戶空間網址，訊息內含設定指引
        httpx.HTTPStatusError: 帳密錯誤等登入失敗
    """
    load_env_file(project_path)
    base_url = resolve_base_url(project_path)
    cache = {} if force else _load_token_cache(project_path)

    # 換了租戶空間就整份快取作廢——Token 綁租戶，跨租戶沿用只會拿到難查的 403
    if cache.get("base_url") and cache["base_url"] != base_url:
        cache = {}

    # 1. 快取仍在有效期內
    if cache.get("access_token") and cache.get("expires_at", 0) - TOKEN_REFRESH_MARGIN > time.time():
        return cache["access_token"]

    # 2. 用 refresh_token 換發（平台不支援時自動略過）
    if not force and cache.get("refresh_token"):
        refreshed = refresh_token(base_url, cache["refresh_token"])
        if refreshed:
            _save_token_cache(project_path, refreshed, base_url)
            return refreshed["access_token"]

    # 3. 帳密登入
    email = os.environ.get("AIGO_EMAIL", "").strip()
    password = os.environ.get("AIGO_PASSWORD", "")
    if not email or not password:
        raise RuntimeError(
            f"❌ 找不到 AI GO 憑證。\n"
            f"   請在 {credentials_path()} 填入：\n"
            f"     AIGO_EMAIL=your-email@example.com\n"
            f"     AIGO_PASSWORD=your-password\n"
            f"   （機器級憑證檔，填一次即可，之後不再詢問；不會被任何 repo 提交）\n"
            f"   或改用環境變數 AIGO_EMAIL / AIGO_PASSWORD。\n"
            f"   建立範本：uv run python scripts/aigo_auth.py setup"
        )

    result = login(base_url, email, password)
    _save_token_cache(project_path, result, base_url)
    return result["access_token"]


def get_app_info(base_url: str, token: str, app_id: str) -> dict:
    """
    呼叫 GET /api/v1/builder/apps/{app_id} 取得 App 資訊。

    Args:
        base_url: API 根 URL
        token: JWT access_token
        app_id: App ID 或 slug

    Returns:
        App 資訊字典（包含 id, name, slug, vfs_state, vfs_version, status, access_mode 等）

    Raises:
        httpx.HTTPStatusError: API 回應錯誤
    """
    url = f"{base_url}/api/v1/builder/apps/{app_id}"
    headers = {"Authorization": f"Bearer {token}"}

    with httpx.Client(timeout=30) as client:
        resp = client.get(url, headers=headers)
        resp.raise_for_status()

    return resp.json()


def print_setup_guide() -> None:
    """印出設定指引，幫助使用者完成初始化。"""
    guide = """
╔══════════════════════════════════════════════════════════════╗
║               AI GO Custom App Builder 設定指引              ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  1. 執行 init_config("./my-project") 建立設定檔骨架          ║
║                                                              ║
║  2. 編輯 .aigo/config.json，填入以下資訊：                    ║
║     - base_url:    https://[tenant].ai-go.app（★ 租戶空間）  ║
║                    tenant = 登入時網址列的第一段；主站       ║
║                    apex https://ai-go.app 已不是登入入口     ║
║     - email:       你的 AI GO 帳號 Email                     ║
║     - app_id:      目標 App 的 UUID                          ║
║     - app_slug:    目標 App 的 Slug                          ║
║     - app_name:    App 顯示名稱（選填）                       ║
║     - access_mode: internal / external（選填）                ║
║                                                              ║
║  3. 執行 `aigo_auth.py setup` 建立 ~/.aigo/.env，填入帳密    ║
║     （每台機器只需一次；不在任何 repo 或 Skill 目錄內）        ║
║                                                              ║
║  4. 之後一律用 get_token() 取 Token——會自動快取與換新        ║
║                                                              ║
║  5. 使用 get_app_info() 驗證連線是否正常                      ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""
    print(guide)


def _cmd_status(project_path: str = ".") -> int:
    """印出憑證與 Token 快取的現況，不外洩任何秘密值。"""
    load_env_file(project_path)
    home_env = credentials_path()
    project_env = credentials_path(project_path)
    email = os.environ.get("AIGO_EMAIL", "").strip()
    has_password = bool(os.environ.get("AIGO_PASSWORD"))
    cache = _load_token_cache(project_path)

    try:
        base_url, source = resolve_base_url_with_source(project_path)
        print(f"租戶空間    : {base_url}   ← {source}")
    except RuntimeError as e:
        print(f"租戶空間    : （未設定或不合法）\n{e}")

    print(f"憑證檔(機器): {home_env}{'' if home_env.exists() else ' （不存在）'}")
    if project_env.expanduser().absolute() != home_env.expanduser().absolute():
        exists = project_env.exists()
        print(f"憑證檔(專案): {project_env}{' （優先）' if exists else ' （不存在）'}")
    print(f"AIGO_EMAIL  : {email or '（未設定）'}")
    print(f"AIGO_PASSWORD: {'已設定' if has_password else '（未設定）'}")

    if not cache.get("access_token"):
        print("Token 快取  : 無（下次呼叫會自動登入）")
        return 0

    remaining = int(cache.get("expires_at", 0) - time.time())
    if remaining > 0:
        print(f"Token 快取  : 有效，剩餘約 {remaining // 60} 分鐘")
    else:
        print("Token 快取  : 已過期（下次呼叫會自動換新）")
    return 0


# === 主程式入口 ===
if __name__ == "__main__":
    import sys

    # Windows 主控台預設 cp950，訊息含 emoji 會炸——與其他腳本一致改用 UTF-8
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    command = sys.argv[1] if len(sys.argv) > 1 else "guide"
    explicit_root = sys.argv[2] if len(sys.argv) > 2 else None
    root = explicit_root if explicit_root is not None else "."

    if command == "setup":
        # 不給路徑 → 機器級 ~/.aigo/.env（預設且建議）；給了才寫進該專案
        write_credentials_template(explicit_root)
    elif command == "status":
        sys.exit(_cmd_status(root))
    elif command == "logout":
        clear_token_cache(root)
    elif command == "login":
        # 驗證憑證可用：取 Token 但不印出 Token 本身
        try:
            get_token(root, force=True)
        except RuntimeError as e:
            print(e)
            sys.exit(1)
        except httpx.HTTPStatusError as e:
            print(f"❌ 登入失敗（HTTP {e.response.status_code}）")
            if e.response.status_code == 401:
                # 平台的反帳號列舉設計：「帳號不在這個租戶」與「密碼錯」回**完全相同**的 401，
                # 所以這裡不能只叫人檢查密碼——先確認打的是不是正確的租戶空間。
                print("   401 有兩種可能，且平台刻意讓兩者無法分辨：")
                print("     1. 密碼錯")
                print("     2. base_url 指到**別的租戶**——同一組帳密在其他租戶等同不存在")
                try:
                    print(f"   目前使用的租戶空間：{resolve_base_url(root)}")
                except RuntimeError:
                    pass
                print("   規則：https://[tenant].ai-go.app/*")
            sys.exit(1)
        print("✅ 登入成功，Token 已快取")
    else:
        print_setup_guide()
