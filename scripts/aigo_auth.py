"""
aigo_auth.py — AI GO Custom App Builder 認證與配置管理模組

提供登入、設定檔管理、App 資訊查詢等功能。
"""

import json
import os
import time
from pathlib import Path
from typing import Any

import httpx

# === 常數 ===
AIGO_BASE_URL = "https://ai-go.app"
API_V1 = f"{AIGO_BASE_URL}/api/v1"

# 設定檔目錄與檔名
CONFIG_DIR = ".aigo"
CONFIG_FILE = "config.json"

# 憑證檔與 Token 快取（皆位於 .aigo/，已被 .gitignore 忽略）
CREDENTIALS_FILE = ".env"
TOKEN_CACHE_FILE = "token.json"

# Token 剩餘不到這個秒數就視為過期，提前換新（避免長流程中途 401）
TOKEN_REFRESH_MARGIN = 300

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

    # 建立骨架
    config: dict[str, Any] = {
        "base_url": AIGO_BASE_URL,
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


def login(base_url: str, email: str, password: str) -> dict:
    """
    呼叫 POST /api/v1/auth/login 取得 JWT Token。

    Args:
        base_url: API 根 URL（例如 https://ai-go.app）
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


def load_env_file(project_path: str = ".") -> dict:
    """
    讀取 `.aigo/.env` 並注入 os.environ（不覆寫已存在的環境變數）。

    格式為每行 `KEY=VALUE`，`#` 開頭為註解，值可用單/雙引號包住。
    檔案不存在時回空字典——環境變數本來就是合法的替代來源。

    Args:
        project_path: 專案根目錄路徑

    Returns:
        從檔案讀到的鍵值字典
    """
    env_file = Path(project_path) / CONFIG_DIR / CREDENTIALS_FILE
    if not env_file.exists():
        return {}

    values: dict[str, str] = {}
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, raw = line.partition("=")
        key = key.strip()
        value = raw.strip().strip("'\"")
        if not key:
            continue
        values[key] = value
        os.environ.setdefault(key, value)

    return values


def write_credentials_template(project_path: str = ".") -> Path:
    """
    建立 `.aigo/.env` 憑證檔範本（已存在則不覆寫）。

    範本刻意留空 AIGO_PASSWORD——密碼由使用者自己填入，
    任何工具或 agent 都不應該代為寫入。

    Args:
        project_path: 專案根目錄路徑

    Returns:
        憑證檔路徑
    """
    env_file = Path(project_path) / CONFIG_DIR / CREDENTIALS_FILE
    if env_file.exists():
        print(f"ℹ️  憑證檔已存在，未覆寫：{env_file}")
        return env_file

    template = (
        "# AI GO Builder 憑證（本檔在 .gitignore 內，不會被提交）\n"
        "# 填好之後這台機器就不必再輸入密碼；Token 會自動快取與換新。\n"
        "AIGO_EMAIL=\n"
        "AIGO_PASSWORD=\n"
    )
    _secure_write(env_file, template)
    print(f"✅ 已建立憑證檔範本：{env_file}")
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


def _save_token_cache(project_path: str, result: dict) -> None:
    """把登入結果連同絕對到期時間寫入 `.aigo/token.json`。"""
    cache_file = Path(project_path) / CONFIG_DIR / TOKEN_CACHE_FILE
    payload = {
        "access_token": result["access_token"],
        "refresh_token": result.get("refresh_token", ""),
        "expires_at": time.time() + float(result.get("expires_in") or 0),
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
    憑證來源為 `.aigo/.env` 或環境變數（AIGO_EMAIL / AIGO_PASSWORD）。

    Args:
        project_path: 專案根目錄路徑
        force: 略過快取，強制重新登入

    Returns:
        access_token 字串

    Raises:
        RuntimeError: 找不到憑證，訊息內含設定指引
        httpx.HTTPStatusError: 帳密錯誤等登入失敗
    """
    load_env_file(project_path)
    base_url = os.environ.get("AIGO_BASE_URL", AIGO_BASE_URL)
    cache = {} if force else _load_token_cache(project_path)

    # 1. 快取仍在有效期內
    if cache.get("access_token") and cache.get("expires_at", 0) - TOKEN_REFRESH_MARGIN > time.time():
        return cache["access_token"]

    # 2. 用 refresh_token 換發（平台不支援時自動略過）
    if not force and cache.get("refresh_token"):
        refreshed = refresh_token(base_url, cache["refresh_token"])
        if refreshed:
            _save_token_cache(project_path, refreshed)
            return refreshed["access_token"]

    # 3. 帳密登入
    email = os.environ.get("AIGO_EMAIL", "").strip()
    password = os.environ.get("AIGO_PASSWORD", "")
    if not email or not password:
        env_file = Path(project_path) / CONFIG_DIR / CREDENTIALS_FILE
        raise RuntimeError(
            f"❌ 找不到 AI GO 憑證。\n"
            f"   請在 {env_file} 填入：\n"
            f"     AIGO_EMAIL=your-email@example.com\n"
            f"     AIGO_PASSWORD=your-password\n"
            f"   （該檔在 .gitignore 內，不會被提交；填一次即可，之後不再詢問）\n"
            f"   或改用環境變數 AIGO_EMAIL / AIGO_PASSWORD。\n"
            f"   建立範本：uv run python scripts/aigo_auth.py setup"
        )

    result = login(base_url, email, password)
    _save_token_cache(project_path, result)
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
║     - email:       你的 AI GO 帳號 Email                     ║
║     - app_id:      目標 App 的 UUID                          ║
║     - app_slug:    目標 App 的 Slug                          ║
║     - app_name:    App 顯示名稱（選填）                       ║
║     - access_mode: internal / external（選填）                ║
║                                                              ║
║  3. 執行 `aigo_auth.py setup` 建立 .aigo/.env，填入帳密      ║
║     （只需一次；該檔已被 .gitignore 忽略）                     ║
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
    env_file = Path(project_path) / CONFIG_DIR / CREDENTIALS_FILE
    email = os.environ.get("AIGO_EMAIL", "").strip()
    has_password = bool(os.environ.get("AIGO_PASSWORD"))
    cache = _load_token_cache(project_path)

    print(f"憑證檔      : {env_file}{'' if env_file.exists() else ' （不存在）'}")
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
    root = sys.argv[2] if len(sys.argv) > 2 else "."

    if command == "setup":
        write_credentials_template(root)
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
            print(f"❌ 登入失敗（HTTP {e.response.status_code}）——請確認帳號密碼")
            sys.exit(1)
        print("✅ 登入成功，Token 已快取")
    else:
        print_setup_guide()
