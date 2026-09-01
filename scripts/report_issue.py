"""
report_issue.py — 平台問題回報（直達 AI GO 開發團隊的 Scrum Board）

在 AI IDE 內直接回報平台問題，不開任何 UI、不經 AI GO 平台。
憑證重用 builder 既有的 `~/.aigo/.env`（AIGO_EMAIL / AIGO_PASSWORD）：
回報帳號在**本地**衍生——AI GO 密碼不離開本機、不傳給回報系統。

用法：
    uv run python scripts/report_issue.py submit "一句話標題" \
        --expected "預期行為" --actual "實際結果" --steps "重現步驟" \
        --image 截圖1.png --image 截圖2.png
    uv run python scripts/report_issue.py submit "標題" --body-file report.md
    uv run python scripts/report_issue.py list
    uv run python scripts/report_issue.py show <ticket_id>

截圖（--image，可重複最多 10 張；png/jpg/webp/gif 單張 ≤8MB）會上傳並
內嵌在開發團隊的卡片裡——UI 問題附截圖能大幅縮短來回。

回報內容規範（BDD，詳見 references/issue-reporting.md）：
寫「行為」不寫「解法」——預期 vs 實際 + 重現步驟；不要提技術建議或實作方式。
"""

import argparse
import hashlib
import os
import re
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

import httpx

sys.path.insert(0, os.path.dirname(__file__))
from aigo_auth import load_env_file, resolve_base_url  # noqa: E402

# 回報系統（獨立部署的 ticket widget，與 AI GO 平台無關；平台掛掉時仍可回報）
DEFAULT_API = "https://urfit-ticket-widget.agent99apps.workers.dev"
ACCOUNT_DOMAIN = "ticket.urfit.com.tw"  # 不收信網域，僅作帳號識別

MAX_IMAGES = 10
MAX_IMAGE_BYTES = 8 * 1024 * 1024
IMAGE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


def _api_base() -> str:
    return os.environ.get("URFIT_TICKET_API", DEFAULT_API).rstrip("/")


def _tenant_slug(project_path: str) -> str:
    """從生效的租戶網址取 slug（https://urfit.ai-go.app → urfit）。"""
    host = urlparse(resolve_base_url(project_path)).hostname or ""
    return host.split(".")[0] or "unknown"


def derive_credentials(project_path: str = ".") -> dict:
    """
    由 AIGO_EMAIL + AIGO_PASSWORD + 租戶 slug 衍生回報帳號。

    - 密碼 = sha256 衍生值：AI GO 密碼**不出本機**，也與回報系統互相隔離
    - 帳號 email 帶衍生值前 6 碼：AI GO 密碼變更後會自動換一個回報帳號
      （舊回報清單自此分離，但回報功能不中斷、不會卡死在憑證漂移）
    - contact_email 帶真實信箱，開發團隊在卡片上看得到回報者是誰
    """
    load_env_file(project_path)
    email = os.environ.get("AIGO_EMAIL", "").strip().lower()
    password = os.environ.get("AIGO_PASSWORD", "")
    if not email or not password:
        raise RuntimeError(
            "❌ 找不到 AI GO 憑證（AIGO_EMAIL / AIGO_PASSWORD）。\n"
            "   回報帳號由它們衍生；請先完成 builder 憑證設定：\n"
            "   uv run python scripts/aigo_auth.py setup"
        )

    tenant = _tenant_slug(project_path)
    digest = hashlib.sha256(
        f"urfit-ticket:{tenant}:{email}:{password}".encode()
    ).hexdigest()
    local = re.sub(r"[^a-z0-9._-]", "-", email.split("@")[0])
    return {
        "email": f"aigo.{tenant}.{local}.{digest[:6]}@{ACCOUNT_DOMAIN}",
        "password": digest,
        "contact_email": email,
        "display_name": email.split("@")[0],
        "tenant": tenant,
    }


def _post(client: httpx.Client, url: str, payload: dict, token: str = "") -> httpx.Response:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    resp = client.post(url, json=payload, headers=headers)
    if resp.status_code == 429:
        # 認證端點每 IP 每分鐘 30 次；等它說的秒數重試一次
        wait = int((resp.json().get("retry_after") or 60)) + 1
        print(f"⏳ 連線頻率限制，{wait} 秒後重試…")
        time.sleep(wait)
        resp = client.post(url, json=payload, headers=headers)
    return resp


def authenticate(client: httpx.Client, creds: dict) -> str:
    """登入；帳號不存在就自動註冊。回傳 access token。"""
    api = _api_base()
    login = _post(client, f"{api}/api/auth/login", {
        "email": creds["email"],
        "password": creds["password"],
        "contact_email": creds["contact_email"],
    })
    if login.status_code == 200:
        return login.json()["access_token"]
    if login.status_code != 401:
        raise RuntimeError(f"❌ 回報系統登入失敗（HTTP {login.status_code}）：{login.text[:200]}")

    reg = _post(client, f"{api}/api/auth/register", {
        "email": creds["email"],
        "password": creds["password"],
        "display_name": creds["display_name"],
        "contact_email": creds["contact_email"],
    })
    if reg.status_code == 200:
        return reg.json()["access_token"]
    raise RuntimeError(f"❌ 回報帳號建立失敗（HTTP {reg.status_code}）：{reg.text[:200]}")


# === 指令 ===

BDD_SECTIONS = [
    ("expected", "預期行為"),
    ("actual", "實際結果"),
    ("steps", "重現步驟"),
    ("context", "環境／補充"),
]


def _compose_body(args: argparse.Namespace) -> str:
    if args.body_file:
        return Path(args.body_file).read_text(encoding="utf-8").strip()
    if any(getattr(args, key) for key, _ in BDD_SECTIONS):
        parts = []
        for key, heading in BDD_SECTIONS:
            value = getattr(args, key)
            if value:
                parts.append(f"## {heading}\n{value}")
        return "\n\n".join(parts)
    return (args.body or "").strip()


def _upload_images(client: httpx.Client, token: str, paths: list) -> list:
    """逐張上傳截圖，回傳附件 key 清單。任何一張失敗就整筆中止（不建缺圖的卡）。"""
    if len(paths) > MAX_IMAGES:
        raise RuntimeError(f"❌ 截圖最多 {MAX_IMAGES} 張（收到 {len(paths)} 張）")
    keys = []
    for i, raw in enumerate(paths, 1):
        p = Path(raw)
        ctype = IMAGE_TYPES.get(p.suffix.lower())
        if not p.is_file():
            raise RuntimeError(f"❌ 找不到截圖：{p}")
        if not ctype:
            raise RuntimeError(f"❌ 不支援的圖片格式：{p.name}（僅收 png/jpg/webp/gif）")
        data = p.read_bytes()
        if len(data) > MAX_IMAGE_BYTES:
            raise RuntimeError(f"❌ {p.name} 超過單張 8MB 上限")
        print(f"⬆️  上傳截圖 {i}/{len(paths)}：{p.name}")
        resp = client.post(
            f"{_api_base()}/api/uploads",
            content=data,
            headers={"Authorization": f"Bearer {token}", "Content-Type": ctype},
        )
        if resp.status_code != 201:
            raise RuntimeError(f"❌ 截圖上傳失敗（HTTP {resp.status_code}）：{resp.text[:200]}")
        keys.append(resp.json()["key"])
    return keys


def cmd_submit(args: argparse.Namespace) -> int:
    body = _compose_body(args)
    if not body:
        print("❌ 需要內文：用 --expected/--actual/--steps（建議）、--body 或 --body-file")
        return 1
    if not ("預期" in body and "實際" in body):
        print("⚠️  內文缺「預期行為 vs 實際結果」——請盡量用 BDD 描述行為，")
        print("    不要寫技術建議或實作方式（見 references/issue-reporting.md）。仍照送。")

    creds = derive_credentials(args.project)
    with httpx.Client(timeout=60) as client:
        token = authenticate(client, creds)
        attachments = _upload_images(client, token, args.image or [])
        resp = _post(client, f"{_api_base()}/api/tickets", {
            "title": args.title.strip()[:80],
            "content": body[:4000],
            "source": "agent",
            "site_key": creds["tenant"],
            "client_msg_id": str(uuid.uuid4()),
            "attachments": attachments,
        }, token)
    if resp.status_code != 201:
        print(f"❌ 回報失敗（HTTP {resp.status_code}）：{resp.text[:200]}")
        return 1
    data = resp.json()
    print(f"✅ 已回報（{creds['tenant']}）：{args.title.strip()[:80]}")
    print(f"   ticket_id: {data['ticket_id']}")
    print(f"   目前狀態: {data['status']}（追蹤：report_issue.py show {data['ticket_id']}）")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    creds = derive_credentials(args.project)
    with httpx.Client(timeout=30) as client:
        token = authenticate(client, creds)
        resp = client.get(
            f"{_api_base()}/api/tickets",
            headers={"Authorization": f"Bearer {token}"},
        )
    if resp.status_code != 200:
        print(f"❌ 讀取失敗（HTTP {resp.status_code}）")
        return 1
    tickets = resp.json().get("tickets", [])
    if not tickets:
        print("（尚無回報紀錄）")
        return 0
    for t in tickets:
        print(f"[{t['status']:>13}] {t['id'][:8]}…  {t['title']}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    creds = derive_credentials(args.project)
    with httpx.Client(timeout=30) as client:
        token = authenticate(client, creds)
        resp = client.get(
            f"{_api_base()}/api/tickets/{args.ticket_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
    if resp.status_code == 404:
        print("❌ 找不到這筆回報（id 錯誤，或不屬於目前的回報帳號）")
        return 1
    if resp.status_code != 200:
        print(f"❌ 讀取失敗（HTTP {resp.status_code}）")
        return 1
    data = resp.json()
    t = data["ticket"]
    print(f"{t['title']}\n狀態：{t['status']}｜建立：{t['created_at'][:16]}\n" + "─" * 40)
    role_label = {"user": "回報者", "agent": "AI Agent", "staff": "★ 官方回覆"}
    for m in data.get("messages", []):
        print(f"\n[{role_label.get(m['role'], m['role'])}] {m['sent_at'][:16]}")
        print(m["content"])
        for url in m.get("attachments") or []:
            print(f"🖼  {url}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="平台問題回報（BDD：寫行為，不寫解法）")
    parser.add_argument("--project", default=".", help="專案根目錄（決定租戶，預設目前目錄）")
    sub = parser.add_subparsers(dest="command", required=True)

    p_submit = sub.add_parser("submit", help="提交回報")
    p_submit.add_argument("title", help="一句話標題（≤80 字）")
    p_submit.add_argument("--expected", help="預期行為")
    p_submit.add_argument("--actual", help="實際結果（含完整錯誤訊息關鍵段落）")
    p_submit.add_argument("--steps", help="重現步驟")
    p_submit.add_argument("--context", help="環境／補充（app_id、時間、request_id…）")
    p_submit.add_argument("--body", help="自由格式內文（仍應含預期 vs 實際）")
    p_submit.add_argument("--body-file", help="從檔案讀內文")
    p_submit.add_argument("--image", action="append",
                          help="附加截圖（可重複，最多 10 張；png/jpg/webp/gif ≤8MB）")
    p_submit.set_defaults(func=cmd_submit)

    p_list = sub.add_parser("list", help="列出自己回報過的問題與目前狀態")
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show", help="單筆詳情（含官方回覆）")
    p_show.add_argument("ticket_id")
    p_show.set_defaults(func=cmd_show)

    args = parser.parse_args()
    try:
        return args.func(args)
    except RuntimeError as e:
        print(e)
        return 1
    except httpx.HTTPError as e:
        print(f"❌ 連線失敗：{e}")
        return 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    sys.exit(main())
