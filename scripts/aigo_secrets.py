"""aigo_secrets.py — Custom App 金鑰（`ctx.secrets`）的寫入工具，值不經過對話

用之前先過 `custom-app-dev-guide.md` §25.2 的確認流程：向用戶說明 key_name 與用途、用戶同意後才寫。
預設先 create-key，再請用戶到 Builder 貼值。備案從環境變數（Windows 可用）或 600 權限檔案讀取，
本腳本只把值放在 HTTPS 請求本體送出，
**不印出、不寫 log、不放指令列**。刻意**沒有**讀值的指令——平台雖有 `GET /actions/secrets/{id}/value`，
本 skill 一律不讀金鑰值。

端點（v1.15.4 核對，權限皆 `builder.access` 且看得到這支 app）：
  GET    /api/v1/actions/apps/{app_id}/secrets     列表（回應只有 key_name 等中繼資料，不含值）
  POST   /api/v1/actions/apps/{app_id}/secrets     建立 {key_name, value, description}；同名 409
  PUT    /api/v1/actions/secrets/{secret_id}       更新 {value?, description?}
  DELETE /api/v1/actions/secrets/{secret_id}

用法（工作區內；<app> 是登錄表的 alias／UUID）：
    uv run --project scripts python scripts/aigo_secrets.py list <app>
    uv run --project scripts python scripts/aigo_secrets.py status <app>
    uv run --project scripts python scripts/aigo_secrets.py create-key <app> <KEY> --description 說明
    uv run --project scripts python scripts/aigo_secrets.py set <app> <KEY> --from-env <VAR>
    uv run --project scripts python scripts/aigo_secrets.py set <app> <KEY> --from-file <path> [--description 說明]
    uv run --project scripts python scripts/aigo_secrets.py delete <app> <KEY> --confirm
"""
from __future__ import annotations

import argparse
import os
import re
import stat
import sys
from pathlib import Path
from urllib.parse import urlsplit

PENDING_SECRET = "PENDING_PASTE_VALUE"


class SecretFileError(ValueError):
    pass


def read_secret_file(path: str | os.PathLike) -> str:
    """讀金鑰值檔：必須是一般檔、權限恰為 600（其他人與群組都不可讀寫）。去掉尾端換行。

    錯誤訊息不含檔案內容。
    """
    p = Path(path)
    if os.name == "nt":
        raise SecretFileError("Windows 不支援此 600 權限檔案路徑；請改用 --from-env，或在 Builder「服務」貼值")
    # O_NOFOLLOW：不跟隨 symlink；權限檢查與讀取用同一個 fd，避免檢查後被換檔（TOCTOU）
    try:
        fd = os.open(p, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        raise SecretFileError(f"找不到金鑰檔：{p}")
    except OSError:
        raise SecretFileError(f"金鑰檔打不開（不可以是 symlink）：{p}")
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise SecretFileError(f"金鑰檔必須是一般檔案：{p}")
        mode = stat.S_IMODE(st.st_mode)
        if mode != 0o600:
            raise SecretFileError(f"金鑰檔權限是 {mode:o}，必須是 600（chmod 600 {p}）")
        with os.fdopen(fd, "rb") as f:
            fd = -1
            raw = f.read()
    finally:
        if fd != -1:
            os.close(fd)
    try:
        value = raw.decode("utf-8").rstrip("\r\n")
    except UnicodeDecodeError:
        raise SecretFileError(f"金鑰檔不是 UTF-8 文字：{p}") from None
    if not value:
        raise SecretFileError(f"金鑰檔是空的：{p}")
    # 整個檔會當成「一顆金鑰的值」送出去——.env 形狀（多行 KEY=value）代表放錯東西了。
    # 多行本身不擋：PEM、service account JSON 是合法的多行值
    if sum(1 for line in value.splitlines() if _ENV_LINE.match(line)) >= 2:
        raise SecretFileError(f"金鑰檔看起來是 .env（多行 KEY=value）；一個檔只放一顆金鑰的值本身：{p}")
    return value


# `=` 後面要接非 `=` 的字元才算：base64 行尾的 `=`／`==` padding（PEM 內文）不算
_ENV_LINE = re.compile(r"^(export\s+)?[A-Za-z_][A-Za-z0-9_]*=[^=\s]")


def _read_env(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise SecretFileError("--from-env 必須是環境變數名稱，不是金鑰值")
    value = os.environ.get(name)
    if value is None:
        raise SecretFileError("指定的環境變數不存在；請用戶在本機設定後再執行")
    return value


def _request(method: str, url: str, token: str, **kwargs):
    """不轉印回應 body 或底層例外，兩者都可能含金鑰。"""
    import httpx
    try:
        return getattr(httpx, method)(url, headers=_headers(token), timeout=30, **kwargs)
    except httpx.HTTPError:
        raise RuntimeError("金鑰 API 連線失敗；請確認連線後再查名稱，未顯示底層內容") from None


def _require_https(base_url: str) -> str:
    base = base_url.rstrip("/")
    if urlsplit(base).scheme != "https":
        raise ValueError("金鑰只透過 https 送出；base_url 不是 https")
    return base


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def list_secrets(base_url: str, token: str, app_id: str) -> list[dict]:
    """回 key_name 等中繼資料；即使平台多回了欄位也只留名稱類欄位。"""
    resp = _request("get", f"{_require_https(base_url)}/api/v1/actions/apps/{app_id}/secrets", token)
    if not resp.is_success:
        raise RuntimeError(f"列出金鑰失敗：HTTP {resp.status_code}")
    keep = ("id", "key_name", "description", "updated_at")
    return [{k: s.get(k) for k in keep} for s in resp.json() if isinstance(s, dict)]


def _find(base_url: str, token: str, app_id: str, key_name: str) -> dict | None:
    return next((s for s in list_secrets(base_url, token, app_id) if s.get("key_name") == key_name), None)


def set_secret(base_url: str, token: str, app_id: str, key_name: str, value_file: str | None = None,
               description: str | None = None, *, env_name: str | None = None) -> str:
    """建立或更新（同名即更新）。回 "created"／"updated"。值只進 request body。"""
    base = _require_https(base_url)
    if (value_file is None) == (env_name is None):
        raise SecretFileError("請擇一指定 --from-file 或 --from-env")
    value = _read_env(env_name) if env_name is not None else read_secret_file(value_file)
    if not value.strip() or value.strip() == PENDING_SECRET:
        raise SecretFileError("金鑰值不可為空或保留佔位值；尚未貼值請用 create-key")
    if value_file is not None and value.startswith(f"{key_name}="):
        raise SecretFileError(f"金鑰檔內容以「{key_name}=」開頭；檔裡只放值本身，不要帶 KEY=：{value_file}")
    existing = _find(base, token, app_id, key_name)
    if existing is None:
        body = {"key_name": key_name, "value": value, "description": description or ""}
        resp = _request("post", f"{base}/api/v1/actions/apps/{app_id}/secrets", token, json=body)
        action = "created"
    else:
        body = {"value": value}
        if description is not None:
            body["description"] = description
        resp = _request("put", f"{base}/api/v1/actions/secrets/{existing['id']}", token, json=body)
        action = "updated"
    if not resp.is_success:
        # 不 raise_for_status：HTTPStatusError 的 repr 帶 request，避免任何把 body 帶出去的可能
        raise RuntimeError(f"寫入金鑰 {key_name} 失敗：HTTP {resp.status_code}")
    return action


def create_key(base_url: str, token: str, app_id: str, key_name: str, description: str) -> str:
    """只建不存在的 key；既有值及說明不動，409 競態也絕不轉成更新。"""
    base = _require_https(base_url)
    if not description.strip():
        raise ValueError("請用 --description 說明用途與使用的 action")
    if _find(base, token, app_id, key_name) is not None:
        return "exists"
    resp = _request("post", f"{base}/api/v1/actions/apps/{app_id}/secrets", token,
                    json={"key_name": key_name, "value": PENDING_SECRET, "description": description})
    if resp.status_code == 409 and _find(base, token, app_id, key_name) is not None:
        return "exists"
    if not resp.is_success:
        raise RuntimeError(f"建立金鑰名稱 {key_name} 失敗：HTTP {resp.status_code}")
    return "created"


def delete_secret(base_url: str, token: str, app_id: str, key_name: str, *, confirm: bool) -> bool:
    """刪除；沒帶 confirm=True 直接拒絕。找不到回 False。"""
    if not confirm:
        raise PermissionError("刪除金鑰要帶 --confirm（先逐項跟用戶確認）")
    base = _require_https(base_url)
    existing = _find(base, token, app_id, key_name)
    if existing is None:
        return False
    resp = _request("delete", f"{base}/api/v1/actions/secrets/{existing['id']}", token)
    if not resp.is_success:
        raise RuntimeError(f"刪除金鑰 {key_name} 失敗：HTTP {resp.status_code}")
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="aigo_secrets.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list", help="列出金鑰名稱（不含值）")
    p.add_argument("app")
    p = sub.add_parser("status", help="只查名稱；不把存在誤報為已設定")
    p.add_argument("app")
    p = sub.add_parser("create-key", help="先建待貼值的 key；同名已存在就不動（action 須先防護佔位值）")
    p.add_argument("app")
    p.add_argument("key")
    p.add_argument("--description", required=True)
    p = sub.add_parser("set", help="從環境變數或 POSIX 600 權限檔案讀值，建立或更新金鑰")
    p.add_argument("app")
    p.add_argument("key")
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--from-file")
    source.add_argument("--from-env", metavar="VAR")
    p.add_argument("--description")
    p = sub.add_parser("delete", help="刪除金鑰（必須帶 --confirm）")
    p.add_argument("app")
    p.add_argument("key")
    p.add_argument("--confirm", action="store_true")
    args = ap.parse_args(argv)

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from aigo_auth import find_workspace, get_token, resolve_app, resolve_base_url
    root = str(find_workspace() or ".")
    app = resolve_app(root, args.app)
    print(app.describe())
    base_url = app.base_url or resolve_base_url(root)
    token = get_token(root)

    if args.cmd in ("list", "status"):
        for s in list_secrets(base_url, token, app.id):
            if args.cmd == "status":
                print(f"{s['key_name']}\t已存在，設定狀態未確認（不讀值）")
            else:
                print(f"{s['key_name']}\t{s.get('description') or ''}")
        if args.cmd == "status":
            print("名稱存在不代表已貼值或憑證有效；請使用者確認並驗證功能。")
        return 0
    if args.cmd == "create-key":
        result = create_key(base_url, token, app.id, args.key, args.description)
        if result == "created":
            print(f"金鑰 {args.key}：已建立，待貼值（PENDING_PASTE_VALUE）；尚不可啟用排程或外呼")
        else:
            print(f"金鑰 {args.key}：已存在，未修改；設定狀態未確認")
        print(f"請到 {base_url.rstrip('/')}/builder/{app.id} →「服務」→ {args.key} 貼上 value；不要貼在對話裡。")
        return 0
    if args.cmd == "set":
        action = set_secret(base_url, token, app.id, args.key, args.from_file, args.description,
                            env_name=args.from_env)
        print(f"金鑰 {args.key}：{'已建立' if action == 'created' else '已更新'}（值未顯示）")
        return 0
    if delete_secret(base_url, token, app.id, args.key, confirm=args.confirm):
        print(f"金鑰 {args.key}：已刪除")
        return 0
    print(f"金鑰 {args.key}：不存在")
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, PermissionError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from None
