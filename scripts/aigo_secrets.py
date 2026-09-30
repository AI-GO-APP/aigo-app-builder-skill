"""aigo_secrets.py — Custom App 金鑰（`ctx.secrets`）的寫入工具，值不經過對話

用之前先過 `custom-app-dev-guide.md` §25.2 的確認流程：向用戶說明 key_name 與用途、用戶同意後才寫。
金鑰的**值**由用戶自己填進本機檔（權限必須是 600），本腳本讀檔後只放在 HTTPS 請求本體送出，
**不印出、不寫 log、不放指令列**。刻意**沒有**讀值的指令——平台雖有 `GET /actions/secrets/{id}/value`，
本 skill 一律不讀金鑰值。

端點（v1.15.4 核對，權限皆 `builder.access` 且看得到這支 app）：
  GET    /api/v1/actions/apps/{app_id}/secrets     列表（回應只有 key_name 等中繼資料，不含值）
  POST   /api/v1/actions/apps/{app_id}/secrets     建立 {key_name, value, description}；同名 409
  PUT    /api/v1/actions/secrets/{secret_id}       更新 {value?, description?}
  DELETE /api/v1/actions/secrets/{secret_id}

用法（工作區內；<app> 是登錄表的 alias／UUID）：
    uv run --project scripts python scripts/aigo_secrets.py list <app>
    uv run --project scripts python scripts/aigo_secrets.py set <app> <KEY> --from-file <path> [--description 說明]
    uv run --project scripts python scripts/aigo_secrets.py delete <app> <KEY> --confirm
"""
from __future__ import annotations

import argparse
import os
import stat
import sys
from pathlib import Path
from urllib.parse import urlsplit


class SecretFileError(ValueError):
    pass


def read_secret_file(path: str | os.PathLike) -> str:
    """讀金鑰值檔：必須是一般檔、權限恰為 600（其他人與群組都不可讀寫）。去掉尾端換行。

    錯誤訊息不含檔案內容。
    """
    p = Path(path)
    try:
        st = p.stat()
    except FileNotFoundError:
        raise SecretFileError(f"找不到金鑰檔：{p}")
    if not stat.S_ISREG(st.st_mode):
        raise SecretFileError(f"金鑰檔必須是一般檔案：{p}")
    mode = stat.S_IMODE(st.st_mode)
    if mode != 0o600:
        raise SecretFileError(f"金鑰檔權限是 {mode:o}，必須是 600（chmod 600 {p}）")
    value = p.read_text(encoding="utf-8").rstrip("\r\n")
    if not value:
        raise SecretFileError(f"金鑰檔是空的：{p}")
    return value


def _require_https(base_url: str) -> str:
    base = base_url.rstrip("/")
    if urlsplit(base).scheme != "https":
        raise ValueError("金鑰只透過 https 送出；base_url 不是 https")
    return base


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def list_secrets(base_url: str, token: str, app_id: str) -> list[dict]:
    """回 key_name 等中繼資料；即使平台多回了欄位也只留名稱類欄位。"""
    import httpx
    resp = httpx.get(f"{_require_https(base_url)}/api/v1/actions/apps/{app_id}/secrets",
                     headers=_headers(token), timeout=30)
    resp.raise_for_status()
    keep = ("id", "key_name", "description", "updated_at")
    return [{k: s.get(k) for k in keep} for s in resp.json() if isinstance(s, dict)]


def _find(base_url: str, token: str, app_id: str, key_name: str) -> dict | None:
    return next((s for s in list_secrets(base_url, token, app_id) if s.get("key_name") == key_name), None)


def set_secret(base_url: str, token: str, app_id: str, key_name: str, value_file: str,
               description: str | None = None) -> str:
    """建立或更新（同名即更新）。回 "created"／"updated"。值只進 request body。"""
    import httpx
    base = _require_https(base_url)
    value = read_secret_file(value_file)
    existing = _find(base, token, app_id, key_name)
    if existing is None:
        body = {"key_name": key_name, "value": value, "description": description or ""}
        resp = httpx.post(f"{base}/api/v1/actions/apps/{app_id}/secrets", json=body,
                          headers=_headers(token), timeout=30)
        action = "created"
    else:
        body = {"value": value}
        if description is not None:
            body["description"] = description
        resp = httpx.put(f"{base}/api/v1/actions/secrets/{existing['id']}", json=body,
                         headers=_headers(token), timeout=30)
        action = "updated"
    if resp.status_code >= 400:
        # 不 raise_for_status：HTTPStatusError 的 repr 帶 request，避免任何把 body 帶出去的可能
        raise RuntimeError(f"寫入金鑰 {key_name} 失敗：HTTP {resp.status_code}")
    return action


def delete_secret(base_url: str, token: str, app_id: str, key_name: str, *, confirm: bool) -> bool:
    """刪除；沒帶 confirm=True 直接拒絕。找不到回 False。"""
    import httpx
    if not confirm:
        raise PermissionError("刪除金鑰要帶 --confirm（先逐項跟用戶確認）")
    base = _require_https(base_url)
    existing = _find(base, token, app_id, key_name)
    if existing is None:
        return False
    resp = httpx.delete(f"{base}/api/v1/actions/secrets/{existing['id']}", headers=_headers(token), timeout=30)
    if resp.status_code >= 400:
        raise RuntimeError(f"刪除金鑰 {key_name} 失敗：HTTP {resp.status_code}")
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="aigo_secrets.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list", help="列出金鑰名稱（不含值）")
    p.add_argument("app")
    p = sub.add_parser("set", help="從 600 權限的檔案讀值，建立或更新金鑰")
    p.add_argument("app")
    p.add_argument("key")
    p.add_argument("--from-file", required=True)
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

    if args.cmd == "list":
        for s in list_secrets(base_url, token, app.id):
            print(f"{s['key_name']}\t{s.get('description') or ''}")
        return 0
    if args.cmd == "set":
        action = set_secret(base_url, token, app.id, args.key, args.from_file, args.description)
        print(f"金鑰 {args.key}：{'已建立' if action == 'created' else '已更新'}（值未顯示）")
        return 0
    if delete_secret(base_url, token, app.id, args.key, confirm=args.confirm):
        print(f"金鑰 {args.key}：已刪除")
        return 0
    print(f"金鑰 {args.key}：不存在")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
