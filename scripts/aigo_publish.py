"""AI GO Custom App 發布工具"""
from __future__ import annotations

import ast
import json
from typing import Any

# 發布端點的三個 query 參數（皆選填、預設 false；2026-09-09 prod 實打皆生效）。
# 預設一個都不帶：409 回來先讀 code，帶哪一個是用戶的決定，不由腳本自動加。
PUBLISH_CONFIRM_PARAMS = ("confirm_removal", "confirm_egress_gaps", "auto_rollback")

# 起手式自帶、宣告／呼叫 openai 的兩個檔（與 aigo_sync.STARTER_EGRESS_LEFTOVERS 同一份）
_STARTER_LEFTOVERS = ("_template.json", "actions/summarize_leads.py")


# ---------------------------------------------------------------------------
# 發布前的 egress 預檢（純函式部分不打網路，可離線測）
# ---------------------------------------------------------------------------

def scan_literal_egress_slugs(vfs: dict) -> tuple[dict[str, list[str]], list[str]]:
    """掃 `actions/*.py` 的字面 `ctx.http.call(<slug>, …)`。

    回 (slug → 出現位置清單, 動態呼叫位置清單)。判定複刻平台 publish_guard.scan_egress_slugs：
    AST 走訪、呼叫形狀 Name(ctx).http.call、第一參數非字面字串算動態（閘門掃不到、只能靠宣告）。
    `actions/_shared/` 是共用模組不是 action，但平台一樣掃 actions/ 底下所有 .py，這裡照掃。
    """
    literal: dict[str, list[str]] = {}
    dynamic: list[str] = []
    for path, code in (vfs or {}).items():
        if not (path.startswith("actions/") and path.endswith(".py")) or not isinstance(code, str):
            continue
        try:
            tree = ast.parse(code)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            if not (isinstance(f, ast.Attribute) and f.attr == "call"
                    and isinstance(f.value, ast.Attribute) and f.value.attr == "http"
                    and isinstance(f.value.value, ast.Name) and f.value.value.id == "ctx"):
                continue
            first = node.args[0] if node.args else None
            where = f"{path}:{node.lineno}"
            if isinstance(first, ast.Constant) and isinstance(first.value, str) and first.value:
                literal.setdefault(first.value, []).append(where)
            else:
                dynamic.append(where)
    return literal, dynamic


def declared_egress_slugs(vfs: dict) -> set[str]:
    """讀 `_template.json` 的 `required_egress`（dict 的 key 或 string[]）；沒有或壞掉回空集合。"""
    raw = (vfs or {}).get("_template.json")
    if not isinstance(raw, str):
        return set()
    try:
        meta = json.loads(raw)
    except ValueError:
        return set()
    req = meta.get("required_egress") if isinstance(meta, dict) else None
    if isinstance(req, dict):
        return {k for k in req if isinstance(k, str) and k}
    if isinstance(req, list):
        return {s for s in req if isinstance(s, str) and s}
    return set()


def available_services(available: dict | None) -> list[dict]:
    """取 available-egress-services 的 `services`（租戶有、且本 App 看得到的外部服務）。

    只認 `services` 這個 key：舊版寫法「回應裡第一個 list」會在缺 key 時撈到
    `authorized_egress_service_ids`，那是另一種形狀的清單（沒有 slug），撈到只會靜靜算錯。
    """
    if not isinstance(available, dict):
        return []
    services = available.get("services")
    if not isinstance(services, list):
        return []
    return [s for s in services if isinstance(s, dict)]


def authorized_service_ids(available: dict | None) -> set[str]:
    """取「已授權給本 App」的 EgressService id 集合。

    ★ 元素是 **dict**，不是字串——2026-09-09 兩個租戶實打（abeco／ckleegarden）皆為
    `[{"service_id": "<uuid>"}]`，與 `PUT authorized-egress-services` 的 body
    `{"services": [{"service_id": …}]}` 同形。直接 `str(x)` 會得到 `"{'service_id': …}"`，
    永遠對不上 `services[].id` → **每個 slug 都被誤判成 gap**（1.39.0 以前的行為）。

    空清單是 `[]`，看不出元素形狀，所以純字串元素也一併吃下；
    key 名同時認 `service_id`／`id`／`egress_service_id`，平台換寫法不會又靜靜算錯。
    """
    if not isinstance(available, dict):
        return set()
    ids: set[str] = set()
    for item in available.get("authorized_egress_service_ids") or []:
        if isinstance(item, dict):
            for key in ("service_id", "id", "egress_service_id"):
                v = item.get(key)
                if isinstance(v, str) and v:
                    ids.add(v)
                    break
        elif isinstance(item, str) and item:
            ids.add(item)
    return ids


def egress_preflight(vfs: dict, available: dict | None = None) -> dict:
    """比對「宣告」「程式碼實際用到」「本 App 已授權」三份 egress slug。純函式。

    `available` 是 `GET /builder/apps/{id}/available-egress-services` 的回應
    （`{services: [{id, slug, is_active, …}], authorized_egress_service_ids: [{"service_id": …}]}`）；
    不給就只比前兩份。授權清單的元素形狀見 `authorized_service_ids()`。

    回傳：
    - needed        閘門會檢查的全集 = declared ∪ literal
    - gaps          needed 裡沒授權給本 App 的（有 available 才算得出）——發布會 409 EGRESS_NOT_READY
    - declared_only 宣告了但程式碼沒用到
    - leftovers     起手式殘留檔（`_template.json` 宣告 openai／示範 action）——與需求無關就兩個一起刪
    """
    declared = declared_egress_slugs(vfs)
    literal, dynamic = scan_literal_egress_slugs(vfs)
    needed = sorted(declared | set(literal))

    authorized: set[str] | None = None
    missing_service: list[str] = []
    if available is not None:
        by_slug = {s.get("slug"): s for s in available_services(available) if s.get("slug")}
        auth_ids = authorized_service_ids(available)
        authorized = {slug for slug, s in by_slug.items() if str(s.get("id")) in auth_ids}
        missing_service = [s for s in needed if s not in by_slug]

    gaps = [s for s in needed if authorized is not None and s not in authorized]
    leftovers = [p for p in _STARTER_LEFTOVERS if p in (vfs or {})]
    if leftovers and "openai" not in needed:
        leftovers = []  # 已經清到不再宣告／呼叫 openai，就不是殘留
    return {
        "declared": sorted(declared),
        "literal": {k: v for k, v in sorted(literal.items())},
        "dynamic": dynamic,
        "needed": needed,
        "authorized": sorted(authorized) if authorized is not None else None,
        "missing_service": missing_service,
        "gaps": gaps,
        "declared_only": sorted(declared - set(literal)),
        "leftovers": leftovers,
    }


def format_egress_preflight(report: dict) -> str:
    lines: list[str] = []
    if report["literal"]:
        used = ", ".join(f"{s}（{', '.join(w)}）" for s, w in report["literal"].items())
        lines.append(f"→ action 程式碼字面呼叫的 egress slug：{used}")
    if report["declared"]:
        lines.append(f"→ _template.json 宣告的 required_egress：{', '.join(report['declared'])}")
    if report["dynamic"]:
        lines.append(f"→ 動態 slug（閘門掃不到、只能靠宣告）：{', '.join(report['dynamic'])}")
    if report["leftovers"]:
        lines.append(f"⚠️  起手式殘留：{', '.join(report['leftovers'])}——與需求無關就兩個一起刪"
                     "（aigo_sync.delete_remote_files；只刪 action 仍擋，README／manifest 不用管）")
    if report["gaps"]:
        ms = set(report["missing_service"])
        parts = [f"{s}（租戶沒有這個外部服務）" if s in ms else f"{s}（有服務、未授權給本 App）" for s in report["gaps"]]
        lines.append(f"❌ 發布會 409 EGRESS_NOT_READY：{'；'.join(parts)}。"
                     "真的要用 → 建立／授權外部服務（dev-guide §25.2）；用不到 → 清掉宣告與呼叫，"
                     "或帶 confirm_egress_gaps=True（發布後呼叫該 slug 必失敗）")
    elif report["authorized"] is not None and report["needed"]:
        lines.append(f"✅ egress 預檢：{', '.join(report['needed'])} 都已授權給本 App")
    elif not report["needed"]:
        lines.append("→ egress 預檢：沒有宣告、沒有對外呼叫")
    return "\n".join(lines)


def fetch_available_egress(base_url: str, token: str, app_id: str) -> dict | None:
    """GET available-egress-services；拿不到（權限不足等）回 None，預檢降級為只比宣告與程式碼。"""
    import httpx
    headers = {"Authorization": f"Bearer {token}"}
    try:
        resp = httpx.get(f"{base_url}/api/v1/builder/apps/{app_id}/available-egress-services",
                         headers=headers, timeout=30)
        if resp.status_code >= 400:
            return None
        data = resp.json()
        return data if isinstance(data, dict) else None
    except (httpx.HTTPError, ValueError):
        return None


# ---------------------------------------------------------------------------
# 發布
# ---------------------------------------------------------------------------

def format_publish_409(detail: Any) -> str:
    """把 409 的 code 翻成下一步。不自動帶 confirm——那是用戶的決定。"""
    code = detail.get("code") if isinstance(detail, dict) else None
    if code == "ACTION_REMOVAL":
        removed = detail.get("removed_actions") or []
        return (f"409 ACTION_REMOVAL：本次發布會移除既有 action {removed}（綁在上面的 webhook／排程會斷）。"
                "用戶確認要移除 → publish_app(..., confirm_removal=True)；不是 → 把該檔放回再發布")
    if code == "EGRESS_NOT_READY":
        gaps = detail.get("gaps") or []
        rows = "\n".join(f"   - {g.get('kind')} {g.get('slug') or g.get('key')}：{g.get('fix')}" for g in gaps if isinstance(g, dict))
        return ("409 EGRESS_NOT_READY：外部服務／金鑰未到位——\n" + rows +
                "\n   真的要用 → 照上面的 fix 建立／授權（dev-guide §25.2）；用不到 → 清掉 _template.json 的宣告與呼叫它的 action"
                "（起手式殘留見 dev-guide §26.2），或 publish_app(..., confirm_egress_gaps=True)（發布後呼叫該 slug 必失敗）")
    return f"409：{detail}"


def publish_app(base_url: str, token: str, app_id: str, *,
                confirm_removal: bool = False, confirm_egress_gaps: bool = False,
                auto_rollback: bool = False, skip_preflight: bool = False) -> dict:
    """發布 App。

    - POST 前先跑 egress 預檢（宣告 ∪ 字面 slug 對照已授權清單），起手式殘留當場點名
    - 三個 query 參數預設都不帶；409 回來把 code 翻成下一步後 raise，不自動重試
    - auto_rollback=True 時 422 代表已退回上一版
    - POST 後二次 GET 驗證 status == published
    """
    import httpx
    from aigo_auth import get_app_info
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    if not skip_preflight:
        info = get_app_info(base_url, token, app_id)
        report = egress_preflight(info.get("vfs_state") or {}, fetch_available_egress(base_url, token, app_id))
        print(format_egress_preflight(report))
        if report["gaps"] and not confirm_egress_gaps:
            raise RuntimeError("發布中止：egress 預檢有缺口（見上）。補設定、清殘留，或明確帶 confirm_egress_gaps=True")

    flags = {"confirm_removal": confirm_removal, "confirm_egress_gaps": confirm_egress_gaps,
             "auto_rollback": auto_rollback}
    params = {k: "true" for k, v in flags.items() if v}
    if params:
        print(f"→ 發布參數：{', '.join(params)}")

    resp = httpx.post(f"{base_url}/api/v1/builder/apps/{app_id}/publish",
                      headers=headers, params=params, json={"published_assets": {}}, timeout=60)
    if resp.status_code == 409:
        try:
            detail = resp.json().get("detail")
        except ValueError:
            detail = resp.text[:500]
        raise RuntimeError(format_publish_409(detail))
    if resp.status_code == 422 and auto_rollback:
        raise RuntimeError(f"auto_rollback：發布後編譯驗證失敗，平台已退回上一版（422）。{resp.text[:500]}")
    resp.raise_for_status()
    # ★ 二次 GET 驗證
    verify = get_app_info(base_url, token, app_id)
    if verify.get('status') != 'published':
        raise RuntimeError(f"發布驗證失敗：status={verify.get('status')}，預期 published")
    return resp.json()


def check_publish_status(base_url: str, token: str, app_id: str) -> str:
    """檢查發布狀態"""
    import httpx
    headers = {"Authorization": f"Bearer {token}"}
    resp = httpx.get(f"{base_url}/api/v1/builder/apps/{app_id}", headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json().get("status", "unknown")


def full_deploy(base_url: str, token: str, app_id: str, slug: str, project_path: str,
                **publish_kwargs: Any) -> dict:
    """完整部署流程：sync → compile → publish（publish_kwargs 透傳給 publish_app）"""
    from aigo_sync import read_local_files, get_remote_vfs, sync_to_cloud
    from aigo_compile import compile_app

    result: dict[str, Any] = {"sync": None, "compile": None, "publish": None}

    # 0. 動手前印目標——打錯 app 的代價是把 VFS 同步到別人的 app（1.22.0）
    from urllib.parse import urlsplit
    from aigo_auth import get_app_info as _info
    remote = _info(base_url, token, app_id)
    print(f"→ 目標：{remote.get('name') or slug}  ({str(remote.get('id') or app_id)[:8]})  @ {urlsplit(base_url).hostname}")

    # 1. 同步
    local_files = read_local_files(project_path)
    _, version = get_remote_vfs(base_url, token, app_id)
    result["sync"] = sync_to_cloud(base_url, token, app_id, local_files, version)

    # 2. 編譯
    compile_result = compile_app(base_url, token, slug)
    result["compile"] = {"success": compile_result.get("success", False)}
    if not compile_result.get("success"):
        result["compile"]["error"] = compile_result.get("error", "未知錯誤")
        return result
    # ★ 二次驗證：確認編譯成功
    if not result["compile"]["success"]:
        raise RuntimeError("部署流程中止：編譯結果驗證失敗")

    # 3. 發布
    result["publish"] = publish_app(base_url, token, app_id, **publish_kwargs)
    # ★ 二次 GET 驗證：確認發布狀態
    from aigo_auth import get_app_info
    verify = get_app_info(base_url, token, app_id)
    if verify.get('status') != 'published':
        raise RuntimeError(f"完整部署驗證失敗：status={verify.get('status')}，預期 published")
    return result


# ---------------------------------------------------------------------------
# 離線自測：`python scripts/aigo_publish.py selftest`（不打網路、只用標準庫）
# ---------------------------------------------------------------------------

# 2026-09-09 實打回應的縮影：`authorized_egress_service_ids` 的元素是
# `{"service_id": …}`（abeco `evidence/egress_final.json` 的 verify、
# ckleegarden `GET available-egress-services` 皆同形）。
_SAMPLE_AVAILABLE = {
    "services": [
        {"id": "c527c1ce-9f2c-4f14-aab0-55c5283ddc99", "name": "OpenAI",
         "slug": "openai", "base_url": "https://api.openai.com",
         "auth_type": "none", "is_active": True},
        {"id": "f55d0c24-11ca-4944-89b7-957975bb8287", "name": "OpenRouter",
         "slug": "openrouter", "base_url": "https://openrouter.ai",
         "auth_type": "none", "is_active": True},
    ],
    "authorized_egress_service_ids": [
        {"service_id": "f55d0c24-11ca-4944-89b7-957975bb8287"},
        {"service_id": "c527c1ce-9f2c-4f14-aab0-55c5283ddc99"},
    ],
}

_SAMPLE_VFS = {
    "_template.json": json.dumps({"required_egress": {"openai": {}}}),
    "actions/summarize_leads.py": "def run(ctx):\n    return ctx.http.call('openai', '/v1/x')\n",
    "actions/po_extract.py": (
        "def run(ctx):\n"
        "    slug = ctx.params['slug']\n"
        "    ctx.http.call(slug, '/dyn')\n"
        "    return ctx.http.call('openrouter', '/api/v1/chat/completions')\n"
    ),
}


def _selftest() -> int:
    fails: list[str] = []

    def check(name: str, got: Any, want: Any) -> None:
        if got != want:
            fails.append(f"{name}\n     got : {got!r}\n     want: {want!r}")

    # 1) 授權清單：dict 元素（實際形狀）、字串元素（防未來改回）、混用、空、壞資料
    check("dict 元素", authorized_service_ids(_SAMPLE_AVAILABLE),
          {"f55d0c24-11ca-4944-89b7-957975bb8287", "c527c1ce-9f2c-4f14-aab0-55c5283ddc99"})
    check("字串元素", authorized_service_ids({"authorized_egress_service_ids": ["a", "b"]}), {"a", "b"})
    check("混用與別名 key", authorized_service_ids(
        {"authorized_egress_service_ids": ["a", {"id": "b"}, {"egress_service_id": "c"}]}), {"a", "b", "c"})
    check("空清單", authorized_service_ids({"authorized_egress_service_ids": []}), set())
    check("欄位缺席", authorized_service_ids({}), set())
    check("不是 dict", authorized_service_ids(None), set())
    check("壞元素略過", authorized_service_ids({"authorized_egress_service_ids": [{"x": 1}, 3, None, ""]}), set())

    # 2) services 只認 services key，不會撈到授權清單當服務用
    check("services 缺席", available_services({"authorized_egress_service_ids": [{"service_id": "a"}]}), [])
    check("services 正常", [s["slug"] for s in available_services(_SAMPLE_AVAILABLE)], ["openai", "openrouter"])

    # 3) ★ 迴歸本體：兩個都已授權 → gaps 必須是空的（修正前這裡是 ['openai', 'openrouter']）
    rep = egress_preflight(_SAMPLE_VFS, _SAMPLE_AVAILABLE)
    check("needed", rep["needed"], ["openai", "openrouter"])
    check("authorized", rep["authorized"], ["openai", "openrouter"])
    check("gaps 應為空", rep["gaps"], [])
    check("動態呼叫仍點名", len(rep["dynamic"]), 1)
    check("起手式殘留仍點名", rep["leftovers"], ["_template.json", "actions/summarize_leads.py"])
    # 起手式的示範 action 自己就字面呼叫 openai，所以宣告 ⊆ 字面 → declared_only 是空的
    check("declared_only", rep["declared_only"], [])
    check("宣告了但沒人呼叫 → declared_only",
          egress_preflight({"_template.json": json.dumps({"required_egress": ["stripe"]})})["declared_only"],
          ["stripe"])

    # 4) 真的沒授權時仍要點名（避免修過頭變成永遠不報 gap）
    none_auth = {**_SAMPLE_AVAILABLE, "authorized_egress_service_ids": []}
    check("零授權 → 全是 gap", egress_preflight(_SAMPLE_VFS, none_auth)["gaps"], ["openai", "openrouter"])
    only_openai = {**_SAMPLE_AVAILABLE,
                   "authorized_egress_service_ids": [{"service_id": "c527c1ce-9f2c-4f14-aab0-55c5283ddc99"}]}
    check("半授權 → 只點沒授的", egress_preflight(_SAMPLE_VFS, only_openai)["gaps"], ["openrouter"])

    # 5) 租戶根本沒建這個服務 → 算 missing_service，訊息要分辨得出來
    no_service = {"services": [], "authorized_egress_service_ids": []}
    rep3 = egress_preflight(_SAMPLE_VFS, no_service)
    check("missing_service", rep3["missing_service"], ["openai", "openrouter"])
    assert "租戶沒有這個外部服務" in format_egress_preflight(rep3)

    # 6) 不給 available → 降級，不算 gaps
    rep4 = egress_preflight(_SAMPLE_VFS)
    check("降級 authorized", rep4["authorized"], None)
    check("降級 gaps", rep4["gaps"], [])

    if fails:
        print("❌ selftest 失敗 %d 項：" % len(fails))
        for f in fails:
            print("   - " + f)
        return 1
    print("✅ aigo_publish selftest 全數通過（egress 預檢，離線）")
    return 0


if __name__ == "__main__":
    import sys
    # Windows 主控台預設 cp950，訊息裡的 ✅／❌ 會炸 UnicodeEncodeError
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        raise SystemExit(_selftest())
    print("用法：python aigo_publish.py selftest")
