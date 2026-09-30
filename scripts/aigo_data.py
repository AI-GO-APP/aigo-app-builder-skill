"""
aigo_data.py — 以**登入使用者身分**直接操作 AI GO 資料（不經 Custom App proxy、不需要 app）

適用情景：用戶的目的不是開發 app，而是讀寫自己有權限的資料——查訂單、批次修客戶、
匯出報表、灌自建表。四條資料面（詳見 references/data-operations.md）：

| 資料面 | 端點 | 權限閘 |
|---|---|---|
| 預設表 | 各模組 REST `/api/v1/client`、`/sale`、`/crm`、`/hr`、`/stock`、`/purchase`、`/accounting`… | `<module>.read/write/delete` |
| 自建表 | `/api/v1/data-center/tables/{key}/records`（`aigo_data_center.py` 已封裝） | `builder.access` |
| 批次匯出／匯入 | `/api/v1/exports`（6 張預設表白名單）／`/api/v1/imports`（admin） | 該模組 read／`system.data_import` |
| 值域與結構 | `/api/v1/data-center/meta/tables/{key}`（select 型欄位帶 options） | 登入即可 |

路由事實以本 skill 的 references/ 為準（平台 prod／UAT 都已不對外供應 openapi.json）；
要確認一條路由在不在就直接打（寫入路由改對同路徑打 GET）：FastAPI 預設的 404 `{"detail":"Not Found"}`
＝這個 method＋path 不存在；405＝路徑存在（最可靠）；401／403＝路由在但權限不足。
422 或帶業務訊息的 404 可能來自相鄰的 `/{id}` 路由，不能單獨當「目標路由存在」的證據。`call --all` 依第一頁回應的形狀自動翻頁。

用法（工作區由 `--root` 或 `AIGO_PROJECT_ROOT` 指定，預設從目前目錄往上找）：
    uv run --project scripts python scripts/aigo_data.py me
    uv run --project scripts python scripts/aigo_data.py perm-check GET /api/v1/sale/orders
    uv run --project scripts python scripts/aigo_data.py call GET /api/v1/client --params limit=50 --all --out customers.json
    uv run --project scripts python scripts/aigo_data.py call POST /api/v1/client --json '{"name":"…","customer_type":"company"}'
    uv run --project scripts python scripts/aigo_data.py export sale_orders --format csv --wait --out sale_orders.csv
    uv run --project scripts python scripts/aigo_data.py meta table crm_clients

★ 寫入前一律先 `perm-check`，並把目標租戶與身分印給用戶確認——這裡打的是正式資料，沒有 app 沙箱。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

sys.path.insert(0, os.path.dirname(__file__))
from aigo_auth import find_workspace, get_token, resolve_base_url  # noqa: E402

PAGE_SAFETY_CAP = 20000  # --all 最多收多少列，避免把整個租戶拉下來
MUTATING = {"POST", "PUT", "PATCH", "DELETE"}

# 路徑前綴 → 權限模組（核自 backend/app/api/*.py 的 require_permission，2026-09-03）。
# 這是**推估**：少數端點另有細權限（hr.leave_manage、payroll.*、accounting.post…），以實際 403 為準。
PREFIX_MODULE: dict[str, str] = {
    "/api/v1/client": "crm",
    "/api/v1/crm": "crm",
    "/api/v1/sale": "sale",
    "/api/v1/purchase": "purchase",
    "/api/v1/supplier": "supplier",
    "/api/v1/stock": "stock",
    "/api/v1/hr": "hr",
    "/api/v1/accounting": "accounting",
    "/api/v1/mrp": "mrp",
    "/api/v1/project": "project",
}
VERB_ACTION = {"GET": "read", "POST": "write", "PUT": "write", "PATCH": "write", "DELETE": "delete"}

# 匯出白名單（backend/app/services/export_service.py ERP_EXPORT_REGISTRY，2026-09-03）
EXPORT_REGISTRY: dict[str, tuple[str, str]] = {
    "sale_orders": ("sale.read", "銷售訂單"),
    "purchase_orders": ("purchase.read", "採購訂單"),
    "stock_quants": ("stock.read", "即時庫存"),
    "crm_leads": ("crm.read", "商機"),
    "hr_employees": ("hr.read", "員工"),
    "account_moves": ("accounting.read", "會計傳票"),
}


# ── 基礎 ──────────────────────────────────────────────────────


def norm_path(path: str) -> str:
    """把使用者給的路徑正規化成 `/api/v1/...`。

    - Windows 的 Git Bash（MSYS）會把以 `/` 開頭的參數改寫成 `C:/Program Files/Git/api/v1/...`
      ——這裡把 `/api/v1/` 之前的東西全部砍掉（或設 `MSYS_NO_PATHCONV=1` 避免改寫）
    - 允許省略前綴：`client` 或 `sale/orders` → `/api/v1/client`、`/api/v1/sale/orders`
    """
    p = (path or "").strip().replace("\\", "/")
    marker = "/api/v1/"
    if marker in p and not p.startswith(marker):
        p = p[p.index(marker):]
    if not p.startswith("/"):
        p = "/api/v1/" + p
    elif not p.startswith("/api/"):
        p = "/api/v1" + p
    return p


class Session:
    """一個工作區＝一個租戶＝一把 token。"""

    def __init__(self, root: str = "."):
        ws = find_workspace(root)
        self.root = str(ws) if ws else root
        self.base_url = resolve_base_url(self.root)
        self.token = get_token(self.root)
        self.client = httpx.Client(
            base_url=self.base_url, headers={"Authorization": f"Bearer {self.token}"}, timeout=60
        )
        self._me: dict | None = None

    @property
    def tenant(self) -> str:
        return urlsplit(self.base_url).hostname or self.base_url

    def me(self) -> dict:
        if self._me is None:
            r = self.client.get("/api/v1/auth/me")
            r.raise_for_status()
            self._me = r.json()
        return self._me

    @property
    def permissions(self) -> set[str]:
        return set(self.me().get("permissions") or [])

    def describe(self) -> str:
        me = self.me()
        roles = "、".join(me.get("role_names") or me.get("roles") or []) or "?"
        return f"→ 租戶 {self.tenant}  身分 {me.get('email')}（{roles}）"


# ── OpenAPI（已停供） ─────────────────────────────────────────

OPENAPI_GONE = """❌ 平台已不對外供應 `/api/v1/openapi.json`（prod 與 UAT 都關閉，/docs、/redoc 一併關閉），
   `openapi paths／op／schema` 子指令因此停用。改用：
   1. 路由、參數、必填欄位 → 本 skill 的 references/（資料操作看 data-operations.md，
      各模組表結構看 default-table-lookup.md；值域用 `aigo_data.py meta table <key>`）
   2. 確認路由在不在 → 直接打：`aigo_data.py call GET <path>`。FastAPI 預設 404 `{"detail":"Not Found"}`
      ＝這個 method＋path 不存在；405＝路徑存在（最可靠）；401／403＝路由在但權限不足。
      422 或帶業務訊息的 404 可能是相鄰的 `/{id}` 路由回的，不能當證據。寫入路由**不要用寫入去試**——
      對同路徑打 GET，只有 405 Method Not Allowed 才代表路徑存在
   3. 文件說有、prod 打卻 404 → 可能是部署落差：prod 跑最新的 `v*` tag，main 先上 UAT"""


# ── 權限 ─────────────────────────────────────────────────────


def permission_for(method: str, path: str) -> str | None:
    """推估這條端點需要的權限標籤；None＝本表不認得（登入即可或另有規則）。"""
    m = method.upper()
    if path.startswith("/api/v1/data-center/meta"):
        return None
    if path.startswith("/api/v1/data-center"):
        if "/records" in path or "/images" in path:
            return "builder.access"
        if m == "DELETE":
            return "system.admin"
        return "datacenter.schema_write" if m in MUTATING else "builder.access"
    if path.startswith("/api/v1/imports"):
        return "system.data_import"
    # 成員／角色管理線（references/member-admin.md §2；核自 api/invitations.py、members.py @ v1.15.4）
    if path.startswith("/api/v1/invitations"):
        return "system.invitations"
    if path == "/api/v1/members/roles" or path.startswith("/api/v1/members/roles/"):
        return "system.roles_manage" if m in MUTATING else None  # GET 角色清單：登入即可
    if path.startswith("/api/v1/members"):
        return "hr.member_manage"  # 列表／單筆讀取也要 hr.member_manage，不是 hr.read
    if path.startswith("/api/v1/hosted-apps") and path.endswith("/access-settings"):
        return "hosted_apps.deploy"
    if path.startswith("/api/v1/builder/apps") and path.endswith("/settings"):
        return "builder.manage_access"
    # erp_core.py @ v1.15.4：分析帳走會計權限、銀行帳戶有獨立權限，其餘參考資料
    if path.startswith("/api/v1/erp/analytic"):
        return f"accounting.{VERB_ACTION[m]}"
    if path.startswith("/api/v1/erp/partner-banks"):
        return "system.partner_banks"
    if path.startswith("/api/v1/erp"):
        return "system.reference_data"
    if path.startswith("/api/v1/exports"):
        return None  # 依 target_ref 的模組 read 權限，見 EXPORT_REGISTRY
    for prefix, module in PREFIX_MODULE.items():
        if path == prefix or path.startswith(prefix + "/"):
            return f"{module}.{VERB_ACTION[m]}"
    return None


def check_permission(s: Session, method: str, path: str) -> tuple[bool | None, str]:
    """(通過?/None=無法判定, 說明)。system.admin 直通。"""
    need = permission_for(method, path)
    perms = s.permissions
    if need is None:
        return None, "本表沒有這條端點的權限規則（可能登入即可）；以實際回應為準"
    if "system.admin" in perms or need in perms:
        return True, f"需要 {need}——已具備" + ("（system.admin 直通）" if "system.admin" in perms else "")
    return False, f"需要 {need}——目前身分沒有；打了會 403，請管理員在角色 UI 授權後再試"


# ── 呼叫與翻頁 ────────────────────────────────────────────────


def _items_of(payload: Any) -> tuple[list, int | None]:
    if isinstance(payload, list):
        return payload, None
    if isinstance(payload, dict):
        for k in ("items", "data", "results"):
            if isinstance(payload.get(k), list):
                return payload[k], payload.get("total")
    return [], None


PAGING_CHOICES = ("auto", "page", "skip", "offset", "none")


def infer_pagination(payload: Any, params: dict | None = None) -> str | None:
    """從**實際回應**判分頁形狀（平台不再供應 openapi，無法事先查參數）。

    - 使用者已在 `--params` 帶 page／page_size → `page`；帶 skip → `skip`；帶 offset → `offset`
    - 信封回聲欄位：有 `page`／`page_size` → `page`；有 `offset` → `offset`；有 `skip`／`limit` → `skip`
      （平台模組 REST 多回 `{items,total,skip,limit}`，crm／資料中心回 `{items,total,page,page_size}`）
    - 只有 `{items,total}` 沒回聲 → `page`；裸 list → `skip`
    - 其他（單筆物件、無 items 的 dict）→ None，不翻頁
    """
    keys = set(params or {})
    if keys & {"page", "page_size"}:
        return "page"
    if "offset" in keys:
        return "offset"
    if "skip" in keys:
        return "skip"
    if isinstance(payload, list):
        return "skip"
    if isinstance(payload, dict):
        if not any(isinstance(payload.get(k), list) for k in ("items", "data", "results")):
            return None
        pk = set(payload)
        if pk & {"page", "page_size"}:
            return "page"
        if "offset" in pk:
            return "offset"
        if pk & {"skip", "limit"}:
            return "skip"
        if "total" in pk:
            return "page"
    return None


def call(
    s: Session, method: str, path: str, params: dict | None = None, body: Any = None,
    all_pages: bool = False, max_rows: int = PAGE_SAFETY_CAP, paging: str = "auto",
) -> Any:
    """通用呼叫。`all_pages=True` 時翻完所有頁、回合併後的 list。

    `paging="auto"` 先打一次（照使用者給的 params），依回應形狀判 page／skip／offset；
    也可明確指定 `page`（page＋page_size）、`skip`（skip＋limit）、`offset`（offset＋limit）、`none`。
    """
    m = method.upper()
    params = dict(params or {})
    if not all_pages:
        r = s.client.request(m, path, params=params or None, json=body)
        return _result(r)
    scheme: str | None = paging
    if paging == "auto":
        probe = _result(s.client.request(m, path, params=params or None))
        scheme = infer_pagination(probe, params)
        items, total = _items_of(probe)
        if scheme is None or (total is not None and len(items) >= total):
            if not items and probe and not isinstance(probe, list):
                return probe
            return items[:max_rows]
    if scheme == "none":
        payload = _result(s.client.request(m, path, params=params or None))
        rows, _ = _items_of(payload)
        return payload if (not rows and payload and not isinstance(payload, list)) else rows[:max_rows]
    if scheme == "page":
        size_key, pos_key = "page_size", "page"
        size = int(params.get("page_size") or 100)
        pos = int(params.get("page") or 1)
    else:  # skip / offset
        size_key, pos_key = "limit", scheme
        size = int(params.get("limit") or 100)
        pos = int(params.get(scheme) or 0)
    rows: list = []
    prev: list | None = None
    while True:
        params.update({pos_key: pos, size_key: size})
        payload = _result(s.client.request(m, path, params=params))
        items, total = _items_of(payload)
        if prev is not None and items and items == prev:
            # 端點不吃這組分頁參數、每次回同一頁——停，別無限重抓
            print(f"⚠️ 第二頁與前一頁相同：{path} 似乎不支援 {pos_key}／{size_key}，已停止翻頁；"
                  "可用 --paging 指定其他形狀", file=sys.stderr)
            break
        rows += items
        prev = items
        if not items or len(items) < size or (total is not None and len(rows) >= total) or len(rows) >= max_rows:
            break
        pos += 1 if scheme == "page" else size
    return rows[:max_rows]


def _result(r: httpx.Response) -> Any:
    if r.status_code >= 400:
        raise RuntimeError(f"❌ HTTP {r.status_code} {r.request.method} {r.request.url.path}\n   {r.text[:600]}")
    if r.status_code == 204 or not r.content:
        return None
    try:
        return r.json()
    except json.JSONDecodeError:
        return r.text


# ── 匯出 ─────────────────────────────────────────────────────


def export_create(s: Session, target: str, fmt: str = "json", filters: dict | None = None,
                  source_type: str | None = None) -> dict:
    """建立匯出任務。`target` 是白名單預設表名（source_type=erp_table）或舊 CustomObject 的 UUID。

    ⚠️ 資料中心**自建表不在**匯出範圍（`custom_table` 指的是舊 CustomObject，
    2026-09-03 測試租戶實測以自建表 id 送會 failed「custom object not in tenant」）——
    自建表要整表取出用 `call GET /api/v1/data-center/tables/{key}/records --all`。
    """
    st = source_type or ("custom_table" if "-" in target and len(target) >= 32 else "erp_table")
    if st == "erp_table" and target not in EXPORT_REGISTRY:
        raise RuntimeError(
            f"❌ `{target}` 不在匯出白名單。可匯出的預設表：{', '.join(EXPORT_REGISTRY)}\n"
            "   其他表改用 `call GET <模組列表端點> --all` 取回後自己落檔"
        )
    body: dict[str, Any] = {"source_type": st, "target_ref": target, "format": fmt}
    if filters:
        body["filters"] = filters
    return _result(s.client.post("/api/v1/exports", json=body))


def export_wait(s: Session, job_id: str, timeout: int = 300) -> dict:
    deadline = time.time() + timeout
    while True:
        job = _result(s.client.get(f"/api/v1/exports/{job_id}"))
        if job.get("status") in ("completed", "done", "succeeded", "failed", "error"):
            return job
        if time.time() > deadline:
            raise RuntimeError(f"❌ 匯出 {job_id[:8]} 在 {timeout} 秒內未完成（status={job.get('status')}）")
        time.sleep(2)


def export_download(s: Session, job_id: str, out: Path) -> Path:
    r = s.client.get(f"/api/v1/exports/{job_id}/download", follow_redirects=True)
    if r.status_code >= 400:
        raise RuntimeError(f"❌ 下載失敗 HTTP {r.status_code}：{r.text[:200]}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(r.content)
    return out


# ── Meta（值域） ──────────────────────────────────────────────


def meta_tables(s: Session, source: str | None = None, grep: str = "") -> list[dict]:
    """列全部表（預設表 source=erp、自建表 source=custom）。⚠️ 預設表的 Meta key 不一定等於
    proxy／refs 用的表名（例：客戶是 `crm_clients`，proxy 面叫 `customers`）——先列表再取。"""
    items: list[dict] = []
    page = 1
    while True:
        payload = _result(s.client.get("/api/v1/data-center/meta/tables", params={"page": page, "page_size": 100}))
        batch = payload.get("items", [])
        items += batch
        if not batch or len(items) >= payload.get("total", 0):
            break
        page += 1
    g = grep.lower()
    return [
        i for i in items
        if (not source or i.get("source") == source)
        and (not g or g in json.dumps(i, ensure_ascii=False).lower())
    ]


def meta_table(s: Session, key: str) -> dict:
    return _result(s.client.get(f"/api/v1/data-center/meta/tables/{key}"))


def value_domains(table: dict) -> list[tuple[str, list[str]]]:
    """從 Meta 回應抽出 select 型欄位的合法值。"""
    return [
        (f.get("key"), [o.get("value") for o in (f.get("options") or [])])
        for f in table.get("fields", []) if f.get("options")
    ]


# ── CLI ──────────────────────────────────────────────────────


def _kv(pairs: list[str] | None) -> dict:
    out: dict[str, Any] = {}
    for p in pairs or []:
        k, _, v = p.partition("=")
        out[k] = v
    return out


def _dump(obj: Any, out: str | None) -> None:
    text = json.dumps(obj, ensure_ascii=False, indent=2, default=str)
    if out:
        Path(out).write_text(text, encoding="utf-8")
        n = len(obj) if isinstance(obj, list) else 1
        print(f"✅ 已寫入 {out}（{n} 筆）")
    else:
        print(text if len(text) < 20000 else text[:20000] + f"\n… （共 {len(text)} 字元，加 --out 落檔）")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="aigo_data.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=os.environ.get("AIGO_PROJECT_ROOT", "."), help="工作區（預設從目前目錄往上找）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("me", help="目前身分、角色、權限清單")

    p = sub.add_parser("perm-check", help="推估端點需要的權限並對照目前身分")
    p.add_argument("method"); p.add_argument("path")

    # 已停用：平台不再供應 openapi.json。保留指令外形讓舊用法得到明確說明，而不是 argparse 錯誤
    p = sub.add_parser("openapi", help="（已停用）平台不再供應 openapi.json")
    p.add_argument("rest", nargs=argparse.REMAINDER)

    p = sub.add_parser("call", help="通用呼叫；GET 加 --all 自動翻頁")
    p.add_argument("method"); p.add_argument("path")
    p.add_argument("--params", nargs="*", help="k=v …（query string）")
    p.add_argument("--json", dest="json_body", help="JSON 字串 body")
    p.add_argument("--json-file", help="從檔案讀 body")
    p.add_argument("--all", action="store_true", help="翻完所有頁（依第一頁回應判分頁形狀）")
    p.add_argument("--paging", choices=PAGING_CHOICES, default="auto",
                   help="--all 的分頁形狀：auto（預設，看回應）／page（page+page_size）／skip（skip+limit）／offset／none")
    p.add_argument("--max", type=int, default=PAGE_SAFETY_CAP)
    p.add_argument("--out", help="結果寫入檔案（JSON）")
    p.add_argument("--dry-run", action="store_true", help="只印出將送出的請求")
    p.add_argument("--skip-perm-check", action="store_true")

    p = sub.add_parser("export", help="建立匯出任務（白名單預設表）")
    p.add_argument("target", help=f"預設表名（{'/'.join(EXPORT_REGISTRY)}）或舊 CustomObject UUID")
    p.add_argument("--format", default="json", choices=["json", "csv"])
    p.add_argument("--filters", help="JSON 物件")
    p.add_argument("--wait", action="store_true"); p.add_argument("--out")
    p = sub.add_parser("export-list"); p = sub.add_parser("export-download"); p.add_argument("job_id"); p.add_argument("--out", required=True)

    p = sub.add_parser("meta", help="表清單與值域（select 型欄位的合法值）")
    ps = p.add_subparsers(dest="sub", required=True)
    q = ps.add_parser("tables"); q.add_argument("--source", choices=["erp", "custom"]); q.add_argument("--grep", default="")
    q = ps.add_parser("table"); q.add_argument("key")

    a = ap.parse_args(argv)
    if a.cmd == "openapi":
        print(OPENAPI_GONE)
        return 2
    if getattr(a, "path", None):
        a.path = norm_path(a.path)
    s = Session(a.root)

    if a.cmd == "me":
        me = s.me()
        print(s.describe())
        print("permissions:", ", ".join(sorted(s.permissions)) or "（空）")
        return 0

    if a.cmd == "perm-check":
        ok, why = check_permission(s, a.method, a.path)
        print(("✅" if ok else "❓" if ok is None else "❌"), f"{a.method.upper()} {a.path}：{why}")
        return 0 if ok is not False else 1

    if a.cmd == "call":
        m = a.method.upper()
        params = _kv(a.params)
        body = None
        if a.json_body:
            body = json.loads(a.json_body)
        elif a.json_file:
            body = json.loads(Path(a.json_file).read_text(encoding="utf-8"))
        if m in MUTATING:
            print(s.describe())
            if not a.skip_perm_check:
                ok, why = check_permission(s, m, a.path)
                print(("✅" if ok else "❓" if ok is None else "❌"), why)
                if ok is False:
                    return 1
        if a.dry_run:
            print(json.dumps({"method": m, "url": s.base_url + a.path, "params": params, "body": body}, ensure_ascii=False, indent=2))
            return 0
        result = call(s, m, a.path, params=params, body=body, all_pages=a.all and m == "GET", max_rows=a.max, paging=a.paging)
        _dump(result, a.out)
        return 0

    if a.cmd == "export":
        print(s.describe())
        job = export_create(s, a.target, a.format, json.loads(a.filters) if a.filters else None)
        print(f"✅ 匯出任務 {job['id']}（{job.get('status')}）")
        if a.wait or a.out:
            job = export_wait(s, job["id"])
            print(f"   狀態 {job.get('status')}，{job.get('row_count')} 列")
            if job.get("status") not in ("completed", "done", "succeeded"):
                print("   錯誤：", job.get("error_message") or job.get("error"))
                return 1
            if a.out:
                export_download(s, job["id"], Path(a.out))
                print(f"✅ 已下載 {a.out}")
        return 0
    if a.cmd == "export-list":
        for j in _result(s.client.get("/api/v1/exports")):
            print(f"{j.get('id','')[:8]}  {j.get('status'):<10} {j.get('source_type')}:{j.get('target_ref')}  rows={j.get('row_count')}  {j.get('error_message') or ''}")
        return 0
    if a.cmd == "export-download":
        export_download(s, a.job_id, Path(a.out)); print(f"✅ 已下載 {a.out}")
        return 0

    if a.cmd == "meta":
        if a.sub == "tables":
            for t in meta_tables(s, a.source, a.grep):
                print(f"{t.get('source'):<7} {t.get('key'):<32} {t.get('title') or ''}  [{t.get('capability')}]")
        else:
            t = meta_table(s, a.key)
            print(f"{t.get('key')}  {t.get('title')}  [{t.get('capability')}]  {len(t.get('fields', []))} 欄")
            for f in t.get("fields", []):
                flag = "".join(x for x, ok in (("*", f.get("required")), ("r", f.get("readonly")), ("s", f.get("system"))) if ok)
                opts = f" ∈ {[o.get('value') for o in f['options']]}" if f.get("options") else ""
                print(f"  {f.get('key'):<28} {f.get('type'):<10} {flag:<3} {f.get('label') or ''}{opts}")
        return 0
    return 2


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    try:
        sys.exit(main())
    except RuntimeError as e:
        print(e)
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        print(f"❌ HTTP {e.response.status_code}: {e.response.text[:300]}")
        sys.exit(1)
