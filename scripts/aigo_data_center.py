"""AI GO 資料中心自建表管理工具

自建表是**租戶級**資源（不綁 app），端點前綴 /api/v1/data-center/。
權限：建／改／刪結構需 system.admin；讀結構與記錄 CRUD 需 builder.access。

規格見 references/data-center.md，術語見 CONTEXT.md。
"""
from typing import Any, Optional

FIELD_TYPES = {
    "text", "number", "boolean", "date", "datetime",
    "select", "relation", "json", "image",
}
# 系統欄位的**實體名**。建表時自動產生，不可刪、不計欄位配額。
SYSTEM_FIELD_NAMES = {"id", "created_at", "updated_at"}
# 單次 POST /tables 的欄位數上限（schema 層 max_length=50）。
# 這與「每表欄位配額」（免費 50／付費 100）是兩回事：付費租戶要建 60 欄，
# 必須先建表再逐次 add_field()，否則拿到的是 422 而不是 409。
MAX_FIELDS_PER_CREATE = 50


class PermissionDenied(Exception):
    """403。`needs` 說明缺哪個權限。

    結構操作（needs="system.admin"）→ 上層應**降級**：輸出可照抄的建表規格，
    引導用戶到資料中心 UI 自建，建完再用 list_tables() 驗收。
    資料操作（needs="builder.access"）→ 帳號根本沒有資料中心存取權，
    降級成「請用戶開權限」，**不要**叫他去 UI 建表。
    """

    def __init__(self, message: str, needs: str = "system.admin"):
        super().__init__(message)
        self.needs = needs


# 相容別名：舊呼叫端 except AdminRequired 仍可運作
AdminRequired = PermissionDenied


class QuotaOrConflict(Exception):
    """409：撞配額、實體名撞名、唯一值重複、關聯衝突等。

    `detail` 保留後端的結構化內容——刪表被真 FK 擋下時，
    detail["dependents"] 是「被哪些表依賴」的唯一線索。
    """

    def __init__(self, message: str, detail: Any = None):
        super().__init__(message)
        self.detail = detail


def _headers(token: str, json_body: bool = False) -> dict:
    h = {"Authorization": f"Bearer {token}"}
    if json_body:
        h["Content-Type"] = "application/json"
    return h


def _base(base_url: str) -> str:
    return f"{base_url}/api/v1/data-center"


def _raise_for(resp, scope: str = "schema") -> None:
    """把常見狀態碼翻成有語義的例外。

    scope="schema"：結構操作，403 代表缺 system.admin
    scope="data"  ：讀取／記錄操作，403 代表缺 builder.access（或跨租戶）
    """
    if resp.status_code == 403:
        if scope == "schema":
            raise PermissionDenied(
                "結構操作需 system.admin 權限。請改為輸出建表規格，"
                "引導用戶到資料中心 UI 自建，建完再以 list_tables() 驗收。",
                needs="system.admin",
            )
        raise PermissionDenied(
            "資料中心存取被拒（需 builder.access，或目標不屬於本租戶）。"
            "這不是建表權限問題，不要引導用戶去 UI 建表。",
            needs="builder.access",
        )
    if resp.status_code == 409:
        detail = None
        try:
            detail = resp.json().get("detail")
        except Exception:
            pass
        raise QuotaOrConflict(f"409 衝突：{resp.text}", detail=detail)
    resp.raise_for_status()


# ── 盤點（★ 建表前必跑）────────────────────────────────────────────────

def list_tables(base_url: str, token: str) -> list[dict]:
    """列出租戶所有自建表（含欄位定義）。回傳陣列，不是分頁信封。

    ★ 建表前必須先跑這支。自建表跨 app 共用——語意相同的表已存在就重用，
    重複建表會讓同一份業務資料分裂成兩張表。
    """
    import httpx
    resp = httpx.get(f"{_base(base_url)}/tables", headers=_headers(token), timeout=30)
    _raise_for(resp, scope="data")
    return resp.json()


def get_table(base_url: str, token: str, key: str) -> dict:
    """讀單一自建表結構。key = 表的實體名（physical_name）。"""
    import httpx
    resp = httpx.get(f"{_base(base_url)}/tables/{key}", headers=_headers(token), timeout=30)
    _raise_for(resp, scope="data")
    return resp.json()


def find_similar_tables(tables: list[dict], keywords: list[str]) -> list[dict]:
    """在既有自建表中找語意可能重複的表，供建表前判斷是否重用。

    比對顯示名與實體名。這只是提示，最終「重用或新建」由用戶在 Phase 1.5 決定。
    """
    terms = [k.strip().lower() for k in keywords if k and k.strip()]
    if not terms:
        return []
    hits = []
    for t in tables:
        haystack = f"{t.get('display_name', '')} {t.get('physical_name', '')}".lower()
        if any(k in haystack for k in terms):
            hits.append(t)
    return hits


# ── 表結構（需 system.admin）──────────────────────────────────────────

def validate_field_spec(field: dict) -> None:
    """建表／加欄前的本地檢查，避免送出必然失敗的請求。"""
    import uuid as _uuid

    if not field.get("display_name"):
        raise ValueError("欄位缺少 display_name（顯示名）")
    name = field["display_name"]
    ftype = field.get("field_type")
    if ftype not in FIELD_TYPES:
        raise ValueError(f"欄位 '{name}' 的型別 '{ftype}' 未知，可用：{sorted(FIELD_TYPES)}")
    if ftype == "select" and not field.get("options"):
        raise ValueError(f"select 欄位 '{name}' 必須提供 options 選項集")
    if ftype == "relation":
        tid, erp = field.get("target_table_id"), field.get("target_erp_key")
        if bool(tid) == bool(erp):
            raise ValueError(
                f"relation 欄位 '{name}' 必須指定 target_table_id"
                "（指向自建表，建真外鍵）或 target_erp_key（指向預設表，軟關聯）之一"
            )
        if tid:
            # ★ 這是本模組唯一不用實體名的地方，最容易填錯
            try:
                _uuid.UUID(str(tid))
            except (ValueError, AttributeError, TypeError):
                raise ValueError(
                    f"relation 欄位 '{name}' 的 target_table_id 必須是目標表的 id（UUID），"
                    "不是 physical_name。請從 list_tables() 取 t['id']。"
                )


def create_table(base_url: str, token: str, display_name: str,
                 fields: list[dict], section_path: Optional[list[str]] = None) -> dict:
    """建表（含首批欄位）。需 system.admin。

    只給顯示名，實體名由系統生成且**建立後永不可變**。
    403 → 拋 PermissionDenied，上層應降級成引導用戶到 UI 自建。

    fields 元素形狀：
        {"display_name": "姓名", "field_type": "text",
         "is_required": True, "is_unique": False,
         "options": [...],            # 僅 select
         "target_table_id": "<UUID>", # 僅 relation → 自建表（真 FK）
         "target_erp_key": "..."}     # 僅 relation → 預設表（軟關聯）
    """
    import httpx
    for f in fields:
        validate_field_spec(f)
    if len(fields) > MAX_FIELDS_PER_CREATE:
        raise ValueError(
            f"單次建表最多 {MAX_FIELDS_PER_CREATE} 個欄位（收到 {len(fields)}）。"
            "超過的部分請先建表，再逐次 add_field()——這是 schema 層上限，"
            "與每表欄位配額（免費 50／付費 100）不同。"
        )

    body: dict[str, Any] = {"display_name": display_name, "fields": fields}
    if section_path is not None:
        body["section_path"] = section_path

    resp = httpx.post(f"{_base(base_url)}/tables", headers=_headers(token, True),
                      json=body, timeout=60)
    _raise_for(resp)
    result = resp.json()

    # ★ 二次 GET 驗證：確認表確實出現在租戶表清單中
    physical = result.get("physical_name")
    if physical:
        tables = list_tables(base_url, token)
        if not any(t.get("physical_name") == physical for t in tables):
            raise RuntimeError(f"建表驗證失敗：{physical} 未出現在租戶表清單中")
    return result


def add_field(base_url: str, token: str, key: str, field: dict) -> dict:
    """加欄。key = 表實體名。需 system.admin。"""
    import httpx
    validate_field_spec(field)
    resp = httpx.post(f"{_base(base_url)}/tables/{key}/fields",
                      headers=_headers(token, True), json=field, timeout=60)
    _raise_for(resp)
    return resp.json()


def update_field(base_url: str, token: str, key: str, field_key: str,
                 updates: dict) -> dict:
    """改欄。需 system.admin。

    只送真正要改的鍵——未帶的鍵不動。
    可改：display_name / is_required / is_unique / default_value /
          options（僅 select）/ is_public_readable。
    **實體名、型別、relation 目標建立後不可變**，payload 帶到即 422。
    """
    import httpx
    forbidden = {"physical_name", "field_type", "target_table_id", "target_erp_key"}
    bad = forbidden & set(updates)
    if bad:
        raise ValueError(f"這些屬性建立後不可變，不可出現在 payload：{sorted(bad)}")
    resp = httpx.patch(f"{_base(base_url)}/tables/{key}/fields/{field_key}",
                       headers=_headers(token, True), json=updates, timeout=60)
    _raise_for(resp)
    return resp.json()


# ── 兩段式刪除（需 system.admin）──────────────────────────────────────

def get_table_impact(base_url: str, token: str, key: str) -> dict:
    """刪表影響預覽（兩段式第一段）。回傳記錄數、欄位非空值統計、關聯依賴。"""
    import httpx
    resp = httpx.get(f"{_base(base_url)}/tables/{key}/impact",
                     headers=_headers(token), timeout=30)
    _raise_for(resp, scope="data")
    return resp.json()


def get_field_impact(base_url: str, token: str, key: str, field_key: str) -> dict:
    """刪欄影響預覽（兩段式第一段）。"""
    import httpx
    resp = httpx.get(f"{_base(base_url)}/tables/{key}/fields/{field_key}/impact",
                     headers=_headers(token), timeout=30)
    _raise_for(resp, scope="data")
    return resp.json()


def delete_table(base_url: str, token: str, key: str, confirm: str) -> bool:
    """刪表（兩段式第二段）。**不可逆**。

    confirm 送出為 query 參數，必須等於表的**實體名**（不是顯示名）。

    ⚠️ 本地的 confirm 比對**只擋得住「誤傳顯示名」，不是授權閘**——
    key 與 confirm 由同一個呼叫端提供，湊出相等值零成本。真正的比對在後端。
    「刪除前必須先讓人看過影響預覽」是**流程紀律**（SKILL.md 的閘門），
    程式碼層擋不住，別把這行 if 當成安全機制。
    """
    import httpx
    if confirm != key:
        raise ValueError(
            f"confirm 必須等於表實體名 '{key}'（收到 '{confirm}'）。"
            "顯示名不可作為確認值。"
        )
    resp = httpx.delete(f"{_base(base_url)}/tables/{key}",
                        headers=_headers(token), params={"confirm": confirm}, timeout=60)
    _raise_for(resp)
    # ★ 二次 GET 驗證
    tables = list_tables(base_url, token)
    if any(t.get("physical_name") == key for t in tables):
        raise RuntimeError(f"刪表驗證失敗：{key} 仍存在於租戶表清單中")
    return True


def delete_field(base_url: str, token: str, key: str, field_key: str,
                 confirm: str) -> bool:
    """刪欄（兩段式第二段）。confirm 必須等於**欄位實體名**，走 query 參數。

    同 delete_table：本地比對只擋誤傳顯示名，不是授權閘。
    """
    import httpx
    if confirm != field_key:
        raise ValueError(
            f"confirm 必須等於欄位實體名 '{field_key}'（收到 '{confirm}'）"
        )
    resp = httpx.delete(f"{_base(base_url)}/tables/{key}/fields/{field_key}",
                        headers=_headers(token), params={"confirm": confirm}, timeout=60)
    _raise_for(resp)
    # ★ 二次 GET 驗證：確認欄位確實從表結構消失
    table = get_table(base_url, token, key)
    if any(f.get("physical_name") == field_key for f in (table.get("fields") or [])):
        raise RuntimeError(f"刪欄驗證失敗：{field_key} 仍存在於 {key} 的欄位清單中")
    return True


# ── 記錄（需 builder.access）──────────────────────────────────────────

def query_records(base_url: str, token: str, key: str, *,
                  filters: Optional[list[dict]] = None, sort: Optional[str] = None,
                  page: int = 1, page_size: int = 25) -> dict:
    """查記錄。回傳分頁信封 {items, total, page, page_size}。

    filters 元素：{"field": <實體名>, "op": "eq|contains|gte|lte", "value": ...}（多條 AND）
    sort：<實體名> 升冪，或 -<實體名> 降冪，單欄
    """
    import httpx
    import json as _json
    params: dict[str, Any] = {"page": page, "page_size": page_size}
    if sort:
        params["sort"] = sort
    if filters:
        params["filters"] = _json.dumps(filters, ensure_ascii=False)
    resp = httpx.get(f"{_base(base_url)}/tables/{key}/records",
                     headers=_headers(token), params=params, timeout=30)
    _raise_for(resp, scope="data")
    return resp.json()


def insert_record(base_url: str, token: str, key: str, data: dict) -> dict:
    """新增記錄。data 的鍵是欄位**實體名**。"""
    import httpx
    resp = httpx.post(f"{_base(base_url)}/tables/{key}/records",
                      headers=_headers(token, True), json={"data": data}, timeout=30)
    _raise_for(resp, scope="data")
    return resp.json()


def update_record(base_url: str, token: str, key: str, record_id: str, data: dict) -> dict:
    """更新記錄。只更新帶到的欄位。"""
    import httpx
    resp = httpx.patch(f"{_base(base_url)}/tables/{key}/records/{record_id}",
                       headers=_headers(token, True), json={"data": data}, timeout=30)
    _raise_for(resp, scope="data")
    return resp.json()


def delete_record(base_url: str, token: str, key: str, record_id: str) -> bool:
    """刪除單筆記錄（記錄刪除不需兩段式確認）。"""
    import httpx
    resp = httpx.delete(f"{_base(base_url)}/tables/{key}/records/{record_id}",
                        headers=_headers(token), timeout=30)
    _raise_for(resp, scope="data")
    return True


# ── 報告 ──────────────────────────────────────────────────────────────

def format_tables_report(tables: Optional[list]) -> str:
    """把租戶自建表清單格式化為 Phase 0 盤點報告的一段。

    tables 為 None＝**盤點失敗**（與「租戶真的沒有表」是兩回事，不可混為一談）。
    """
    if tables is None:
        return ("🗄️ 租戶自建表\n"
                "  ⚠️ 盤點失敗——**未能確認**租戶是否已有表。\n"
                "  不可據此建表：可能已存在語意相同的表，重複建會讓資料分裂。\n"
                "  請先排除權限或連線問題，重跑盤點。")

    lines = ["🗄️ 租戶自建表（資料中心，跨 app 共用）"]
    if not tables:
        lines.append("  盤點成功，租戶目前沒有任何自建表")
        return "\n".join(lines)
    lines.append(f"  共 {len(tables)} 張")
    for t in tables:
        fields = t.get("fields") or []
        biz = [f for f in fields if not f.get("is_system")]
        lines.append(f"  {t.get('physical_name')} — {t.get('display_name')} "
                     f"（{len(biz)} 個業務欄位，id={t.get('id')}）")
        for f in biz:
            marks = []
            if f.get("is_required"):
                marks.append("必填")
            if f.get("is_unique"):
                marks.append("唯一")
            if f.get("target_table_id"):
                marks.append("→自建表(真FK)")
            if f.get("target_erp_key"):
                marks.append(f"→ERP:{f['target_erp_key']}(軟關聯)")
            suffix = f" [{', '.join(marks)}]" if marks else ""
            lines.append(f"    {f.get('physical_name')}: {f.get('field_type')}{suffix}"
                         f" — {f.get('display_name')}")
    return "\n".join(lines)


def format_create_spec(display_name: str, fields: list[dict]) -> str:
    """PermissionDenied(needs="system.admin") 降級時，
    輸出讓用戶照抄到資料中心 UI 的建表規格。

    這是錯誤處理路徑——欄位鍵一律用 .get()，不可在這裡再拋例外。
    """
    lines = [
        "請到資料中心 UI 建立這張表（你的帳號需要租戶管理員權限）：",
        "",
        f"表顯示名：{display_name}",
        "",
        "| 欄位顯示名 | 型別 | 必填 | 唯一 | 備註 |",
        "|---|---|---|---|---|",
    ]
    for f in fields:
        note = ""
        if f.get("options"):
            note = "選項：" + "／".join(str(o) for o in f["options"])
        elif f.get("target_table_id"):
            note = "關聯 → 自建表"
        elif f.get("target_erp_key"):
            note = f"關聯 → 預設表 {f['target_erp_key']}"
        lines.append(
            f"| {f.get('display_name', '?')} | {f.get('field_type', '?')} | "
            f"{'✓' if f.get('is_required') else ''} | "
            f"{'✓' if f.get('is_unique') else ''} | {note} |"
        )
    lines += [
        "",
        "（id／created_at／updated_at 由系統自動建立，不用自己加）",
        "建好後告訴我，我會用 list_tables() 驗收再繼續。",
    ]
    return "\n".join(lines)
