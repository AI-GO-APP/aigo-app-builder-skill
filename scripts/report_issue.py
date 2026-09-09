"""
report_issue.py — 平台問題回報（直達 AI GO 開發團隊的 Scrum Board）

在 AI IDE 內直接回報平台問題，不開任何 UI、不經 AI GO 平台。
憑證重用 builder 既有的 `~/.aigo/.env`（AIGO_EMAIL / AIGO_PASSWORD）：
回報帳號在**本地**衍生——AI GO 密碼不離開本機、不傳給回報系統。

用法：
    uv run python scripts/report_issue.py submit "一句話標題" \
        --given "情境：想完成什麼、當時在什麼狀態" --when "操作：做了什麼" \
        --then "結果：實際發生什麼（錯誤原文關鍵段落）" --expected "預期：依文件應該怎樣" \
        --ruled-out "已排除清單（回報前自審紀錄，每行一項）" \
        --user-confirmed \
        --image 截圖1.png --image 截圖2.png
    uv run python scripts/report_issue.py submit "標題" --body-file report.md --user-confirmed
        # 內文須含「情境」「操作」「結果」三段與「已排除」段
    uv run python scripts/report_issue.py list
    uv run python scripts/report_issue.py show <ticket_id>

截圖（--image，可重複最多 10 張；png/jpg/webp/gif 單張 ≤8MB）會上傳並
內嵌在開發團隊的卡片裡——UI 問題附截圖能大幅縮短來回。

回報內容規範（BDD，詳見 references/issue-reporting.md）：
骨架是「情境（想完成什麼）→ 操作（做了什麼）→ 結果（實際發生什麼）→ 預期（依文件應該怎樣）」，
重心是「嘗試做什麼、結果是什麼」。三段缺一拒收；內文出現技術建議／修法／根因猜測也拒收。

回報前自審閘門（references/pre-report-self-grill.md）：
預設平台必定正確、失敗是自己操作有誤。`submit` 必須帶 `--ruled-out`（已排除清單，
至少三項、每項有證據），或 `--body-file` 內文含「已排除」段落；缺少即拒收、不建卡。

送出確認（SKILL.md「問題回報」第 4–5 步）：
自審通過後 agent 要先把摘要拿給使用者、問要不要提交；使用者同意才帶 `--user-confirmed` 送出。
缺少同樣拒收、不建卡。旗標的真假 CLI 驗不了，靠對話裡的摘要與問句可稽核。
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
    ("given", "情境（想完成什麼、當時在什麼狀態）"),
    ("when", "操作（做了什麼）"),
    ("then", "結果（實際發生什麼）"),
    ("expected", "預期（依文件應該怎樣）"),
    ("context", "環境／補充"),
]
REQUIRED_BDD = ("given", "when", "then")          # 缺一不建卡
BDD_BODY_MARKERS = ("情境", "操作", "結果")       # --body／--body-file 內文至少要有這三個段落字樣
THEN_SOFT_LIMIT = 1200                            # 結果段超過此長度提醒：原文貼關鍵段落，完整輸出留在已排除清單

# 內文出現這些措辭＝在開藥方（技術建議／修法／根因猜測），拒收。只掃 BDD 內文，不掃已排除清單。
PRESCRIPTIVE_PATTERNS = (
    r"建議(把|將|改|用|加|移除|採用|在)",
    r"應該(改|把|將|用|加|移除)",
    r"應改為",
    r"修法",
    r"實作方式",
    r"實作建議",
    r"怎麼修",
    r"如何修",
    r"root cause",
    r"根因(是|在|為)",
    r"請修改",
)

BDD_SUMMARY = """\
❌ 拒收：缺「%s」。回報要用 BDD 骨架寫「嘗試做什麼、結果是什麼」，不是先講技術契約：
   --given    情境：想完成什麼、當時在什麼狀態（一句使用者目標層的話，例：想把含中文檔名的元件同步上去）
   --when     操作：做了什麼（步驟、打了哪個端點；可含 payload 形狀）
   --then     結果：實際發生什麼（狀態碼＋錯誤原文的關鍵段落；指令與完整輸出留在 --ruled-out）
   --expected 預期：依文件應該怎樣（對照用，放結果之後）
   用 --body／--body-file 時，內文須含「情境」「操作」「結果」三個段落。見 references/issue-reporting.md。
"""


def _check_bdd(args: argparse.Namespace, body: str) -> None:
    """BDD 骨架閘門：情境／操作／結果三段缺一不建卡。"""
    structured = any(getattr(args, k, None) for k, _ in BDD_SECTIONS)
    if structured and not args.body_file:
        missing = [h.split("（")[0] for k, h in BDD_SECTIONS if k in REQUIRED_BDD and not getattr(args, k)]
    else:
        missing = [m for m in BDD_BODY_MARKERS if m not in body]
    if missing:
        raise RuntimeError(BDD_SUMMARY % "、".join(missing))


def _check_no_prescription(body: str) -> None:
    """開藥方閘門：內文有技術建議／修法／根因猜測就不建卡，印出命中的句子讓人改寫。"""
    hits = []
    for line in body.splitlines():
        for pat in PRESCRIPTIVE_PATTERNS:
            m = re.search(pat, line, re.IGNORECASE)
            if m:
                hits.append((m.group(0), line.strip()))
                break
    if not hits:
        return
    msg = "❌ 拒收：內文在開藥方（技術建議／修法／根因猜測）。回報寫行為，不寫解法——解法是開發團隊拿完整脈絡做的事：\n"
    for phrase, line in hits[:5]:
        msg += f"   「{phrase}」← {line[:80]}\n"
    msg += "   改寫成「做了什麼 → 發生了什麼 → 依文件應該怎樣」再送。"
    raise RuntimeError(msg)


def _warn_then_length(args: argparse.Namespace) -> None:
    then = getattr(args, "then", None) or ""
    if len(then) > THEN_SOFT_LIMIT:
        print(f"⚠️  「結果」段有 {len(then)} 字——錯誤原文只貼關鍵段落，指令與完整輸出留在 --ruled-out。仍照送。")

RULED_OUT_HEADING = "已排除（回報前自審）"
RULED_OUT_MARKER = "已排除"      # --body-file 內文至少要有這個字樣的段落
RULED_OUT_MIN_ITEMS = 3          # 六輪自審濃縮後不可能少於三項；少於此數視同沒排除

SELF_GRILL_SUMMARY = """\
❌ 拒收：缺「已排除清單」。預設平台必定正確、失敗是自己操作有誤——
   回報前必須走完 references/pre-report-self-grill.md 的六輪自審：
     0 讀完錯誤原文、症狀唯一化
     1 版本與部署落差（skill 版本、prod 落後 main、文件既有 ⚠️ 註記）
     2 身分與環境（租戶網址、401/403、權限層級、產品線與模式、乾淨環境對照）
     3 請求契約（{"data"} 包裝、實體名、filters 契約、型別格式、路徑、既有路徑）
     4 生命週期（發布快照、簽核攔截、409/423、非同步延遲、平台刻意設計、自己的 bundle）
     5 文件核對（troubleshooting、對應章節、CONTEXT 術語；文件沒寫 ≠ 平台錯）
     6 最小重現（去除 app 程式碼直打 API、穩定重現、最小 payload、對照組）
   每題附指令＋輸出節錄，濃縮成清單後用 --ruled-out（或 --ruled-out-file）送出，
   至少 %d 項。寫不出來就代表還沒排除完——不要報，先把自審紀錄交給使用者。
""" % RULED_OUT_MIN_ITEMS


USER_CONFIRM_HEADING = "送出確認"
USER_CONFIRM_LINE = "使用者已看過摘要（情境／操作／結果／預期／已排除清單）並同意送出。"
USER_CONFIRM_SUMMARY = """\
❌ 拒收：缺 --user-confirmed。自審通過不等於可以送——送出與否由使用者決定，問的人是 agent：
   1. 先把摘要拿給使用者（references/pre-report-self-grill.md §3 的固定格式）：
        【疑似平台問題】<症狀一句>
        情境：… ／ 操作：… ／ 結果：… ／ 預期：… ／ 已排除：…
        要不要提交給開發團隊？
   2. 使用者說「送」→ 原指令加 --user-confirmed 重送
   3. 使用者說「不送」→ 自審紀錄留在專案，不送
   沒問過就帶 --user-confirmed ＝ 替使用者決定，是最嚴重的違規。
"""


def _check_user_confirmed(args: argparse.Namespace) -> None:
    """送出確認閘門：使用者未點頭就不建卡。"""
    if not getattr(args, "user_confirmed", False):
        raise RuntimeError(USER_CONFIRM_SUMMARY)


def _ruled_out_text(args: argparse.Namespace) -> str:
    """--ruled-out / --ruled-out-file 的內容；沒給回空字串。"""
    if getattr(args, "ruled_out_file", None):
        return Path(args.ruled_out_file).read_text(encoding="utf-8").strip()
    return (getattr(args, "ruled_out", None) or "").strip()


def _ruled_out_items(text: str) -> list:
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def _check_self_grill(args: argparse.Namespace, body: str) -> str:
    """回報前自審閘門。通過回傳已排除清單原文（可能為空，代表已在 body 內）；不通過拋 RuntimeError。"""
    ruled = _ruled_out_text(args)
    if ruled:
        items = _ruled_out_items(ruled)
        if len(items) < RULED_OUT_MIN_ITEMS:
            raise RuntimeError(
                f"❌ 拒收：--ruled-out 只有 {len(items)} 項（至少 {RULED_OUT_MIN_ITEMS} 項，每行一項）。\n"
                "   六輪自審濃縮後不可能只有這幾項——請補齊版本／身分／契約／生命週期／文件／重現的證據。"
            )
        return ruled
    if RULED_OUT_MARKER in body:
        return ""
    raise RuntimeError(SELF_GRILL_SUMMARY)


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


PREFLIGHT_LABEL = {
    "fixed": "同症狀的卡已修復（Done）",
    "tracking": "同症狀的卡處理中",
    "none": "沒有同症狀的卡",
}


def _preflight(client: httpx.Client, token: str, title: str, body: str, tenant: str):
    """
    開單前查既有卡（CSM Manager #46／本 repo #43）：送出前先問伺服器
    「同症狀是否已有卡、修好了沒」。

    ★ 第一階段只查、只記，**不改流程**：不論 decision 是什麼都照常送出。
    要等命中率看得到（伺服器每日統計「開單前查卡」那一行）才會開第二階段
    ——已修復一句帶過、自動重試、續行。原因：伺服器端歸卡上線至今零命中實績，
    誤命中的代價是 AI 對使用者說「修好了我直接繼續」然後重試失敗。

    best-effort：任何失敗（連線、非 200、伺服器沒這個端點）都回 None，照常送出。
    設 URFIT_TICKET_PREFLIGHT=0 可整個關掉。
    """
    if os.environ.get("URFIT_TICKET_PREFLIGHT", "1") == "0":
        return None
    try:
        resp = _post(client, f"{_api_base()}/api/tickets/preflight", {
            "title": title,
            "content": body,
            "site_key": tenant,
        }, token)
    except httpx.HTTPError as e:
        print(f"ℹ️  開單前查卡略過（連線問題：{e}）")
        return None
    if resp.status_code != 200:
        print(f"ℹ️  開單前查卡略過（HTTP {resp.status_code}）")
        return None
    data = resp.json()
    decision = data.get("decision", "none")
    match = data.get("match") or {}
    extra = ""
    if match:
        extra = f"：{match.get('title', '')}（信心 {match.get('confidence')}"
        extra += f"，修好於 {str(match.get('done_at', ''))[:10]}）" if match.get("done_at") else "）"
    print(f"🔎 開單前查卡：{PREFLIGHT_LABEL.get(decision, decision)}{extra}——第一階段僅記錄，仍照常送出")
    return data


def _report_outcome(client: httpx.Client, token: str, preflight_id: str, outcome: str) -> None:
    """回報 skill 照 decision 做了什麼（第一階段一律 submitted）。稽核用，失敗不影響回報。"""
    try:
        client.post(
            f"{_api_base()}/api/tickets/preflight/{preflight_id}/outcome",
            json={"outcome": outcome},
            headers={"Authorization": f"Bearer {token}"},
        )
    except httpx.HTTPError:
        pass


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
        print("❌ 需要內文：用 --given/--when/--then/--expected（建議）、--body 或 --body-file")
        return 1
    # ★ BDD 骨架閘門：情境／操作／結果三段缺一不建卡；內文開藥方也不建卡（references/issue-reporting.md）
    _check_bdd(args, body)
    _check_no_prescription(body)
    _warn_then_length(args)

    # ★ 回報前自審閘門：沒有已排除清單就不建卡（references/pre-report-self-grill.md）
    ruled = _check_self_grill(args, body)
    if ruled:
        body = f"{body}\n\n## {RULED_OUT_HEADING}\n{ruled}"
    # ★ 送出確認閘門：自審通過後要先問使用者，使用者同意才建卡（SKILL.md「問題回報」第 4–5 步）
    _check_user_confirmed(args)
    body = f"{body}\n\n## {USER_CONFIRM_HEADING}\n{USER_CONFIRM_LINE}"

    creds = derive_credentials(args.project)
    title = args.title.strip()[:80]
    content = body[:4000]
    with httpx.Client(timeout=60) as client:
        token = authenticate(client, creds)
        # 開單前查既有卡（第一階段只記錄，見 _preflight）
        pf = _preflight(client, token, title, content, creds["tenant"])
        preflight_id = (pf or {}).get("preflight_id") or ""
        attachments = _upload_images(client, token, args.image or [])
        payload = {
            "title": title,
            "content": content,
            "source": "agent",
            "site_key": creds["tenant"],
            "client_msg_id": str(uuid.uuid4()),
            "attachments": attachments,
        }
        # 帶 preflight_id 送出：伺服器據此直接附掛（tracking）或當復發處理，並把這張票
        # 掛回那次判斷供稽核。伺服器不認這個 id（400／409）就退回不帶它再送一次——
        # 查卡是加分項，不能反過來擋住回報
        resp = _post(client, f"{_api_base()}/api/tickets",
                     {**payload, "preflight_id": preflight_id} if preflight_id else payload, token)
        if preflight_id and resp.status_code in (400, 409) and "preflight" in resp.text:
            print(f"ℹ️  伺服器不接受 preflight_id（HTTP {resp.status_code}），改不帶它送出")
            payload["client_msg_id"] = str(uuid.uuid4())
            resp = _post(client, f"{_api_base()}/api/tickets", payload, token)
        if resp.status_code == 201 and preflight_id:
            _report_outcome(client, token, preflight_id, "submitted")
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
    p_submit.add_argument("--given", help="★ 情境：想完成什麼、當時在什麼狀態（一句使用者目標層的話）")
    p_submit.add_argument("--when", "--steps", dest="when",
                          help="★ 操作：做了什麼（步驟、打了哪個端點；--steps 是舊名）")
    p_submit.add_argument("--then", "--actual", dest="then",
                          help="★ 結果：實際發生什麼（狀態碼＋錯誤原文關鍵段落；--actual 是舊名）")
    p_submit.add_argument("--expected", help="預期：依文件應該怎樣（對照用，放在結果之後）")
    p_submit.add_argument("--context", help="環境／補充（app_id、時間、request_id…）")
    p_submit.add_argument("--body", help="自由格式內文（須含「情境」「操作」「結果」三段）")
    p_submit.add_argument("--body-file", help="從檔案讀內文")
    p_submit.add_argument("--image", action="append",
                          help="附加截圖（可重複，最多 10 張；png/jpg/webp/gif ≤8MB）")
    p_submit.add_argument("--ruled-out",
                          help=f"★ 已排除清單（回報前自審紀錄，每行一項、至少 {RULED_OUT_MIN_ITEMS} 項）；"
                               "缺少即拒收，見 references/pre-report-self-grill.md")
    p_submit.add_argument("--ruled-out-file", help="從檔案讀已排除清單")
    p_submit.add_argument("--user-confirmed", action="store_true",
                          help="★ 使用者已看過摘要並同意送出（SKILL.md「問題回報」第 4 步）；缺少即拒收")
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
