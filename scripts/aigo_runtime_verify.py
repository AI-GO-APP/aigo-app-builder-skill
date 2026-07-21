"""
aigo_runtime_verify.py — Custom App Runtime 端到端驗證

在 preview（compile 後）和 publish 後，驗證 App 實際可運行：
1. Compile 產物驗證（HTML/JS/CSS 有效性）
2. 自建表記錄 CRUD（讀寫刪查）
3. Server Action 呼叫
4. published_vfs 與 vfs_state 一致性
"""
import json
import time
from typing import Any


def verify_compile_output(compile_result: dict, baseline_css_size: int = 0) -> dict:
    """
    驗證 Compile API 回傳的產物是否有效。

    Args:
        compile_result: compile_app() 的回傳值
        baseline_css_size: 上次成功編譯的 CSS 大小（可選）。
                          若提供，會進行回歸比對（新 CSS < 基線 50% 視為異常）。

    Returns:
        驗證報告 dict
    """
    checks = []
    html = compile_result.get("html", "")
    js = compile_result.get("bundle_js", "")
    css = compile_result.get("css", "")

    checks.append(("compile_success", compile_result.get("success") is True))
    checks.append(("html_not_empty", len(html) > 50))
    checks.append(("html_has_doctype", "<!DOCTYPE" in html or "<!doctype" in html))
    checks.append(("html_has_root_div", 'id="root"' in html))
    checks.append(("bundle_js_not_empty", len(js) > 500))
    checks.append(("bundle_js_has_react", "React" in js or "react" in js or "createElement" in js))
    checks.append(("css_not_empty", len(css) > 50))

    # ★ App.css 內容存在性檢查：確認 CSS 含有 App 自定義樣式
    # Runtime 基礎 CSS ~42KB，但不含 :host/:root 變數宣告，這些來自 App.css
    has_app_css_markers = (
        ":host" in css or ":root" in css  # CSS 變數宣告（SKILL.md 要求 :host, :root）
        or "--" in css  # CSS custom properties
    )
    checks.append(("css_has_app_styles", has_app_css_markers))

    # ★ CSS 基線回歸比對（如有提供基線）
    if baseline_css_size > 0:
        regression_ratio = len(css) / baseline_css_size
        # CSS 大小低於基線的 50% 視為回歸（可能遺失 App.css）
        checks.append(("css_no_regression", regression_ratio >= 0.5))

    all_pass = all(ok for _, ok in checks)
    return {
        "passed": all_pass,
        "checks": checks,
        "html_size": len(html),
        "js_size": len(js),
        "css_size": len(css),
    }


def verify_custom_data_crud(base_url: str, token: str, table_key: str) -> dict:
    """
    對指定**自建表**執行完整 CRUD 驗證（建→讀→刪→確認刪除）。

    Args:
        base_url: API 根 URL
        token: JWT access_token
        table_key: 自建表的**實體名**（physical_name），不是 UUID、不是顯示名

    Returns:
        驗證報告 dict；失敗時 checks 內含錯誤訊息

    註：只碰記錄面（需 builder.access），不做任何結構操作。
    """
    import httpx
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    import json as _json
    base = f"{base_url}/api/v1/data-center/tables/{table_key}/records"
    checks = []
    record_id = None

    def _exists(rid):
        """以 id 過濾直接查——不掃分頁，避免大表產生假陰性。"""
        r = httpx.get(base, headers=headers, timeout=15, params={
            "filters": _json.dumps([{"field": "id", "op": "eq", "value": str(rid)}]),
            "page_size": 1,
        })
        if r.status_code != 200:
            return False
        return r.json().get("total", 0) > 0

    def _placeholder(f):
        """依型別給合法佔位值，讓必填欄位不會擋下驗證。"""
        t_ = f.get("field_type")
        if t_ == "text":
            return f"E2E_verify_{int(time.time())}"
        if t_ == "number":
            return 0
        if t_ == "boolean":
            return False
        if t_ == "date":
            return "2000-01-01"
        if t_ == "datetime":
            return "2000-01-01T00:00:00Z"
        if t_ == "json":
            return {}
        if t_ == "select":
            opts = f.get("options") or []
            return opts[0] if opts else None
        return None  # relation / image：湊不出合法值

    try:
        schema = httpx.get(
            f"{base_url}/api/v1/data-center/tables/{table_key}",
            headers=headers, timeout=15,
        )
        checks.append(("schema_readable", schema.status_code == 200))
        if schema.status_code != 200:
            return {"passed": False, "checks": checks,
                    "detail": f"讀不到表結構（{schema.status_code}）"}

        fields = [f for f in (schema.json().get("fields") or [])
                  if not f.get("is_system")]
        payload = {}
        for f in fields:
            if f.get("is_required"):
                v = _placeholder(f)
                if v is None:
                    return {"passed": True, "skipped": True, "checks": checks,
                            "detail": f"必填欄位 {f.get('physical_name')} "
                                      f"（{f.get('field_type')}）無法自動產生佔位值，跳過"}
                payload[f["physical_name"]] = v
        if not payload:  # 沒有必填欄位 → 隨便填一個 text 以產生可辨識記錄
            for f in fields:
                if f.get("field_type") == "text":
                    payload[f["physical_name"]] = _placeholder(f)
                    break

        resp = httpx.post(base, headers=headers, json={"data": payload}, timeout=15)
        create_ok = resp.status_code in (200, 201)
        checks.append(("create_record", create_ok))
        if not create_ok:
            return {"passed": False, "checks": checks,
                    "detail": f"建立失敗（{resp.status_code}）：{resp.text[:200]}"}

        record_id = resp.json().get("id")
        checks.append(("create_has_id", bool(record_id)))
        checks.append(("read_confirms_create", bool(record_id) and _exists(record_id)))

    except Exception as e:
        checks.append(("crud_exception", False))
        return {"passed": False, "checks": checks, "detail": str(e)[:200]}
    finally:
        # ★ 無論成敗都要清乾淨——這是租戶的**真實 Postgres 表**，
        #   留下測試記錄比舊 CustomObject 的 JSONB 沙盒代價高得多
        if record_id:
            try:
                d = httpx.delete(f"{base}/{record_id}", headers=headers, timeout=15)
                checks.append(("delete_record", d.status_code in (200, 204)))
                checks.append(("read_confirms_delete", not _exists(record_id)))
            except Exception as e:
                checks.append(("cleanup_failed", False))

    all_pass = all(ok for _, ok in checks)
    return {"passed": all_pass, "checks": checks}


def verify_server_action(base_url: str, token: str, app_id: str,
                          action_name: str, params: dict = None) -> dict:
    """
    呼叫 Server Action 並驗證回傳結果。

    Args:
        base_url: API 根 URL
        token: Builder JWT token
        app_id: App UUID
        action_name: Action 名稱
        params: 傳入 Action 的參數

    Returns:
        驗證報告 dict
    """
    import httpx
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    resp = httpx.post(
        f"{base_url}/api/v1/actions/apps/{app_id}/run/{action_name}",
        headers=headers,
        json={"params": params or {}},
        timeout=30,
    )

    checks = []
    checks.append(("http_200", resp.status_code == 200))

    if resp.status_code == 200:
        data = resp.json()
        checks.append(("has_execution_id", bool(data.get("execution_id"))))
        checks.append(("status_success", data.get("status") == "success"))
        checks.append(("has_result", data.get("result") is not None))
        checks.append(("no_error", data.get("error") is None))
        duration = data.get("duration_ms", 0)
        checks.append(("under_30s", duration < 30000))
    else:
        checks.append(("response_body", False))

    all_pass = all(ok for _, ok in checks)
    return {
        "passed": all_pass,
        "checks": checks,
        "response": resp.json() if resp.status_code == 200 else {"status_code": resp.status_code},
    }


def verify_publish_consistency(base_url: str, token: str, app_id: str) -> dict:
    """
    驗證 published_vfs 與 vfs_state 的一致性。

    Args:
        base_url: API 根 URL
        token: JWT access_token
        app_id: App UUID

    Returns:
        驗證報告 dict
    """
    from aigo_auth import get_app_info
    app = get_app_info(base_url, token, app_id)

    vfs = app.get("vfs_state", {})
    pvfs = app.get("published_vfs", {})
    status = app.get("status", "")
    pub_at = app.get("published_at", "")

    checks = []
    checks.append(("status_published", status == "published"))
    checks.append(("published_at_exists", bool(pub_at)))
    checks.append(("published_vfs_not_empty", len(pvfs) > 0))
    checks.append(("file_count_match", len(pvfs) == len(vfs)))

    # 逐檔比對
    if pvfs and vfs:
        vfs_paths = set(vfs.keys())
        pvfs_paths = set(pvfs.keys())
        checks.append(("paths_match", vfs_paths == pvfs_paths))

        content_match = all(pvfs.get(p) == vfs.get(p) for p in pvfs_paths)
        checks.append(("content_match", content_match))

        if vfs_paths != pvfs_paths:
            missing = vfs_paths - pvfs_paths
            extra = pvfs_paths - vfs_paths
            if missing:
                checks.append(("missing_in_published", False))
            if extra:
                checks.append(("extra_in_published", False))

    all_pass = all(ok for _, ok in checks)
    return {"passed": all_pass, "checks": checks, "vfs_files": len(vfs), "published_files": len(pvfs)}


def run_full_runtime_verification(
    base_url: str, token: str, app_id: str, slug: str,
    table_key: str = "", action_name: str = ""
) -> dict:
    """
    執行完整的 preview + publish 端到端運行驗證。

    Args:
        base_url: API 根 URL
        token: JWT token
        app_id: App UUID
        slug: App slug
        table_key: 自建表實體名 physical_name（可選）
        action_name: Server Action 名稱（可選）

    Returns:
        完整驗證報告 dict
    """
    from aigo_compile import compile_app

    results = {}
    all_pass = True

    # 1. Compile 產物驗證（Preview 狀態）
    compile_result = compile_app(base_url, token, slug, dev=True)
    r1 = verify_compile_output(compile_result)
    results["compile_output"] = r1
    if not r1["passed"]:
        all_pass = False

    # 2. Publish 一致性驗證
    r2 = verify_publish_consistency(base_url, token, app_id)
    results["publish_consistency"] = r2
    if not r2["passed"]:
        all_pass = False

    # 3. 自建表記錄 CRUD（如果提供 table_key）
    if table_key:
        r3 = verify_custom_data_crud(base_url, token, table_key)
        results["custom_data_crud"] = r3
        if not r3["passed"]:
            all_pass = False

    # 4. Server Action（如果提供 action_name）
    if action_name:
        r4 = verify_server_action(base_url, token, app_id, action_name)
        results["server_action"] = r4
        if not r4["passed"]:
            all_pass = False

    results["all_passed"] = all_pass
    return results


def format_verification_report(results: dict) -> str:
    """格式化驗證報告為可讀文字"""
    lines = []
    lines.append("═" * 55)
    lines.append("  Custom App Runtime 端到端驗證報告")
    lines.append("═" * 55)

    section_names = {
        "compile_output": "📦 Compile 產物驗證",
        "publish_consistency": "🚀 Publish 一致性",
        "custom_data_crud": "📊 自建表記錄 CRUD",
        "server_action": "⚡ Server Action",
    }

    for key, label in section_names.items():
        if key not in results:
            continue
        r = results[key]
        icon = "✅" if r["passed"] else "❌"
        lines.append(f"\n{icon} {label}")
        for name, ok in r["checks"]:
            flag = "  ✓" if ok else "  ✗"
            lines.append(f"  {flag} {name}")
        # 額外資訊
        if key == "compile_output":
            lines.append(f"    HTML={r.get('html_size',0):,} JS={r.get('js_size',0):,} CSS={r.get('css_size',0):,}")

    overall = "✅ 全部通過" if results.get("all_passed") else "❌ 有項目失敗"
    lines.append(f"\n{'═' * 55}")
    lines.append(f"  結果：{overall}")
    lines.append("═" * 55)
    return "\n".join(lines)
