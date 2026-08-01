"""AI GO Builder Skill — 完整 E2E 測試腳本"""
import sys
import os
import json
import time
import tempfile
import shutil

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

from aigo_auth import login, get_app_info, init_config, load_config, validate_config, load_env_file
from aigo_review import analyze_vfs, check_css_compliance, format_review_report, PROTECTED_FILES
from aigo_scaffold import download_vfs_to_local
from aigo_sync import read_local_files, diff_vfs, sync_to_cloud, get_remote_vfs
from aigo_compile import compile_app, parse_compile_error, auto_fix_css, check_shadow_dom_compliance
from aigo_publish import publish_app, check_publish_status
from aigo_data_center import (
    list_tables, create_table, delete_table, get_table_impact,
    validate_field_spec, PermissionDenied, QuotaOrConflict,
)
import httpx

# === 設定（依序讀 <專案>/.aigo/.env → ~/.aigo/.env，環境變數優先） ===
# 專案根用 AIGO_PROJECT_ROOT 指定；沒指定就是 CWD——別在 skill 目錄下跑。
load_env_file(os.environ.get("AIGO_PROJECT_ROOT", "."))

BASE_URL = os.environ.get("AIGO_BASE_URL", "https://ai-go.app")
EMAIL = os.environ.get("AIGO_EMAIL", "")
PASSWORD = os.environ.get("AIGO_PASSWORD", "")
APP_ID = os.environ.get("AIGO_APP_ID", "")
SLUG = os.environ.get("AIGO_SLUG", "")

if not EMAIL or not PASSWORD or not APP_ID:
    print("❌ 缺少憑證：AIGO_EMAIL, AIGO_PASSWORD, AIGO_APP_ID")
    print("   建議做法（設定一次即可）：")
    print("     uv run python scripts/aigo_auth.py setup   # 建立 ~/.aigo/.env 後填入帳密")
    print("     AIGO_APP_ID / AIGO_SLUG 放該 app 專案的 .aigo/.env，並用 AIGO_PROJECT_ROOT 指過去")
    print("   或臨時用環境變數：$env:AIGO_EMAIL='xxx'; $env:AIGO_PASSWORD='xxx'; $env:AIGO_APP_ID='xxx'")
    sys.exit(1)

# === 測試框架 ===
results = []

def test(group: str, name: str, func):
    """執行單一測試"""
    start = time.time()
    try:
        checks = func()
        duration = round(time.time() - start, 2)
        all_pass = all(c[0] for c in checks)
        status = "PASS" if all_pass else "FAIL"
        results.append({"group": group, "name": name, "status": status, "duration": duration, "checks": checks})
        icon = "✅" if all_pass else "❌"
        print(f"  {icon} {name} ({duration}s)")
        for ok, desc in checks:
            flag = "  ✓" if ok else "  ✗"
            print(f"    {flag} {desc}")
    except Exception as e:
        duration = round(time.time() - start, 2)
        results.append({"group": group, "name": name, "status": "ERROR", "duration": duration,
                        "checks": [(False, f"例外：{str(e)[:200]}")]})
        print(f"  💥 {name} ({duration}s) — ERROR: {str(e)[:150]}")

# ====================================================================
print("=" * 60)
print("  AI GO Builder Skill — E2E 測試執行")
print(f"  目標 App: {APP_ID}")
print("=" * 60)

# ====================================================================
print("\n📦 群組 1：認證與連線")
# ====================================================================

token = None
app_info = None

def t1_1():
    global token
    result = login(BASE_URL, EMAIL, PASSWORD)
    token = result.get("access_token", "")
    return [
        (isinstance(result, dict), "回應為 dict"),
        (len(token) > 50, f"access_token 長度 {len(token)} > 50"),
        (bool(result.get("refresh_token")), "含 refresh_token"),
        (result.get("expires_in") == 3600, f"expires_in={result.get('expires_in')} == 3600"),
        (result.get("token_type") == "bearer", f"token_type={result.get('token_type')} == bearer"),
    ]

def t1_2():
    global app_info
    app_info = get_app_info(BASE_URL, token, APP_ID)
    return [
        (app_info.get("id") == APP_ID, f"id 匹配"),
        (isinstance(app_info.get("vfs_state"), dict), "vfs_state 為 dict"),
        (isinstance(app_info.get("vfs_version"), int) and app_info["vfs_version"] >= 1, f"vfs_version={app_info.get('vfs_version')} >= 1"),
        (app_info.get("slug") == SLUG, f"slug={app_info.get('slug')} == {SLUG}"),
        (bool(app_info.get("name")), f"name 非空: {app_info.get('name')}"),
    ]

def t1_3():
    try:
        bad = login(BASE_URL, EMAIL, "wrong_password_12345")
        # 如果沒有 raise，檢查是否回傳了 token
        has_token = bool(bad.get("access_token"))
        return [(not has_token, "無效密碼不應回傳 token")]
    except Exception as e:
        err_str = str(e)
        is_auth_err = "401" in err_str or "400" in err_str or "422" in err_str or "Unauthorized" in err_str
        return [(is_auth_err, f"正確拒絕無效密碼: {err_str[:80]}")]

test("認證與連線", "T1.1 Login API 正常登入", t1_1)
test("認證與連線", "T1.2 Token 可用於 GET App", t1_2)
test("認證與連線", "T1.3 無效密碼被拒絕", t1_3)

# ====================================================================
print("\n🔍 群組 2：Review 功能完整性")
# ====================================================================

vfs = app_info.get("vfs_state", {}) if app_info else {}

def t2_1():
    analysis = analyze_vfs(vfs)
    files = analysis["files"]
    sdk_files = [f for f in files if f["tag"] == "[SDK]"]
    inj_files = [f for f in files if f["tag"] == "[INJ]"]
    app_files = [f for f in files if f["tag"] == "[APP]"]
    all_positive = all(f["size"] > 0 for f in files)
    return [
        (analysis["total_files"] == 26, f"total_files={analysis['total_files']} == 26"),
        (len(sdk_files) == 3, f"SDK 檔案數={len(sdk_files)} == 3"),
        (len(inj_files) == 3, f"INJ 檔案數={len(inj_files)} == 3"),
        (len(app_files) == 20, f"APP 檔案數={len(app_files)} == 20"),
        (all_positive, "所有檔案 size > 0"),
    ]

def t2_2():
    analysis = analyze_vfs(vfs)
    routes = analysis["routes"]
    return [
        (analysis["router_type"] == "HashRouter", f"router_type={analysis['router_type']}"),
        ("/" in routes, "含路由 /"),
        ("/kanban" in routes, "含路由 /kanban"),
        ("/patents" in routes, "含路由 /patents"),
        (any(":id" in r for r in routes), f"含動態路由 /patents/:id"),
        (len(routes) >= 5, f"路由數={len(routes)} >= 5"),
    ]

def t2_3():
    css = vfs.get("src/App.css", "")
    issues = check_css_compliance(css)
    has_html_issue = any("html" in i for i in issues)
    has_host_mention = any(":host" in i for i in issues)
    return [
        (len(issues) > 0, f"偵測到 {len(issues)} 個 CSS 問題"),
        (has_html_issue, "問題包含 'html' 關鍵字"),
        (has_host_mention, "問題包含 ':host' 關鍵字"),
    ]

def t2_4():
    analysis = analyze_vfs(vfs)
    actions = analysis["actions"]
    names = [a["name"] for a in actions]
    return [
        (len(actions) == 4, f"Action 數量={len(actions)} == 4"),
        ("ocr_and_nlp_doc" in names, "含 ocr_and_nlp_doc"),
        ("ai_patent_assistant" in names, "含 ai_patent_assistant"),
        ("oa_helper" in names, "含 oa_helper"),
        ("billing_and_rates" in names, "含 billing_and_rates"),
    ]

test("Review 功能", "T2.1 VFS 檔案分類正確", t2_1)
test("Review 功能", "T2.2 路由結構偵測", t2_2)
test("Review 功能", "T2.3 CSS 合規性檢查", t2_3)
test("Review 功能", "T2.4 Server Actions 偵測", t2_4)

# ====================================================================
print("\n🔄 群組 3：VFS 同步與版本控制")
# ====================================================================

test_page_content = '''import React from "react";
export default function E2ETestPage() {
  return <div className="page-content"><h1>E2E 測試頁面</h1><p>此頁面由自動測試建立。</p></div>;
}
'''

def t3_1():
    global app_info
    # 取最新版本
    remote_vfs, v_before = get_remote_vfs(BASE_URL, token, APP_ID)
    # PATCH 注入測試檔案
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    resp = httpx.patch(
        f"{BASE_URL}/api/v1/builder/apps/{APP_ID}/source/files",
        headers=headers,
        json={"files": {"src/pages/E2ETestPage.tsx": test_page_content}, "expected_version": v_before},
        timeout=30
    )
    patch_ok = resp.status_code == 200
    # GET 確認
    app2 = get_app_info(BASE_URL, token, APP_ID)
    v_after = app2.get("vfs_version", 0)
    has_file = "src/pages/E2ETestPage.tsx" in app2.get("vfs_state", {})
    content_match = app2.get("vfs_state", {}).get("src/pages/E2ETestPage.tsx", "") == test_page_content
    app_info = app2  # 更新全域
    return [
        (patch_ok, f"PATCH HTTP {resp.status_code} == 200"),
        (v_after == v_before + 1, f"vfs_version {v_before}→{v_after} (+1)"),
        (has_file, "VFS 包含 E2ETestPage.tsx"),
        (content_match, "內容完全匹配"),
    ]

def t3_2():
    # 故意用舊版本
    remote_vfs, v_current = get_remote_vfs(BASE_URL, token, APP_ID)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    resp = httpx.patch(
        f"{BASE_URL}/api/v1/builder/apps/{APP_ID}/source/files",
        headers=headers,
        json={"files": {"src/pages/Conflict.tsx": "test"}, "expected_version": v_current - 2},
        timeout=30
    )
    return [
        (resp.status_code == 409, f"HTTP {resp.status_code} == 409 Conflict"),
    ]

def t3_3():
    # 建立臨時目錄模擬含 SDK 檔案的專案
    tmp = tempfile.mkdtemp(prefix="aigo_test_")
    try:
        # 建立假檔案（含 SDK 保護檔）
        os.makedirs(os.path.join(tmp, "src"), exist_ok=True)
        os.makedirs(os.path.join(tmp, "actions"), exist_ok=True)
        for f in ["src/App.tsx", "src/App.css", "src/main.tsx", "src/api.ts", "src/db.ts",
                   "src/action.ts", "src/data.json", "src/db.json", "src/actions.json"]:
            with open(os.path.join(tmp, f), "w", encoding="utf-8") as fh:
                fh.write(f"// test content for {f}")
        with open(os.path.join(tmp, "actions", "manifest.json"), "w", encoding="utf-8") as fh:
            fh.write("{}")

        files = read_local_files(tmp)
        checks = [
            ("src/api.ts" not in files, "排除 src/api.ts"),
            ("src/db.ts" not in files, "排除 src/db.ts"),
            ("src/action.ts" not in files, "排除 src/action.ts"),
            ("src/data.json" not in files, "排除 src/data.json"),
            ("src/db.json" not in files, "排除 src/db.json"),
            ("src/actions.json" not in files, "排除 src/actions.json"),
            ("src/App.tsx" in files, "保留 src/App.tsx"),
            ("src/App.css" in files, "保留 src/App.css"),
        ]
        return checks
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

test("VFS 同步", "T3.1 注入測試檔案到 VFS", t3_1)
test("VFS 同步", "T3.2 樂觀鎖衝突偵測", t3_2)
test("VFS 同步", "T3.3 SDK 保護檔案過濾", t3_3)

# ====================================================================
print("\n🔨 群組 4：編譯與 CSS 自動修復")
# ====================================================================

def t4_1():
    result = compile_app(BASE_URL, token, SLUG, dev=True)
    return [
        (result.get("success") == True, f"success={result.get('success')}"),
        (len(result.get("html", "")) > 100, f"html length={len(result.get('html', ''))} > 100"),
        (len(result.get("bundle_js", "")) > 1000, f"bundle_js length={len(result.get('bundle_js', ''))} > 1000"),
        (len(result.get("css", "")) > 100, f"css length={len(result.get('css', ''))} > 100"),
    ]

def t4_2():
    css = vfs.get("src/App.css", "")
    # 先確認有問題
    issues_before = check_css_compliance(css)
    # 修復
    fixed = auto_fix_css(css)
    issues_after = check_css_compliance(fixed)
    has_html_host = "html, :host {" in fixed or "html, :host{" in fixed
    return [
        (len(issues_before) > 0, f"修復前有 {len(issues_before)} 個問題"),
        (has_html_host, "修復後含 'html, :host {'"),
        (len(issues_after) == 0, f"修復後問題數={len(issues_after)} == 0"),
    ]

def t4_3():
    error_text = '[ERROR] Could not resolve "react-missing"\n    src/App.tsx:3:24'
    errors = parse_compile_error(error_text)
    e0 = errors[0] if errors else {}
    return [
        (len(errors) >= 1, f"解析出 {len(errors)} 個錯誤"),
        ("App.tsx" in e0.get("file", ""), f"file={e0.get('file')}"),
        (e0.get("line") == 3, f"line={e0.get('line')} == 3"),
        ("react-missing" in e0.get("message", ""), f"message 含 'react-missing'"),
    ]

test("編譯", "T4.1 現有程式碼可編譯", t4_1)
test("編譯", "T4.2 CSS auto_fix 修復已知問題", t4_2)
test("編譯", "T4.3 編譯錯誤解析", t4_3)

# ====================================================================
print("\n📊 群組 5：資料中心自建表")
# ====================================================================

test_table_key = None
skip_reason = None

def t5_1():
    """建自建表。非管理員帳號會 403 —— 那是預期行為，記為 skip 不算失敗。"""
    global test_table_key, skip_reason
    try:
        result = create_table(BASE_URL, token, f"E2E 測試表 {int(time.time())}", fields=[
            {"display_name": "名稱", "field_type": "text", "is_required": True},
            {"display_name": "備註", "field_type": "text"},
        ])
    except PermissionDenied:
        skip_reason = "帳號非 system.admin，結構操作測試略過（403 為預期）"
        return [(True, skip_reason)]
    except QuotaOrConflict as e:
        skip_reason = f"撞配額或衝突，結構操作測試略過：{e}"
        return [(True, skip_reason)]
    test_table_key = result.get("physical_name")
    tables = list_tables(BASE_URL, token)
    keys = [t.get("physical_name") for t in tables]
    return [
        (bool(test_table_key), f"回傳 physical_name={test_table_key}"),
        (test_table_key in keys, "列表含新建的表"),
    ]

def t5_2():
    """欄位規格本地驗證（不打 API）。"""
    def bad(spec):
        try:
            validate_field_spec(spec)
            return False
        except ValueError:
            return True
    return [
        (bad({"display_name": "x", "field_type": "unknown"}), "未知型別 → 拒絕"),
        (bad({"display_name": "x", "field_type": "select"}), "select 缺 options → 拒絕"),
        (bad({"display_name": "x", "field_type": "relation"}), "relation 未指定目標 → 拒絕"),
        (bad({"display_name": "x", "field_type": "relation",
              "target_table_id": "a", "target_erp_key": "b"}), "relation 兩個目標都給 → 拒絕"),
        (bad({"display_name": "created_at", "field_type": "date"}), "系統欄位名 → 拒絕"),
        (not bad({"display_name": "姓名", "field_type": "text"}), "合法 text 欄位 → 通過"),
    ]

def t5_3():
    """兩段式刪除：先看 impact，confirm 必須是實體名。"""
    global test_table_key
    if not test_table_key:
        return [(True, skip_reason or "無測試表，略過")]

    impact = get_table_impact(BASE_URL, token, test_table_key)
    wrong_confirm_rejected = False
    try:
        delete_table(BASE_URL, token, test_table_key, confirm="顯示名不是實體名")
    except ValueError:
        wrong_confirm_rejected = True

    ok = delete_table(BASE_URL, token, test_table_key, confirm=test_table_key)
    tables = list_tables(BASE_URL, token)
    keys = [t.get("physical_name") for t in tables]
    gone = test_table_key not in keys
    test_table_key = None
    return [
        (isinstance(impact, dict), "取得刪表影響預覽"),
        (wrong_confirm_rejected, "用顯示名當 confirm → 被擋下"),
        (ok, "以實體名 confirm 刪除成功"),
        (gone, "列表已不含該表"),
    ]

test("自建表", "T5.1 建立自建表", t5_1)
test("自建表", "T5.2 欄位規格驗證", t5_2)
test("自建表", "T5.3 兩段式刪除並清理", t5_3)

# ====================================================================
print("\n🏗️ 群組 6：腳手架生成器")
# ====================================================================

def t6_1():
    tmp = tempfile.mkdtemp(prefix="aigo_scaffold_")
    try:
        created = download_vfs_to_local(vfs, tmp)
        has_app_tsx = "src/App.tsx" in created
        has_app_css = "src/App.css" in created
        has_main = "src/main.tsx" in created
        has_manifest = "actions/manifest.json" in created
        no_sdk = all(p not in created for p in ["src/api.ts", "src/db.ts", "src/action.ts"])
        no_inj = all(p not in created for p in ["src/data.json", "src/db.json", "src/actions.json"])
        # 內容驗證
        app_tsx_local = ""
        app_tsx_path = os.path.join(tmp, "src", "App.tsx")
        if os.path.exists(app_tsx_path):
            with open(app_tsx_path, "r", encoding="utf-8") as f:
                app_tsx_local = f.read()
        content_match = app_tsx_local == vfs.get("src/App.tsx", "")
        gi_exists = os.path.exists(os.path.join(tmp, ".gitignore"))
        return [
            (len(created) > 0, f"下載了 {len(created)} 個檔案"),
            (no_sdk, "不含 SDK 保護檔"),
            (no_inj, "不含 Runtime 注入檔"),
            (has_app_tsx, "含 src/App.tsx"),
            (has_app_css, "含 src/App.css"),
            (has_main, "含 src/main.tsx"),
            (content_match, "App.tsx 內容匹配"),
            (has_manifest, "含 actions/manifest.json"),
            (gi_exists, ".gitignore 存在"),
        ]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

def t6_2():
    tmp = tempfile.mkdtemp(prefix="aigo_action_")
    try:
        created = download_vfs_to_local(vfs, tmp)
        action_path = os.path.join(tmp, "actions", "ai_patent_assistant.py")
        exists = os.path.exists(action_path)
        content = ""
        if exists:
            with open(action_path, "r", encoding="utf-8") as f:
                content = f.read()
        len_match = len(content) == len(vfs.get("actions/ai_patent_assistant.py", ""))
        has_execute = "def execute(ctx)" in content or "def execute(" in content
        return [
            (exists, "ai_patent_assistant.py 存在"),
            (len_match, f"長度匹配 ({len(content)} chars)"),
            (has_execute, "含 def execute(ctx)"),
        ]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

test("腳手架", "T6.1 VFS 下載到本地", t6_1)
test("腳手架", "T6.2 Action Python 檔完整性", t6_2)

# ====================================================================
print("\n🚀 群組 7：發布與狀態驗證")
# ====================================================================

def t7_1():
    c = compile_app(BASE_URL, token, SLUG, dev=True)
    compile_ok = c.get("success") == True
    p = publish_app(BASE_URL, token, APP_ID)
    publish_ok = isinstance(p, dict) and bool(p)
    return [
        (compile_ok, f"Compile success={c.get('success')}"),
        (publish_ok, "Publish 回應有效"),
    ]

def t7_2():
    status = check_publish_status(BASE_URL, token, APP_ID)
    app_final = get_app_info(BASE_URL, token, APP_ID)
    pub_at = app_final.get("published_at")
    return [
        (status == "published", f"status={status}"),
        (bool(pub_at), f"published_at={pub_at}"),
    ]

test("發布", "T7.1 編譯後發布", t7_1)
test("發布", "T7.2 發布後狀態確認", t7_2)

# ====================================================================
print("\n🧹 清理測試痕跡")
# ====================================================================

# 清理注入的測試檔案
try:
    remote_vfs, v = get_remote_vfs(BASE_URL, token, APP_ID)
    if "src/pages/E2ETestPage.tsx" in remote_vfs:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        resp = httpx.request("DELETE", f"{BASE_URL}/api/v1/builder/apps/{APP_ID}/source/files",
                             headers=headers, json={"paths": ["src/pages/E2ETestPage.tsx"], "expected_version": v},
                             timeout=30)
        print(f"  刪除 E2ETestPage.tsx: HTTP {resp.status_code}")
        # 重新編譯+發布恢復原始狀態
        c = compile_app(BASE_URL, token, SLUG, dev=True)
        print(f"  重新編譯: success={c.get('success')}")
        p = publish_app(BASE_URL, token, APP_ID)
        print(f"  重新發布: OK")
    else:
        print("  E2ETestPage.tsx 已不存在，無需清理")
except Exception as e:
    print(f"  清理警告: {e}")

# 清理測試表（如果還在）
if test_table_key:
    try:
        delete_table(BASE_URL, token, test_table_key, confirm=test_table_key)
        print(f"  刪除測試表: OK")
    except Exception:
        pass

# ====================================================================
# 輸出總結
# ====================================================================
print("\n" + "=" * 60)
print("  測試結果總結")
print("=" * 60)

total = len(results)
passed = sum(1 for r in results if r["status"] == "PASS")
failed = sum(1 for r in results if r["status"] == "FAIL")
errors = sum(1 for r in results if r["status"] == "ERROR")
total_time = sum(r["duration"] for r in results)

print(f"\n  合計：{total} 個測試案例")
print(f"  ✅ PASS:  {passed}")
print(f"  ❌ FAIL:  {failed}")
print(f"  💥 ERROR: {errors}")
print(f"  ⏱  總耗時: {total_time:.1f}s")

# 分群組統計
groups = {}
for r in results:
    g = r["group"]
    if g not in groups:
        groups[g] = {"pass": 0, "fail": 0, "error": 0}
    groups[g][{"PASS": "pass", "FAIL": "fail", "ERROR": "error"}.get(r["status"], "error")] += 1

print("\n  群組統計：")
for g, s in groups.items():
    icon = "🟢" if s["fail"] == 0 and s["error"] == 0 else "🔴"
    print(f"    {icon} {g}: {s['pass']}P / {s['fail']}F / {s['error']}E")

# 判定等級
core_ok = all(r["status"] == "PASS" for r in results if r["group"] in ("認證與連線", "Review 功能"))
if passed == total:
    level = "🟢 全部通過"
elif passed >= 17 and core_ok:
    level = "🟡 可接受"
else:
    level = "🔴 失敗"

print(f"\n  {'=' * 40}")
print(f"  判定等級：{level} ({passed}/{total})")
print(f"  {'=' * 40}")

# 輸出失敗/錯誤的詳細資訊
if failed + errors > 0:
    print("\n  失敗/錯誤詳細：")
    for r in results:
        if r["status"] != "PASS":
            print(f"\n  ❌ [{r['group']}] {r['name']} — {r['status']}")
            for ok, desc in r["checks"]:
                if not ok:
                    print(f"      ✗ {desc}")

# 輸出 JSON 結果
output_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..",
                           "dev project", "FDE AIGO Builder skill", "test_results.json")
output_path = os.path.normpath(output_path)
try:
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({"results": results, "summary": {"total": total, "pass": passed, "fail": failed,
                   "error": errors, "level": level, "duration": total_time}}, f, ensure_ascii=False, indent=2)
    print(f"\n  結果已儲存至: {output_path}")
except Exception:
    pass
