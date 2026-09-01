"""AI GO Custom App 現有程式碼 Review 工具"""
import json
import re
from typing import Any

# SDK 保護清單（必定存在且不可修改）
SDK_FILES = {"src/api.ts", "src/db.ts", "src/action.ts"}
# 已知 Runtime 注入檔模式（不一定全部存在，依 App 狀態而定）
KNOWN_INJECTED_PATHS = {"src/data.json", "src/db.json", "src/actions.json"}
# 保護檔集合（同步/腳手架時應跳過的路徑）
PROTECTED_FILES = SDK_FILES | KNOWN_INJECTED_PATHS
# 相容舊引用
INJECTED_FILES = KNOWN_INJECTED_PATHS


def review_app(base_url: str, token: str, app_id: str) -> dict:
    """取得 App 資訊並執行完整 Review（含租戶級資源盤點）

    VFS 分析只看得到 app 自己的東西。自建表與排程是**租戶級**資源、不在 VFS 裡，
    必須另外打 API 盤點——這是 SKILL.md Phase 0 步驟 6／7 的強制項。
    """
    import httpx
    headers = {"Authorization": f"Bearer {token}"}
    resp = httpx.get(f"{base_url}/api/v1/builder/apps/{app_id}", headers=headers, timeout=30)
    resp.raise_for_status()
    app_info = resp.json()
    analysis = analyze_vfs(app_info.get("vfs_state", {}))
    return {
        "app_info": app_info,
        "analysis": analysis,
        "custom_tables": fetch_custom_tables(base_url, token),
        "crons": fetch_app_crons(base_url, token, app_id),
    }


def fetch_custom_tables(base_url: str, token: str):
    """盤點租戶既有自建表（★ Phase 0 步驟 6，建表前不可跳過）。

    回傳 list＝盤點成功（空 list＝租戶真的沒有表）；
    回傳 **None＝盤點失敗**（權限不足／連線問題）。

    這兩者必須可區分：把失敗當成「沒有表」會導致重複建表、
    同一份業務資料分裂成兩張——正是本步驟要防的事。
    """
    import httpx
    try:
        resp = httpx.get(f"{base_url}/api/v1/data-center/tables",
                         headers={"Authorization": f"Bearer {token}"}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else None
    except (httpx.HTTPError, ValueError):
        return None


def fetch_app_crons(base_url: str, token: str, app_id: str = "") -> list[dict]:
    """盤點既有 App 排程（★ Phase 0 步驟 7）。

    回傳 list＝成功；**None＝盤點失敗**（多半是缺 settings.read）。
    republish 或改動 action 名稱前必須知道有哪些排程綁在上面——
    action 消失連續 2 次會讓排程被自動暫停，且不會自動恢復。
    """
    import httpx
    try:
        resp = httpx.get(f"{base_url}/api/v1/app-crons",
                         headers={"Authorization": f"Bearer {token}"}, timeout=30)
        resp.raise_for_status()
        crons = resp.json()
        if isinstance(crons, dict):
            crons = crons.get("items", [])
        if not isinstance(crons, list):
            return None
        if app_id:
            crons = [c for c in crons if str(c.get("app_id")) == str(app_id)]
        return crons
    except (httpx.HTTPError, ValueError):
        return None


def analyze_vfs(vfs_state: dict) -> dict:
    """分析 VFS 結構"""
    files_info = []
    for path, content in sorted(vfs_state.items()):
        # 動態分類：INJ 標籤只在路徑確實存在於 VFS 時才套用
        if path in SDK_FILES:
            tag = "[SDK]"
        elif path in KNOWN_INJECTED_PATHS:
            tag = "[INJ]"
        else:
            tag = "[APP]"
        files_info.append({"path": path, "size": len(content), "tag": tag})

    # 解析路由
    routes = []
    app_tsx = vfs_state.get("src/App.tsx", "")
    for m in re.finditer(r'path=["\'](/[^"\']*)["\']', app_tsx):
        routes.append(m.group(1))
    for m in re.finditer(r'path=["\'](\*)["\']', app_tsx):
        routes.append(m.group(1))

    # 解析 manifest
    pages = []
    manifest_str = vfs_state.get("src/pages/_manifest.json", "")
    if manifest_str:
        try:
            manifest = json.loads(manifest_str)
            pages = manifest.get("pages", [])
        except json.JSONDecodeError:
            pass

    # Legacy CustomObject 偵測（已退場的前代模型，見 CONTEXT.md）
    legacy = detect_legacy_custom_object(vfs_state)

    # builder.access 破口偵測（前端直呼自建表 SDK，規則 31）
    dc_frontend = detect_data_center_frontend_usage(vfs_state)

    # 解析 Actions（含 webhook 宣告——決定哪些 action 有對外端點）
    actions = []
    actions_manifest = vfs_state.get("actions/manifest.json", "")
    if actions_manifest:
        try:
            am = json.loads(actions_manifest)
            if isinstance(am, list):  # 舊格式容錯
                am = {x.get("name"): x for x in am if isinstance(x, dict) and x.get("name")}
            if not isinstance(am, dict):
                am = {}
            for name, info in am.items():
                info = info if isinstance(info, dict) else {}
                is_default_hook = name == "receive_webhook"
                actions.append({
                    "name": name,
                    "description": info.get("description", ""),
                    "timeout_ms": info.get("timeout_ms"),
                    "is_enabled": info.get("is_enabled", True),
                    # receive_webhook 是歷史預設端點，無需宣告旗標
                    "webhook": bool(info.get("webhook")) or is_default_hook,
                })
        except json.JSONDecodeError:
            pass

    # 解析 Data Reference（db.json）
    data_references = []
    db_json_str = vfs_state.get("src/db.json", "")
    if db_json_str and db_json_str != "{}":
        try:
            db_json = json.loads(db_json_str)
            for table_key, info in db_json.items():
                columns = info.get("columns", [])
                col_names = [c.get("name", "") for c in columns]
                has_custom_data = "custom_data" in col_names
                # 統計 app_domain 分布
                app_domains = {}
                for record in info.get("data", []):
                    cd = record.get("custom_data") or {}
                    domain = cd.get("app_domain", "_none_")
                    app_domains[domain] = app_domains.get(domain, 0) + 1
                data_references.append({
                    "table": info.get("table", table_key),
                    "permissions": info.get("permissions", []),
                    "columns_count": len(columns),
                    "columns": col_names,
                    "has_custom_data": has_custom_data,
                    "records_count": len(info.get("data", [])),
                    "app_domains": app_domains,
                })
        except json.JSONDecodeError:
            pass

    # CSS 檢查
    css_content = vfs_state.get("src/App.css", "")
    css_issues = check_css_compliance(css_content)

    # 路由類型偵測
    router_type = "HashRouter" if "HashRouter" in app_tsx else "BrowserRouter" if "BrowserRouter" in app_tsx else "none"

    return {
        "files": files_info,
        "total_files": len(files_info),
        "routes": routes,
        "router_type": router_type,
        "pages": pages,
        "legacy_custom_object": legacy,
        "data_center_frontend_usage": dc_frontend,
        "webhook_actions": [a["name"] for a in actions if a.get("webhook")],
        "data_references": data_references,
        "actions": actions,
        "css_issues": css_issues,
    }


# 前端自建表 SDK 方法（src/api.ts）。這些呼叫以「登入者身分」打 /data-center/*，
# 記錄 CRUD 掛 builder.access——internal app 的一般員工受眾執行期必 403（規則 31）。
DATA_CENTER_FRONTEND_METHODS = {
    "listTables", "queryTable", "listRows", "getRow",
    "insertRow", "updateRow", "deleteRow",
}


def detect_data_center_frontend_usage(vfs_state: dict) -> list[dict]:
    """盤點前端檔對自建表 SDK 的直接呼叫（builder.access 破口偵測，規則 31）。

    比對的是方法名字面，所以表名帶變數（SNAP_TABLE 之類）也抓得到。
    回傳 [{"path", "methods"}]；是否構成破口要配合 access_mode 判讀
    （internal＝必改；external 走 /ext/data-center 不受影響），
    判讀放在 format_review_report()。
    """
    hits = []
    for path, content in sorted(vfs_state.items()):
        if not isinstance(content, str) or path in SDK_FILES:
            continue
        if not path.endswith((".ts", ".tsx")):
            continue
        used = sorted(m for m in DATA_CENTER_FRONTEND_METHODS
                      if re.search(rf"\b{m}\s*\(", content))
        if used:
            hits.append({"path": path, "methods": used})
    return hits


def detect_legacy_custom_object(vfs_state: dict) -> dict:
    """偵測 legacy CustomObject 使用痕跡（見 CONTEXT.md）。

    CustomObject 是自建表的前身：綁 app、資料存 JSONB、沒有真實資料表。
    存量 app 的既有功能維持原樣即可運作（SDK 雙軌並存），
    但**不要往上加東西**——新資料需求一律開自建表。
    """
    signals = []

    data_json_str = vfs_state.get("src/data.json", "")
    tables = []
    if isinstance(data_json_str, str) and data_json_str.strip() not in ("", "{}"):
        try:
            data_json = json.loads(data_json_str)
            if not isinstance(data_json, dict):
                data_json = {}
            for name, info in data_json.items():
                info = info if isinstance(info, dict) else {}
                tables.append({
                    "name": name,
                    "slug": info.get("slug", ""),
                    "fields_count": len(info.get("fields", [])),
                    "records_count": len(info.get("records", [])),
                })
            if tables:
                signals.append(f"src/data.json 定義了 {len(tables)} 張 legacy 表")
        except json.JSONDecodeError:
            pass

    # 前端 SDK 的 legacy 方法
    fe_legacy = {"listRecords", "submitRecord", "updateRecord", "deleteRecord"}
    # Server Action 的 legacy 方法
    py_legacy = {"query_object", "insert_object", "update_object",
                 "remove_object", "list_custom_objects"}
    used = set()
    for path, content in vfs_state.items():
        if not isinstance(content, str):
            continue
        if path in SDK_FILES:
            continue  # SDK 本體天然含這些定義，不算使用痕跡
        if path.endswith((".ts", ".tsx")):
            used |= {m for m in fe_legacy if re.search(rf"\b{m}\s*\(", content)}
        elif path.endswith(".py"):
            used |= {m for m in py_legacy if re.search(rf"\b{m}\s*\(", content)}
    if used:
        signals.append("程式碼呼叫了 legacy 方法：" + ", ".join(sorted(used)))

    return {
        "detected": bool(signals),
        "signals": signals,
        "legacy_tables": tables,
        "legacy_calls": sorted(used),
    }


def check_css_compliance(css_content: str) -> list[str]:
    """檢查 CSS 是否符合 Shadow DOM 規範"""
    issues = []
    lines = css_content.split("\n")
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if re.match(r'^:root\s*\{', stripped) and ':host' not in stripped:
            prev_line = lines[i - 2].strip() if i >= 2 else ""
            if ':host' not in prev_line:
                issues.append(f"第 {i} 行: ':root {{' 缺少 ':host' 配對 → 應改為 ':host, :root {{'")
        if re.match(r'^html\s*\{', stripped) and ':host' not in stripped:
            prev_line = lines[i - 2].strip() if i >= 2 else ""
            if ':host' not in prev_line:
                issues.append(f"第 {i} 行: 'html {{' 缺少 ':host' 配對 → 應改為 'html, :host {{'")
    return issues


def format_review_report(app_info: dict, analysis: dict,
                         custom_tables: list = None,
                         crons: list = None) -> str:
    """格式化 Review 報告

    custom_tables / crons 是**租戶級**資源（不在 VFS 裡），
    由 review_app() 一併取回；直接呼叫本函式時可省略，
    但那樣產出的報告缺 Phase 0 步驟 6／7，不足以作為建表決策依據。
    """
    lines = []
    lines.append("═" * 55)
    lines.append("  AI GO Custom App Review 報告")
    lines.append("═" * 55)
    lines.append("")
    lines.append("📋 App 元資料")
    lines.append(f"  名稱：{app_info.get('name', 'N/A')}")
    lines.append(f"  ID：{app_info.get('id', 'N/A')}")
    lines.append(f"  Slug：{app_info.get('slug', 'N/A')}")
    lines.append(f"  狀態：{app_info.get('status', 'N/A')} | 模式：{app_info.get('access_mode', 'N/A')}")
    lines.append(f"  VFS 版本：{app_info.get('vfs_version', 'N/A')} | 檔案數：{analysis['total_files']}")
    lines.append("")
    lines.append("📁 VFS 檔案結構")
    for f in analysis["files"]:
        lines.append(f"  {f['tag']} {f['path']} ({f['size']:,} chars)")
    lines.append("")
    if analysis["routes"]:
        lines.append(f"🗺️ 路由結構（{analysis['router_type']}，{len(analysis['routes'])} 條路由）")
        for r in analysis["routes"]:
            lines.append(f"  {r}")
        lines.append("")
    legacy = analysis.get("legacy_custom_object") or {}
    if legacy.get("detected"):
        lines.append("⚠️ 偵測到 legacy CustomObject（已退場的前代模型）")
        for s in legacy["signals"]:
            lines.append(f"  {s}")
        for lt in legacy.get("legacy_tables", []):
            lines.append(f"    {lt['slug']} ({lt['fields_count']} 欄位, "
                         f"{lt['records_count']} 記錄) — {lt['name']}")
        lines.append("  → 存量功能維持原樣即可運作，但**不要往上加東西**；")
        lines.append("    新資料需求一律開自建表（見 CONTEXT.md / data-center.md）")
        lines.append("")
    dc_frontend = analysis.get("data_center_frontend_usage") or []
    access_mode = app_info.get("access_mode", "")
    legacy_fe = {"listRecords", "submitRecord", "updateRecord", "deleteRecord"}
    legacy_fe_used = sorted(legacy_fe & set(legacy.get("legacy_calls", [])))
    if dc_frontend and access_mode == "external":
        lines.append(f"ℹ️ 前端直呼自建表 SDK（{len(dc_frontend)} 檔）——external app 走"
                     " /ext/data-center，不受 builder.access 閘影響")
        for hit in dc_frontend:
            lines.append(f"    {hit['path']} — {', '.join(hit['methods'])}")
        lines.append("")
    elif dc_frontend or (legacy_fe_used and access_mode != "external"):
        lines.append("🚨 builder.access 破口：前端以登入者身分直打資料端點（必改）")
        lines.append("  無 builder.access 的一般員工執行期必 403，且開發帳號測不出此問題。")
        lines.append("  修法：包 Server Action（ctx.db.*）＋前端 runAction，並在 action 內")
        lines.append("  補授權分流 → data-center.md §7.5、SKILL.md 規則 31")
        for hit in dc_frontend:
            lines.append(f"    {hit['path']} — {', '.join(hit['methods'])}")
        if legacy_fe_used:
            lines.append("  ⚠️ 含 legacy CustomObject 前端方法（走 /data/objects/*，"
                         f"掛同一道閘）：{', '.join(legacy_fe_used)}")
        lines.append("")
    if analysis["actions"]:
        lines.append(f"⚡ Server Actions（{len(analysis['actions'])} 個）")
        for a in analysis["actions"]:
            marks = []
            if a.get("webhook"):
                marks.append("🌐 webhook 端點")
            if a.get("is_enabled") is False:
                marks.append("已停用")
            if a.get("timeout_ms"):
                marks.append(f"timeout {a['timeout_ms']}ms")
            suffix = f" [{', '.join(marks)}]" if marks else ""
            lines.append(f"  {a['name']}{suffix} — {a['description']}")
        if analysis.get("webhook_actions"):
            lines.append("  註：webhook 端點以**最近一次發布的快照**為準，"
                         "改 manifest 必須 republish 才生效")
        lines.append("")
    if analysis.get("data_references"):
        lines.append(f"🗃️ Data Reference / 預設表（{len(analysis['data_references'])} 張）")
        for dr in analysis["data_references"]:
            perms = ", ".join(dr["permissions"]) if dr["permissions"] else "N/A"
            cd_mark = " ★ 含 custom_data" if dr["has_custom_data"] else ""
            lines.append(f"  {dr['table']} ({dr['columns_count']} 欄位, {dr['records_count']} 筆){cd_mark}")
            lines.append(f"    權限：{perms}")
            if dr["app_domains"]:
                domains_str = ", ".join(f"{k}={v}" for k, v in dr["app_domains"].items())
                lines.append(f"    app_domain 分布：{domains_str}")
        lines.append("")
    if custom_tables is not None:
        from aigo_data_center import format_tables_report
        lines.append(format_tables_report(custom_tables))
        lines.append("  ★ 建表前必讀：自建表跨 app 共用，語意相同的表請重用不要新建")
        lines.append("")

    if crons is None:
        lines.append("⏰ 排程盤點失敗——未能確認本 App 是否有排程")
        lines.append("  republish 或改動 action 名稱前請先自行確認，"
                     "action 消失連續 2 次會讓排程自動暫停")
        lines.append("")
    elif crons:
        lines.append(f"⏰ 綁在本 App 的排程（{len(crons)} 條）")
        for c in crons:
            state = "啟用中" if c.get("active") else \
                    f"已暫停（{c.get('paused_reason') or '未知原因'}）"
            lines.append(f"  {c.get('name')} → {c.get('action_name')}"
                         f"｜{c.get('schedule_kind')} {c.get('schedule_fields')}"
                         f"｜{state}")
            if c.get("last_status"):
                lines.append(f"    上次：{c.get('last_status')}"
                             f"（{c.get('lastcall') or '尚未執行'}）")
        lines.append("  ⚠️ 改動或刪除上列 action 前先確認影響——"
                     "action 消失連續 2 次會讓排程自動暫停，且不會自動恢復")
        lines.append("")

    css_status = "✅ 通過" if not analysis["css_issues"] else "❌ 有問題"
    lines.append(f"🎨 CSS 規範 {css_status}")
    for issue in analysis["css_issues"]:
        lines.append(f"  ⚠️ {issue}")
    lines.append("")
    lines.append("═" * 55)
    return "\n".join(lines)
