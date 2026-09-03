"""T3.2 / T4.1 / T7.1 補強二次驗證重測"""
import sys, os, time, json
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

from aigo_auth import get_token, get_app_info, load_env_file, resolve_base_url
from aigo_sync import get_remote_vfs
from aigo_compile import compile_app
from aigo_publish import publish_app
import httpx

load_env_file(os.environ.get("AIGO_PROJECT_ROOT", "."))

# 租戶空間（https://[tenant].ai-go.app）——無預設值，見 aigo_auth.resolve_base_url
try:
    BASE_URL = resolve_base_url(os.environ.get("AIGO_PROJECT_ROOT", "."))
except RuntimeError as e:
    print(e)
    sys.exit(1)

# 目標 app：工作區登錄表（--app／AIGO_APP → default_app → 唯一一筆），相容舊的 AIGO_APP_ID
from aigo_auth import resolve_app
try:
    _target = resolve_app(os.environ.get("AIGO_PROJECT_ROOT", "."))
except RuntimeError as e:
    print(e)
    sys.exit(1)
APP_ID = _target.id
SLUG = _target.slug or os.environ.get("AIGO_SLUG", "")
print(_target.describe())

try:
    token = get_token(os.environ.get("AIGO_PROJECT_ROOT", "."))
except RuntimeError as e:
    print(e)
    sys.exit(1)
print("Login OK\n")

results = []

def run(name, func):
    start = time.time()
    try:
        checks = func()
        dur = round(time.time() - start, 2)
        ok = all(c[0] for c in checks)
        icon = '\u2705' if ok else '\u274c'
        status = 'PASS' if ok else 'FAIL'
        results.append({"name": name, "status": status, "dur": dur, "checks": checks})
        print(f"{icon} {name} ({dur}s) \u2014 {status}")
        for passed, desc in checks:
            flag = "  \u2713" if passed else "  \u2717"
            print(f"  {flag} {desc}")
        print()
    except Exception as e:
        dur = round(time.time() - start, 2)
        results.append({"name": name, "status": "ERROR", "dur": dur, "checks": [(False, str(e)[:200])]})
        print(f"\U0001f4a5 {name} ({dur}s) \u2014 ERROR: {str(e)[:150]}\n")


# ============================================================
# T3.2 補強：樂觀鎖衝突偵測 + 二次 GET 確認 VFS 未被修改
# ============================================================
def t3_2_enhanced():
    # 記錄衝突前的狀態
    vfs_before, v_before = get_remote_vfs(BASE_URL, token, APP_ID)
    file_count_before = len(vfs_before)

    # 故意用過舊版本 PATCH
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    resp = httpx.patch(
        f"{BASE_URL}/api/v1/builder/apps/{APP_ID}/source/files",
        headers=headers,
        json={"files": {"src/pages/ConflictTest.tsx": "// should not exist"}, "expected_version": v_before - 2},
        timeout=30
    )
    got_409 = resp.status_code == 409

    # ★ 二次 GET 驗證：VFS 確實未被修改
    vfs_after, v_after = get_remote_vfs(BASE_URL, token, APP_ID)
    version_unchanged = v_after == v_before
    file_not_injected = "src/pages/ConflictTest.tsx" not in vfs_after
    file_count_same = len(vfs_after) == file_count_before

    return [
        (got_409, f"HTTP {resp.status_code} == 409 Conflict"),
        (version_unchanged, f"vfs_version \u672a\u8b8a: {v_before} \u2192 {v_after}"),
        (file_not_injected, "ConflictTest.tsx \u672a\u88ab\u5beb\u5165 VFS"),
        (file_count_same, f"\u6a94\u6848\u6578\u672a\u8b8a: {file_count_before} \u2192 {len(vfs_after)}"),
    ]

run("T3.2 \u6a02\u89c0\u9396\u885d\u7a81\u5075\u6e2c\uff08\u88dc\u5f37\uff09", t3_2_enhanced)


# ============================================================
# T4.1 補強：編譯成功 + 二次 GET 確認 VFS 未被異動 + 編譯產物驗證
# ============================================================
def t4_1_enhanced():
    # 記錄編譯前的 VFS 版本
    _, v_before = get_remote_vfs(BASE_URL, token, APP_ID)

    # 編譯
    result = compile_app(BASE_URL, token, SLUG, dev=True)
    success = result.get("success") == True
    html_len = len(result.get("html", ""))
    js_len = len(result.get("bundle_js", ""))
    css_len = len(result.get("css", ""))

    # ★ 二次 GET 驗證
    app_after = get_app_info(BASE_URL, token, APP_ID)
    v_after = app_after.get("vfs_version", 0)
    vfs_untouched = v_after == v_before  # 編譯不應改動 VFS 版本

    # ★ 確認 App 的 compiled 狀態（last_compiled_at 或 status 可用於判斷）
    status_after = app_after.get("status", "")
    # compiled_html 是否被更新（部分 API 可能不回傳此欄位，但 status 應仍有效）
    has_status = bool(status_after)

    return [
        (success, f"compile success={result.get('success')}"),
        (html_len > 100, f"html length={html_len} > 100"),
        (js_len > 1000, f"bundle_js length={js_len} > 1000"),
        (css_len > 100, f"css length={css_len} > 100"),
        (vfs_untouched, f"VFS \u7248\u672c\u672a\u88ab\u7de8\u8b6f\u7570\u52d5: {v_before} \u2192 {v_after}"),
        (has_status, f"\u7de8\u8b6f\u5f8c App status={status_after}"),
    ]

run("T4.1 \u73fe\u6709\u7a0b\u5f0f\u78bc\u53ef\u7de8\u8b6f\uff08\u88dc\u5f37\uff09", t4_1_enhanced)


# ============================================================
# T7.1 補強：發布 + 二次 GET 確認 status + published_at 時間戳更新
# ============================================================
def t7_1_enhanced():
    # 記錄發布前的狀態
    app_before = get_app_info(BASE_URL, token, APP_ID)
    pub_at_before = app_before.get("published_at", "")

    # 先編譯
    c = compile_app(BASE_URL, token, SLUG, dev=True)
    compile_ok = c.get("success") == True

    # 發布
    p = publish_app(BASE_URL, token, APP_ID)
    publish_response_ok = isinstance(p, dict) and bool(p)

    # ★ 二次 GET 驗證：status 確實變為 published
    app_after = get_app_info(BASE_URL, token, APP_ID)
    status_is_published = app_after.get("status") == "published"
    pub_at_after = app_after.get("published_at", "")
    pub_at_updated = bool(pub_at_after) and pub_at_after != pub_at_before

    return [
        (compile_ok, f"Compile success={c.get('success')}"),
        (publish_response_ok, f"Publish response \u6709\u6548"),
        (status_is_published, f"GET \u78ba\u8a8d status={app_after.get('status')} == published"),
        (pub_at_updated, f"published_at \u5df2\u66f4\u65b0: {pub_at_before[:19]}... \u2192 {pub_at_after[:19]}..."),
    ]

run("T7.1 \u7de8\u8b6f\u5f8c\u767c\u5e03\uff08\u88dc\u5f37\uff09", t7_1_enhanced)


# ============================================================
# 總結
# ============================================================
print("=" * 55)
total = len(results)
passed = sum(1 for r in results if r["status"] == "PASS")
failed = sum(1 for r in results if r["status"] == "FAIL")
errors = sum(1 for r in results if r["status"] == "ERROR")
total_dur = sum(r["dur"] for r in results)
print(f"  \u88dc\u5f37\u6e2c\u8a66\u7d50\u679c: {passed}/{total} PASS, {failed} FAIL, {errors} ERROR ({total_dur:.1f}s)")

# 統計所有 check 項目
all_checks = []
for r in results:
    all_checks.extend(r["checks"])
check_pass = sum(1 for c in all_checks if c[0])
check_total = len(all_checks)
print(f"  \u6aa2\u67e5\u9ede: {check_pass}/{check_total} \u901a\u904e")
print("=" * 55)
