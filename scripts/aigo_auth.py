"""
aigo_auth.py — AI GO Custom App Builder 認證與配置管理模組

提供登入、設定檔管理、App 資訊查詢等功能。

## 三層模型（1.22.0 起）

| 層 | 落點 | 範圍 |
|---|---|---|
| 裝置 | skill 一份（user scope）；`~/.aigo/.env` 放預設帳密，`AIGO_TENANT` 可選 | 每台機器 |
| 身分 | `<工作區>/.aigo/.env` 覆寫 → `~/.aigo/.env` | 每人每租戶 |
| 工作區 | 含 `.aigo/config.json` 的目錄＝**一個租戶**，內含 0..n 個 app（`apps` 登錄表） | 每個目錄 |

同一套機制從「1 租戶 1 app」平順長到「N 租戶 N app」：多一個租戶就多一個工作區目錄，
多一個 app 就在登錄表多一筆。單 app 的使用者感覺不到登錄表存在（`resolve_app()` 自動選唯一那筆）。
"""

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
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
CONFIG_SCHEMA = 2

# 憑證檔與 Token 快取（皆位於 .aigo/，已被 .gitignore 忽略）
#
# 憑證檔預設放**機器級**的 `~/.aigo/.env`：它與 Skill 安裝目錄無關，
# 因此 `npx skills update`（會 rm -rf 整個 skill 目錄再複製）或重裝都不會洗掉。
# 工作區級的 `<工作區>/.aigo/.env` 仍然有效且優先，供「不同租戶用不同帳號」的情境。
CREDENTIALS_FILE = ".env"
TOKEN_CACHE_FILE = "token.json"

# Token 剩餘不到這個秒數就視為過期，提前換新（避免長流程中途 401）
TOKEN_REFRESH_MARGIN = 300

# 匯入當下的 shell 環境變數快照——**必須在任何 load_env_file() 之前取**。
# `load_env_file` 會把 `.env` 的鍵 setdefault 進 os.environ，之後就再也分不出
# 「使用者這次在 shell 明確指定的」與「從 .env 檔讀進來的機器預設」。
# 這個區別是 `resolve_base_url()` 優先序的基礎：臨時覆寫必須贏過專案設定，
# 但機器級 `.env` 的預設值不該贏過專案自己的 config.json。
_SHELL_ENV = {
    k: (os.environ.get(k) or "").strip()
    for k in ("AIGO_BASE_URL", "AIGO_TENANT", "AIGO_APP", "AIGO_APP_ID", "AIGO_SLUG")
}

# `.env` 讀進來的每一個鍵各自來自哪個檔案——`status` 用來說明「身分是從哪一層來的」
_ENV_SOURCES: dict[str, str] = {}

# 設定檔必填欄位（租戶層）。app 層改由 `apps` 登錄表逐筆驗證，見 `validate_config`
REQUIRED_FIELDS = ["base_url", "email"]

# App 登錄表
APP_KINDS = ("custom", "hosted")
ALIAS_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
LEGACY_ALIAS = "default"  # v1 設定檔升級時，唯一那筆 app 的 alias
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)

# 多安裝註冊表（由 check_update.py 維護），status 用來提醒「本機不只一份 skill」
UPDATE_STATE_FILE = Path.home() / CONFIG_DIR / "update_check.json"


# === 工作區與設定檔 ===


def _is_skill_install_dir(path: Path) -> bool:
    """該目錄是不是 skill 本體（SKILL.md ＋ scripts/check_update.py）。

    工作區設定不該落在 skill 安裝目錄裡——`npx skills update` 會整個資料夾重建。
    """
    return (path / "SKILL.md").exists() and (path / "scripts" / "check_update.py").exists()


def find_workspace(start: str | Path = ".") -> Path | None:
    """從 `start` 往上找最近的 `.aigo/config.json`，回傳工作區根目錄；找不到回 None。

    像 git 找 repo root 一樣：在 Hosted App 原始碼的子目錄、或工作區內任一深度執行，
    都能找到同一份登錄表。`AIGO_PROJECT_ROOT` 明確指定時不往上找（那就是根）。
    """
    explicit = os.environ.get("AIGO_PROJECT_ROOT", "").strip()
    if explicit and Path(start).resolve() == Path(explicit).resolve():
        return Path(explicit).resolve() if (Path(explicit) / CONFIG_DIR / CONFIG_FILE).exists() else None
    cur = Path(start).resolve()
    for candidate in (cur, *cur.parents):
        if (candidate / CONFIG_DIR / CONFIG_FILE).exists():
            return candidate
    return None


def init_config(project_path: str) -> dict:
    """
    建立 .aigo/config.json 骨架（schema 2：租戶層＋空的 app 登錄表）。

    若檔案已存在則直接讀取並回傳，不覆寫。

    Args:
        project_path: 工作區根目錄路徑

    Returns:
        config 字典（已正規化）
    """
    config_dir = Path(project_path) / CONFIG_DIR
    config_file = config_dir / CONFIG_FILE

    if config_file.exists():
        return load_config(project_path)

    # 建立骨架。
    # `base_url` 刻意留空：它是**租戶專屬**的（`https://{tenant}.ai-go.app`），
    # 沒有一個對全部租戶都成立的預設值。填 apex 當預設會讓使用者以為不用改。
    config: dict[str, Any] = {
        "schema": CONFIG_SCHEMA,
        "base_url": "",
        "email": "",
        "default_app": "",
        "apps": {},
    }

    config_dir.mkdir(parents=True, exist_ok=True)
    config_file.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"✅ 已建立設定檔：{config_file}")
    return normalize_config(config)


def _blank_app(kind: str = "custom") -> dict:
    return {
        "kind": kind,
        "id": "",
        "slug": "",
        "name": "",
        "access_mode": "",
        "app_domain": "",
        "integration_id": "",
        "path": "",
    }


def normalize_config(raw: dict) -> dict:
    """把任一版本的設定檔正規化成 schema 2（純記憶體，不寫檔）。

    - v1（頂層 `app_id`／`app_slug`／`app_name`／`access_mode`／`app_domain`）
      → 升級成 `apps[LEGACY_ALIAS]` 一筆，`default_app` 指向它
    - v2 → 補齊每筆 app 的欄位
    - 兩種格式都會把 default app 的欄位**鏡射回頂層** `app_id`／`app_slug`／…，
      讓只認得 v1 鍵的舊呼叫端繼續能用
    """
    cfg: dict[str, Any] = dict(raw or {})
    apps_raw = cfg.get("apps")
    apps: dict[str, dict] = {}
    if isinstance(apps_raw, dict):
        for alias, entry in apps_raw.items():
            if not isinstance(entry, dict):
                continue
            merged = _blank_app(entry.get("kind") or "custom")
            merged.update({k: (v if v is not None else "") for k, v in entry.items()})
            apps[str(alias)] = merged
    elif isinstance(apps_raw, list):  # 容忍陣列形狀：以 alias 或 id 前八碼當 key
        for entry in apps_raw:
            if not isinstance(entry, dict):
                continue
            alias = str(entry.get("alias") or (entry.get("id") or "")[:8] or f"app{len(apps) + 1}")
            merged = _blank_app(entry.get("kind") or "custom")
            merged.update({k: v for k, v in entry.items() if k != "alias" and v is not None})
            apps[alias] = merged

    # v1 頂層 app 欄位：沒有 apps 時升級成一筆；有 apps 時忽略（v2 為準）
    legacy_id = (cfg.get("app_id") or "").strip() if isinstance(cfg.get("app_id"), str) else ""
    if not apps and legacy_id:
        entry = _blank_app("custom")
        entry.update({
            "id": legacy_id,
            "slug": cfg.get("app_slug") or "",
            "name": cfg.get("app_name") or "",
            "access_mode": cfg.get("access_mode") or "",
            "app_domain": cfg.get("app_domain") or "",
        })
        apps[LEGACY_ALIAS] = entry

    default_app = (cfg.get("default_app") or "").strip() if isinstance(cfg.get("default_app"), str) else ""
    if default_app not in apps:
        default_app = next(iter(apps)) if len(apps) == 1 else ""

    cfg["schema"] = CONFIG_SCHEMA
    cfg["base_url"] = (cfg.get("base_url") or "").strip()
    cfg["email"] = (cfg.get("email") or "").strip()
    cfg["apps"] = apps
    cfg["default_app"] = default_app

    # 鏡射 default app 到 v1 鍵（向後相容；`save_config` 寫檔時會拿掉）
    mirror = apps.get(default_app) or _blank_app()
    cfg["app_id"] = mirror["id"]
    cfg["app_slug"] = mirror["slug"]
    cfg["app_name"] = mirror["name"]
    cfg["access_mode"] = mirror["access_mode"] or cfg.get("access_mode") or ""
    cfg["app_domain"] = mirror["app_domain"]
    return cfg


def load_config(project_path: str) -> dict:
    """
    讀取 .aigo/config.json 並正規化成 schema 2（見 `normalize_config`）。

    Args:
        project_path: 工作區根目錄路徑

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

    raw = config_file.read_text(encoding="utf-8-sig")
    try:
        return normalize_config(json.loads(raw))
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(
            f"❌ 設定檔 JSON 格式錯誤：{e.msg}",
            e.doc,
            e.pos,
        )


def save_config(project_path: str, config: dict) -> Path:
    """以 schema 2 形狀寫回 config.json（去掉鏡射的 v1 鍵；未知鍵原樣保留）。"""
    cfg = normalize_config(config)
    out: dict[str, Any] = {}
    for key, value in cfg.items():
        if key in ("app_id", "app_slug", "app_name", "access_mode", "app_domain"):
            continue
        out[key] = value
    # 固定欄位順序，diff 才好讀
    ordered = {k: out.pop(k) for k in ("schema", "base_url", "email", "default_app", "apps") if k in out}
    ordered.update(out)
    config_file = Path(project_path) / CONFIG_DIR / CONFIG_FILE
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(json.dumps(ordered, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return config_file


def migrate_config(project_path: str) -> Path:
    """把 v1 設定檔就地改寫成 schema 2（顯式操作；`load_config` 只在記憶體升級）。"""
    config_file = Path(project_path) / CONFIG_DIR / CONFIG_FILE
    cfg = load_config(project_path)
    backup = config_file.with_suffix(".json.v1.bak")
    if not backup.exists():
        backup.write_bytes(config_file.read_bytes())
    save_config(project_path, cfg)
    print(f"✅ 已改寫為 schema {CONFIG_SCHEMA}：{config_file}（原檔備份：{backup.name}）")
    return config_file


def validate_config(config: dict) -> list[str]:
    """
    檢查必填欄位，回傳缺少的欄位名稱清單。

    租戶層：`base_url`、`email`。app 層：登錄表每筆都要有 `id`（回報成 `apps.<alias>.id`）。
    **登錄表可以是空的**——純資料中心工作不需要 app。

    Args:
        config: 設定字典（任一版本；內部會先正規化）

    Returns:
        缺少的欄位名稱列表（空列表表示全部通過）
    """
    cfg = normalize_config(config)
    missing: list[str] = []
    for f_name in REQUIRED_FIELDS:
        value = cfg.get(f_name, "")
        if not value or (isinstance(value, str) and not value.strip()):
            missing.append(f_name)
    for alias, entry in cfg["apps"].items():
        if not (entry.get("id") or "").strip():
            missing.append(f"apps.{alias}.id")
        if entry.get("kind") not in APP_KINDS:
            missing.append(f"apps.{alias}.kind")
    return missing


# === App 登錄表 ===


@dataclass(frozen=True)
class AppRef:
    """`resolve_app()` 的回傳：本次操作的目標 app，連同它所屬的租戶與工作區。"""

    alias: str
    kind: str
    id: str
    slug: str = ""
    name: str = ""
    access_mode: str = ""
    app_domain: str = ""
    integration_id: str = ""
    path: str = ""
    base_url: str = ""
    workspace: str = ""
    source: str = ""  # 這筆是怎麼被選中的（供訊息用）
    extra: dict = field(default_factory=dict)

    @property
    def short_id(self) -> str:
        return self.id[:8]

    def describe(self) -> str:
        """一行目標描述——**每個會寫入的操作動手前都要印**。"""
        tenant = urlsplit(self.base_url).hostname or self.base_url or "?"
        label = self.name or self.slug or "(未命名)"
        return f"→ 目標：{self.alias}  {self.kind}  {label}  ({self.short_id})  @ {tenant}"


def list_apps(project_path: str = ".") -> dict[str, dict]:
    """登錄表（alias → 欄位）。沒有設定檔時回空字典。"""
    try:
        return load_config(project_path)["apps"]
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _match_app(apps: dict[str, dict], selector: str) -> tuple[str, dict] | None:
    """selector 可以是 alias、完整 UUID、或 UUID 前綴（≥ 6 碼且唯一）。"""
    sel = selector.strip()
    if sel in apps:
        return sel, apps[sel]
    low = sel.lower()
    hits = [(a, e) for a, e in apps.items() if (e.get("id") or "").lower() == low]
    if not hits and len(low) >= 6:
        hits = [(a, e) for a, e in apps.items() if (e.get("id") or "").lower().startswith(low)]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        raise RuntimeError(
            f"❌ `{selector}` 對應到多筆 app：{', '.join(a for a, _ in hits)}——請用 alias 指定"
        )
    return None


def _apps_hint(apps: dict[str, dict], default_app: str) -> str:
    if not apps:
        return "   登錄表是空的。加一筆：uv run --project scripts python scripts/aigo_auth.py app add <alias> --id <uuid>"
    rows = []
    for alias, e in apps.items():
        mark = " ★預設" if alias == default_app else ""
        rows.append(f"     {alias:<12} {e.get('kind', '?'):<7} {e.get('name') or e.get('slug') or ''}  ({(e.get('id') or '')[:8]}){mark}")
    return (
        "   可選的 app：\n" + "\n".join(rows) + "\n"
        "   指定方式（擇一）：--app <alias>／環境變數 AIGO_APP=<alias>／"
        "aigo_auth.py app default <alias>"
    )


def resolve_app(project_path: str = ".", selector: str | None = None) -> AppRef:
    """
    決定本次操作的目標 app——**所有需要 app_id 的流程都從這裡拿**，不要自己讀 config。

    順序固定，**不猜**：

    | # | 來源 | 定位 |
    |---|------|------|
    | 1 | 參數 `selector`（`--app`）→ shell 環境變數 `AIGO_APP` | 本次明確指定；alias、UUID 或 UUID 前綴 |
    | 2 | shell 環境變數 `AIGO_APP_ID`（相容舊版） | 登錄表有同 id 就用那筆；沒有就以 alias `env` 臨時成筆 |
    | 3 | `default_app` | 工作區設定的預設 |
    | 4 | 登錄表**只有一筆** | 單 app 工作區——使用者感覺不到登錄表存在 |
    | 5 | 其餘 | `RuntimeError`，訊息列出可選 alias |

    Raises:
        RuntimeError: 找不到工作區、登錄表為空、多筆未指定、或 selector 對不上
    """
    root = find_workspace(project_path)
    if root is None:
        raise RuntimeError(
            f"❌ 從 {Path(project_path).resolve()} 往上找不到工作區（.aigo/config.json）。\n"
            "   工作區＝一個租戶的目錄；建立：uv run --project scripts python scripts/aigo_auth.py setup-workspace <dir>"
        )
    cfg = load_config(str(root))
    apps = cfg["apps"]
    default_app = cfg["default_app"]
    base_url = ""
    try:
        base_url = resolve_base_url(str(root))
    except RuntimeError:
        pass  # 沒有租戶也能解析 app；呼叫端真的打 API 時會再報

    def _build(alias: str, entry: dict, source: str) -> AppRef:
        known = {"kind", "id", "slug", "name", "access_mode", "app_domain", "integration_id", "path"}
        return AppRef(
            alias=alias,
            kind=entry.get("kind") or "custom",
            id=entry.get("id") or "",
            slug=entry.get("slug") or "",
            name=entry.get("name") or "",
            access_mode=entry.get("access_mode") or "",
            app_domain=entry.get("app_domain") or "",
            integration_id=entry.get("integration_id") or "",
            path=entry.get("path") or "",
            base_url=base_url,
            workspace=str(root),
            source=source,
            extra={k: v for k, v in entry.items() if k not in known},
        )

    # 1. 明確指定
    explicit = (selector or "").strip() or _SHELL_ENV["AIGO_APP"]
    if explicit:
        hit = _match_app(apps, explicit)
        if hit is None:
            raise RuntimeError(
                f"❌ 登錄表裡沒有 `{explicit}` 這個 app（工作區 {root}）。\n" + _apps_hint(apps, default_app)
            )
        return _build(hit[0], hit[1], "--app / AIGO_APP")

    # 2. 舊版環境變數
    legacy_id = _SHELL_ENV["AIGO_APP_ID"]
    if legacy_id:
        hit = _match_app(apps, legacy_id)
        if hit is not None:
            return _build(hit[0], hit[1], "AIGO_APP_ID（相容）")
        entry = _blank_app("custom")
        entry.update({"id": legacy_id, "slug": _SHELL_ENV["AIGO_SLUG"]})
        return _build("env", entry, "AIGO_APP_ID（相容，未登錄）")

    # 3. 預設
    if default_app and default_app in apps:
        return _build(default_app, apps[default_app], "default_app")

    # 4. 唯一一筆
    if len(apps) == 1:
        alias, entry = next(iter(apps.items()))
        return _build(alias, entry, "登錄表唯一一筆")

    # 5. 不猜
    if not apps:
        raise RuntimeError(f"❌ 工作區 {root} 的 app 登錄表是空的。\n" + _apps_hint(apps, default_app))
    raise RuntimeError(
        f"❌ 工作區 {root} 有 {len(apps)} 個 app，本次沒有指定要操作哪一個。\n" + _apps_hint(apps, default_app)
    )


def assert_remote_matches(app: AppRef, remote: dict) -> None:
    """寫入前的最後一道閘：遠端回來的 app 與登錄表對得上才繼續。

    比對 id（必須相同）與 name（登錄表有記才比）。打錯 app 的代價是把 VFS
    同步到別人的 app，所以這裡寧可多停一次。
    """
    remote_id = str(remote.get("id") or "")
    if app.id and remote_id and remote_id.lower() != app.id.lower():
        raise RuntimeError(f"❌ 遠端 app id {remote_id[:8]} 與登錄表 `{app.alias}`（{app.short_id}）不符，中止")
    remote_name = remote.get("name") or ""
    if app.name and remote_name and remote_name != app.name:
        raise RuntimeError(
            f"❌ 遠端 app 名稱「{remote_name}」與登錄表 `{app.alias}` 記的「{app.name}」不符，中止。\n"
            f"   若是刻意改名，先 `aigo_auth.py app add {app.alias} --id {app.id}` 重新回填"
        )


def fetch_app_kind(base_url: str, token: str, app_id: str) -> tuple[str, dict]:
    """判定 app 是哪條產品線：先打 builder/apps，404 再打 hosted-apps。回 (kind, 回應)。"""
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=30) as client:
        resp = client.get(f"{base_url}/api/v1/builder/apps/{app_id}", headers=headers)
        if resp.status_code == 200:
            return "custom", resp.json()
        if resp.status_code not in (403, 404):
            resp.raise_for_status()
        resp2 = client.get(f"{base_url}/api/v1/hosted-apps/{app_id}", headers=headers)
        if resp2.status_code == 200:
            return "hosted", resp2.json()
        if resp2.status_code in (403, 404):
            raise RuntimeError(
                f"❌ 兩條產品線都找不到 app {app_id}（builder/apps {resp.status_code}、hosted-apps {resp2.status_code}）。\n"
                f"   確認 UUID 與租戶（{base_url}）是否正確"
            )
        resp2.raise_for_status()
    return "custom", {}


def add_app(
    project_path: str,
    alias: str,
    app_id: str,
    kind: str | None = None,
    make_default: bool | None = None,
    path: str = "",
    app_domain: str = "",
    fetch: bool = True,
) -> dict:
    """登錄一筆 app；`fetch=True` 時打平台回填 kind／slug／name／access_mode（Hosted 另回填整合 id）。

    alias 已存在＝更新那筆（重新回填）。登錄表原本為空、或 `make_default=True` 時設為預設。
    """
    alias = alias.strip()
    if not ALIAS_RE.match(alias):
        raise RuntimeError("❌ alias 只能是小寫英數、底線、連字號，1–32 字，且以英數開頭")
    app_id = app_id.strip()
    if not UUID_RE.match(app_id):
        raise RuntimeError(f"❌ `{app_id}` 不是 UUID——登錄表存的是 app 的 UUID，不是 slug")

    root = find_workspace(project_path) or Path(project_path).resolve()
    cfg = load_config(str(root)) if (root / CONFIG_DIR / CONFIG_FILE).exists() else normalize_config(init_config(str(root)))
    entry = dict(cfg["apps"].get(alias) or _blank_app(kind or "custom"))
    entry["id"] = app_id
    if kind:
        entry["kind"] = kind
    if path:
        entry["path"] = path
    if app_domain:
        entry["app_domain"] = app_domain

    if fetch:
        base_url = resolve_base_url(str(root))
        token = get_token(str(root))
        detected, info = fetch_app_kind(base_url, token, app_id)
        entry["kind"] = detected
        entry["slug"] = info.get("slug") or entry.get("slug") or ""
        entry["name"] = info.get("name") or entry.get("name") or ""
        if detected == "custom":
            entry["access_mode"] = info.get("access_mode") or entry.get("access_mode") or ""
        else:
            entry["integration_id"] = (
                info.get("attached_integration_id") or info.get("integration_id") or entry.get("integration_id") or ""
            )

    was_empty = not cfg["apps"]
    cfg["apps"][alias] = entry
    if make_default or (make_default is None and was_empty):
        cfg["default_app"] = alias
    save_config(str(root), cfg)
    return entry


def remove_app(project_path: str, alias: str) -> None:
    root = find_workspace(project_path) or Path(project_path).resolve()
    cfg = load_config(str(root))
    if alias not in cfg["apps"]:
        raise RuntimeError(f"❌ 登錄表裡沒有 `{alias}`")
    del cfg["apps"][alias]
    if cfg["default_app"] == alias:
        cfg["default_app"] = ""
    save_config(str(root), cfg)


def set_default_app(project_path: str, alias: str) -> None:
    root = find_workspace(project_path) or Path(project_path).resolve()
    cfg = load_config(str(root))
    if alias not in cfg["apps"]:
        raise RuntimeError(f"❌ 登錄表裡沒有 `{alias}`\n" + _apps_hint(cfg["apps"], cfg["default_app"]))
    cfg["default_app"] = alias
    save_config(str(root), cfg)


def deploy_token_env_key(alias: str) -> str:
    """Hosted App 的 Deploy Token 在工作區 `.aigo/.env` 的鍵名：`AIGO_DEPLOY_TOKEN__<ALIAS>`。"""
    return "AIGO_DEPLOY_TOKEN__" + re.sub(r"[^A-Z0-9]", "_", alias.upper())


def app_env(app: AppRef) -> dict[str, str]:
    """執行外部指令（例如 `aigo` CLI）時要疊上去的環境變數。

    Deploy Token 從工作區 `.aigo/.env` 的 `AIGO_DEPLOY_TOKEN__<ALIAS>` 取，匯出成
    `AIGO_DEPLOY_TOKEN`——CLI 的鑑權優先序是環境變數最高，這樣多租戶裝置上 CLI 的
    全域 profile 不會互相蓋。token 本身**不會**被印出來。
    """
    load_env_file(app.workspace or ".")
    env = {
        "AIGO_APP": app.alias,
        "AIGO_APP_ID": app.id,
        "AIGO_SLUG": app.slug,
        "AIGO_PROJECT_ROOT": app.workspace,
    }
    if app.base_url:
        env["AIGO_BASE_URL"] = app.base_url
    token = os.environ.get(deploy_token_env_key(app.alias), "").strip()
    if token:
        env["AIGO_DEPLOY_TOKEN"] = token
    return env


def run_with_app(app: AppRef, command: list[str]) -> int:
    """在 app 的環境下執行指令（`aigo_auth.py run <alias> -- <cmd...>`）。"""
    if not command:
        raise RuntimeError("❌ 沒有給要執行的指令（在 `--` 之後）")
    print(app.describe())
    env = dict(os.environ)
    env.update(app_env(app))
    cwd = str(Path(app.workspace) / app.path) if app.path else (app.workspace or None)
    return subprocess.call(command, env=env, cwd=cwd)


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
    "     - 該工作區 .aigo/config.json 填 \"base_url\": \"https://urfit.ai-go.app\"\n"
    "       ← 建議；一個工作區目錄＝一個租戶，多租戶就多開目錄\n"
    "     - ~/.aigo/.env 填 AIGO_TENANT=urfit（只服務單一租戶的機器可當預設）\n"
    "     - 臨時覆寫：AIGO_TENANT=demo 或 AIGO_BASE_URL=https://demo.ai-go.app"
)


def resolve_base_url(project_path: str = ".") -> str:
    """
    決定本次 API 呼叫要打哪個租戶空間。

    優先序（由高到低）——**特定性越高越優先**：

    | # | 來源 | 定位 |
    |---|------|------|
    | 1 | shell 環境變數 `AIGO_BASE_URL` → `AIGO_TENANT` | 臨時覆寫、CI |
    | 2 | `<工作區>/.aigo/config.json` 的 `base_url`（往上找最近的） | 這個工作區綁定的租戶 |
    | 3 | `.env` 的 `AIGO_BASE_URL` → `AIGO_TENANT` | 機器級預設（`~/.aigo/.env`） |

    `AIGO_TENANT` 只給前綴（`urfit`），由 `tenant_base_url()` 組成完整網址。

    ⚠️ **第 2 層必須贏過第 3 層**：機器級 `.env` 是「預設值」不是「唯一值」。若讓
    `~/.aigo/.env` 的 `AIGO_TENANT` 蓋過工作區的 `config.json`，同一台機器就再也無法
    開另一個租戶的工作區——而那個錯誤會以 401（與密碼錯同形）浮現，極難查。
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

    # 2. 工作區的 config.json（從 project_path 往上找最近的）
    if not candidate:
        root = find_workspace(project_path)
        if root is not None:
            try:
                candidate = (load_config(str(root)).get("base_url") or "").strip()
                source = f"{root / CONFIG_DIR / CONFIG_FILE} 的 base_url"
            except json.JSONDecodeError:
                candidate = ""

    # 3. `.env`（load_env_file 已把工作區級優先於機器級合併進 os.environ）
    if not candidate:
        if os.environ.get("AIGO_BASE_URL", "").strip():
            candidate = os.environ["AIGO_BASE_URL"].strip()
            source = f"{_ENV_SOURCES.get('AIGO_BASE_URL', '.env')} 的 AIGO_BASE_URL"
        elif os.environ.get("AIGO_TENANT", "").strip():
            candidate = _from_tenant(os.environ["AIGO_TENANT"].strip())
            source = f"{_ENV_SOURCES.get('AIGO_TENANT', '.env')} 的 AIGO_TENANT"

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

    - 給定 `project_path` → `<工作區>/.aigo/.env`（該工作區專用；會往上找最近的工作區）
    - 不給 → `~/.aigo/.env`（機器級，預設；符合「每台機器設定一次」的設計，
      且不會因為 Skill 更新／重裝而消失）

    Args:
        project_path: 工作區根目錄路徑；None 表示機器級

    Returns:
        憑證檔路徑
    """
    if project_path is None:
        return Path.home() / CONFIG_DIR / CREDENTIALS_FILE
    root = find_workspace(project_path) or Path(project_path)
    return root / CONFIG_DIR / CREDENTIALS_FILE


def _read_env_into(env_file: Path, values: dict[str, str]) -> None:
    """把單一 .env 的鍵值讀進 values 並注入 os.environ，兩者都不覆寫既有值。"""
    for line in env_file.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, raw = line.partition("=")
        key = key.strip()
        if not key:
            continue
        if key not in values:
            values[key] = raw.strip().strip("'\"")
            _ENV_SOURCES.setdefault(key, str(env_file))
        os.environ.setdefault(key, values[key])


def load_env_file(project_path: str = ".") -> dict:
    """
    讀取憑證檔並注入 os.environ（不覆寫已存在的環境變數）。

    依序讀 `<工作區>/.aigo/.env` → `~/.aigo/.env`，**先讀到的優先**，
    因此工作區級設定會蓋過機器級。格式為每行 `KEY=VALUE`，`#` 開頭為註解，
    值可用單/雙引號包住。兩個檔案都不存在時回空字典——環境變數本來就是
    合法的替代來源。

    Args:
        project_path: 工作區根目錄路徑（或其任一子目錄）

    Returns:
        從檔案讀到的鍵值字典（工作區級優先）
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
    `project_path` 才會寫進該工作區。

    範本刻意留空 AIGO_PASSWORD——密碼由使用者自己填入，
    任何工具或 agent 都不應該代為寫入。

    Args:
        project_path: 工作區根目錄路徑；None（預設）表示機器級

    Returns:
        憑證檔路徑
    """
    env_file = credentials_path(project_path)
    scope = "工作區級" if project_path is not None else "機器級"
    if env_file.exists():
        print(f"ℹ️  憑證檔已存在，未覆寫：{env_file}")
        return env_file

    if project_path is None:
        template = (
            "# AI GO Builder 憑證（機器級；不要放進任何 repo，也不要放進 Skill 安裝目錄）\n"
            "# 填好之後這台機器就不必再輸入密碼；Token 會自動快取與換新。\n"
            "AIGO_EMAIL=\n"
            "AIGO_PASSWORD=\n"
            "\n"
            "# 租戶前綴（可選）：只服務單一租戶的機器可填，例如 urfit → https://urfit.ai-go.app。\n"
            "# 會存取多個租戶的機器建議留空——每個租戶一個工作區目錄，租戶寫在該目錄的\n"
            "# .aigo/config.json（base_url），沒有 config 的目錄就會明確報錯，不會默默連到錯的租戶。\n"
            "AIGO_TENANT=\n"
        )
    else:
        template = (
            "# 這個工作區專用的覆寫（只寫要覆寫的鍵，其餘沿用 ~/.aigo/.env）\n"
            "# 例：此租戶用另一組帳號\n"
            "# AIGO_EMAIL=\n"
            "# AIGO_PASSWORD=\n"
            "\n"
            "# Hosted App 的 Deploy Token，一個 alias 一顆：AIGO_DEPLOY_TOKEN__<ALIAS 大寫>\n"
            "# `aigo_auth.py run <alias> -- aigo hosted deploy ...` 會把它匯出成 AIGO_DEPLOY_TOKEN\n"
            "# AIGO_DEPLOY_TOKEN__SITE=\n"
        )
    _secure_write(env_file, template)
    print(f"✅ 已建立憑證檔範本（{scope}）：{env_file}")
    if project_path is None:
        print("   請自行填入 AIGO_EMAIL 與 AIGO_PASSWORD 後重新執行。")
    return env_file


def _token_cache_path(project_path: str) -> Path:
    root = find_workspace(project_path) or Path(project_path)
    return root / CONFIG_DIR / TOKEN_CACHE_FILE


def _load_token_cache(project_path: str) -> dict:
    """讀取 `.aigo/token.json`，不存在或毀損時回空字典。"""
    cache_file = _token_cache_path(project_path)
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
    cache_file = _token_cache_path(project_path)
    payload = {
        "access_token": result["access_token"],
        "refresh_token": result.get("refresh_token", ""),
        "expires_at": time.time() + float(result.get("expires_in") or 0),
        "base_url": base_url,
    }
    _secure_write(cache_file, json.dumps(payload, indent=2))


def clear_token_cache(project_path: str = ".") -> None:
    """刪除 Token 快取（登出）。憑證檔不動。"""
    cache_file = _token_cache_path(project_path)
    cache_file.unlink(missing_ok=True)
    print("✅ 已清除 Token 快取")


def get_token(project_path: str = ".", force: bool = False) -> str:
    """
    取得可用的 access_token——Skill 內所有 API 呼叫的統一入口。

    依序嘗試：未過期的快取 → refresh_token 換發 → 帳密登入。
    憑證來源為 `.aigo/.env` 或環境變數（AIGO_EMAIL / AIGO_PASSWORD）；
    **租戶空間**來源見 `resolve_base_url()`（config.json 的 `base_url` 或 AIGO_BASE_URL／AIGO_TENANT）。

    Args:
        project_path: 工作區根目錄路徑（或其子目錄）
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
            f"   建立範本：uv run --project scripts python scripts/aigo_auth.py setup"
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
╔══════════════════════════════════════════════════════════════════╗
║               AI GO Custom App Builder 設定指引                  ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  三層：裝置（skill 一份＋~/.aigo/.env 帳密）→ 工作區（一個目錄   ║
║  ＝一個租戶，.aigo/config.json）→ app 登錄表（0..n 筆）          ║
║                                                                  ║
║  1. setup                 建立 ~/.aigo/.env，填入帳密（每機一次）║
║  2. setup-workspace <dir> 在租戶目錄建立 .aigo/config.json，     ║
║                           填 base_url（https://[tenant].ai-go.app）║
║  3. login                 驗證憑證並快取 Token                   ║
║  4. app add <alias> --id <uuid>   登錄 app（自動回填 kind／slug）║
║     app list ／ app default <alias> ／ app remove <alias>        ║
║  5. status                看目前生效的租戶、身分、app 表         ║
║  6. run <alias> -- <cmd>  在該 app 的環境下執行指令（Hosted CLI）║
║                                                                  ║
║  多一個租戶＝多一個工作區目錄；多一個 app＝登錄表多一筆。        ║
║  程式碼一律用 aigo_auth.resolve_app() 取目標 app，不自己讀 config║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
"""
    print(guide)


def _installed_skill_dirs() -> list[str]:
    """從 check_update 的註冊表讀本機已知的 skill 安裝路徑（只認得跑過檢查的）。"""
    try:
        state = json.loads(UPDATE_STATE_FILE.read_text(encoding="utf-8-sig"))
        installs = state.get("installs") or {}
        return [p for p in installs if Path(p).exists()]
    except (OSError, json.JSONDecodeError, AttributeError):
        return []


def _cmd_status(project_path: str = ".") -> int:
    """印出工作區、租戶、身分、app 登錄表與 Token 的現況，不外洩任何秘密值。"""
    warnings: list[str] = []
    root = find_workspace(project_path)
    load_env_file(str(root) if root else project_path)

    # 工作區
    print(f"目前目錄    : {Path(project_path).resolve()}")
    if root is None:
        print("工作區      : （找不到 .aigo/config.json——往上都沒有）")
    else:
        print(f"工作區      : {root}")
        if _is_skill_install_dir(root):
            warnings.append("工作區落在 skill 安裝目錄內——`npx skills update` 會整個資料夾重建，設定會消失；請把工作區移到 skill 之外")

    # 租戶
    try:
        base_url, source = resolve_base_url_with_source(str(root) if root else project_path)
        print(f"租戶空間    : {base_url}   ← {source}")
        if root is not None and source.startswith("環境變數"):
            try:
                cfg_url = validate_base_url(load_config(str(root)).get("base_url") or "")
                if cfg_url != base_url:
                    warnings.append(f"shell 環境變數把租戶覆寫成 {base_url}，但工作區 config 是 {cfg_url}——確認這是刻意的")
            except (ValueError, json.JSONDecodeError):
                pass
    except RuntimeError as e:
        print(f"租戶空間    : （未設定或不合法）\n{e}")

    # 身分
    home_env = credentials_path()
    print(f"憑證檔(機器): {home_env}{'' if home_env.exists() else ' （不存在）'}")
    if root is not None:
        ws_env = root / CONFIG_DIR / CREDENTIALS_FILE
        print(f"憑證檔(工作區): {ws_env}{' （優先）' if ws_env.exists() else ' （不存在）'}")
    email = os.environ.get("AIGO_EMAIL", "").strip()
    print(f"AIGO_EMAIL  : {email or '（未設定）'}{('   ← ' + _ENV_SOURCES['AIGO_EMAIL']) if email and 'AIGO_EMAIL' in _ENV_SOURCES else ''}")
    print(f"AIGO_PASSWORD: {'已設定' if os.environ.get('AIGO_PASSWORD') else '（未設定）'}")

    # app 登錄表
    if root is not None:
        try:
            cfg = load_config(str(root))
            apps, default_app = cfg["apps"], cfg["default_app"]
            print(f"App 登錄表  : {len(apps)} 筆" + ("（空——純資料工作不需要 app）" if not apps else ""))
            for alias, e in apps.items():
                mark = "★" if alias == default_app else " "
                token_key = deploy_token_env_key(alias)
                has_dt = "  deploy-token ✓" if e.get("kind") == "hosted" and os.environ.get(token_key) else ""
                print(f"  {mark} {alias:<12} {e.get('kind', '?'):<7} {e.get('name') or e.get('slug') or '(未命名)'}  ({(e.get('id') or '')[:8]}){has_dt}")
            if len(apps) > 1 and not default_app:
                print("    （沒有 default_app：每次操作都要 --app 或 AIGO_APP 指定）")
            missing = validate_config(cfg)
            if missing:
                warnings.append("設定檔缺欄位：" + ", ".join(missing))
        except json.JSONDecodeError as e:
            warnings.append(f"config.json 不是合法 JSON：{e.msg}")

    # Token
    cache = _load_token_cache(str(root) if root else project_path)
    if not cache.get("access_token"):
        print("Token 快取  : 無（下次呼叫會自動登入）")
    else:
        remaining = int(cache.get("expires_at", 0) - time.time())
        if remaining > 0:
            print(f"Token 快取  : 有效，剩餘約 {remaining // 60} 分鐘（{cache.get('base_url') or '?'}）")
        else:
            print("Token 快取  : 已過期（下次呼叫會自動換新）")

    # skill 安裝
    installs = _installed_skill_dirs()
    if len(installs) > 1:
        warnings.append("本機註冊了 " + str(len(installs)) + " 份 skill 安裝——建議只留 user scope 一份，其餘移除：\n" + "\n".join(f"      {p}" for p in installs))

    for w in warnings:
        print(f"⚠️  {w}")
    return 0


def _cmd_app(argv: list[str]) -> int:
    """`app list|add|remove|default`"""
    import argparse

    parser = argparse.ArgumentParser(prog="aigo_auth.py app", description="工作區的 app 登錄表")
    parser.add_argument("--root", default=".", help="工作區目錄（預設：從目前目錄往上找）")
    sub = parser.add_subparsers(dest="sub", required=True)
    sub.add_parser("list", help="列出登錄表")
    p_add = sub.add_parser("add", help="登錄或重新回填一筆 app")
    p_add.add_argument("alias")
    p_add.add_argument("--id", required=True, help="app 的 UUID")
    p_add.add_argument("--kind", choices=APP_KINDS, help="不打平台回填時才需要指定")
    p_add.add_argument("--path", default="", help="原始碼目錄（相對工作區；Hosted 用）")
    p_add.add_argument("--app-domain", default="", help="Custom App 的 app_domain 標記")
    p_add.add_argument("--default", action="store_true", help="設為預設 app")
    p_add.add_argument("--no-fetch", action="store_true", help="不打平台回填（離線；需 --kind）")
    p_rm = sub.add_parser("remove", help="移除一筆")
    p_rm.add_argument("alias")
    p_def = sub.add_parser("default", help="設定預設 app")
    p_def.add_argument("alias")
    args = parser.parse_args(argv)

    if args.sub == "list":
        apps = list_apps(args.root)
        root = find_workspace(args.root)
        cfg_default = load_config(str(root))["default_app"] if root else ""
        if not apps:
            print("（登錄表是空的）")
            return 0
        for alias, e in apps.items():
            mark = "★" if alias == cfg_default else " "
            print(f"{mark} {alias:<12} {e.get('kind', '?'):<7} {e.get('name') or ''}  slug={e.get('slug') or ''}  id={e.get('id') or ''}")
        return 0
    if args.sub == "add":
        if args.no_fetch and not args.kind:
            print("❌ --no-fetch 需要一併給 --kind custom|hosted")
            return 2
        entry = add_app(
            args.root, args.alias, args.id, kind=args.kind,
            make_default=True if args.default else None,
            path=args.path, app_domain=args.app_domain, fetch=not args.no_fetch,
        )
        print(f"✅ 已登錄 {args.alias}：{entry['kind']}  {entry.get('name') or ''}  slug={entry.get('slug') or ''}")
        return 0
    if args.sub == "remove":
        remove_app(args.root, args.alias)
        print(f"✅ 已移除 {args.alias}")
        return 0
    if args.sub == "default":
        set_default_app(args.root, args.alias)
        print(f"✅ 預設 app：{args.alias}")
        return 0
    return 2


# === 主程式入口 ===
if __name__ == "__main__":
    import sys

    # Windows 主控台預設 cp950，訊息含 emoji 會炸——與其他腳本一致改用 UTF-8
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    command = sys.argv[1] if len(sys.argv) > 1 else "guide"
    explicit_root = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("-") else None
    root = explicit_root if explicit_root is not None else "."

    try:
        if command == "setup":
            # 不給路徑 → 機器級 ~/.aigo/.env（預設且建議）；給了才寫進該工作區
            write_credentials_template(explicit_root)
        elif command == "setup-workspace":
            target = explicit_root or "."
            if _is_skill_install_dir(Path(target).resolve()):
                print("❌ 這是 skill 安裝目錄，工作區不能放這裡（更新時會整個重建）。換一個目錄。")
                sys.exit(1)
            init_config(target)
            write_credentials_template(target)
            print("   接著填 .aigo/config.json 的 base_url（https://[tenant].ai-go.app），再 `app add` 登錄 app")
        elif command == "status":
            sys.exit(_cmd_status(root))
        elif command == "logout":
            clear_token_cache(root)
        elif command == "login":
            # 驗證憑證可用：取 Token 但不印出 Token 本身
            try:
                get_token(root, force=True)
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
        elif command == "app":
            sys.exit(_cmd_app(sys.argv[2:]))
        elif command == "config" and len(sys.argv) > 2 and sys.argv[2] == "migrate":
            migrate_config(sys.argv[3] if len(sys.argv) > 3 else ".")
        elif command == "run":
            # run <alias> [--root DIR] -- <cmd...>
            rest = sys.argv[2:]
            if "--" not in rest:
                print("用法：aigo_auth.py run <alias> [--root DIR] -- <指令...>")
                sys.exit(2)
            head, cmd = rest[: rest.index("--")], rest[rest.index("--") + 1:]
            alias = head[0] if head and not head[0].startswith("-") else ""
            ws = head[head.index("--root") + 1] if "--root" in head else "."
            sys.exit(run_with_app(resolve_app(ws, alias or None), cmd))
        else:
            print_setup_guide()
    except RuntimeError as e:
        print(e)
        sys.exit(1)
