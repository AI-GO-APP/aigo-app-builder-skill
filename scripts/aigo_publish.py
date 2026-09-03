"""AI GO Custom App 發布工具"""
from typing import Any


def publish_app(base_url: str, token: str, app_id: str) -> dict:
    """發布 App"""
    import httpx
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    resp = httpx.post(f"{base_url}/api/v1/builder/apps/{app_id}/publish",
                      headers=headers, json={"published_assets": {}}, timeout=30)
    resp.raise_for_status()
    # ★ 二次 GET 驗證
    from aigo_auth import get_app_info
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


def full_deploy(base_url: str, token: str, app_id: str, slug: str, project_path: str) -> dict:
    """完整部署流程：sync → compile → publish"""
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
    result["publish"] = publish_app(base_url, token, app_id)
    # ★ 二次 GET 驗證：確認發布狀態
    from aigo_auth import get_app_info
    verify = get_app_info(base_url, token, app_id)
    if verify.get('status') != 'published':
        raise RuntimeError(f"完整部署驗證失敗：status={verify.get('status')}，預期 published")
    return result
