"""AI GO Custom App VFS 同步工具"""
import os
from typing import Any

PROTECTED_FILES = {"src/api.ts", "src/db.ts", "src/action.ts", "src/data.json", "src/db.json", "src/actions.json"}
# 起手式（starter-internal／starter-external）自帶、會讓發布 409 EGRESS_NOT_READY 的兩個檔：
# `_template.json` 宣告 required_egress: openai，示範 action 也字面呼叫 openai。與需求無關就兩個一起刪
# （只刪 action 仍擋；README／manifest 殘留不影響閘門）。2026-09-09 prod 實打。
STARTER_EGRESS_LEFTOVERS = ("_template.json", "actions/summarize_leads.py")
# sync_to_cloud() 遇到「遠端有、本機沒有」的 actions/ 檔時怎麼辦。PATCH 是合併、不會刪檔，
# 而平台只看檔案在不在來決定 action 能不能被呼叫——本機刪掉的 action 會繼續在線上。
# 這裡刻意沒有 "delete"：sync_to_cloud() 的 files 可能只是部分檔案，拿它當「本機全貌」去刪會把
# 沒帶進來的 action 全刪掉。要刪，由讀了完整本機專案的 full_deploy() 做，或明確呼叫 delete_remote_files()。
REMOTE_ONLY_MODES = ("abort", "keep")


class RemoteOnlyFilesError(RuntimeError):
    """遠端還留著本機已經沒有的 actions/ 檔；`paths` 是那些路徑。"""

    def __init__(self, paths: list[str]):
        self.paths = list(paths)
        rows = "\n".join(f"   - {p}" for p in self.paths)
        super().__init__(
            "同步中止（尚未寫入任何東西）：遠端還有本機沒有的 actions/ 檔，同步不會刪它們，"
            "發布後照樣可以被呼叫——\n" + rows +
            "\n   要下架 → delete_remote_files(..., paths=<上列路徑>) 後重新同步，"
            "或 full_deploy(..., on_remote_only=\"delete\")（發布時平台會回 409 ACTION_REMOVAL，再帶 confirm_removal=True）；"
            "\n   要保留（本機不是完整專案、只同步部分檔案）→ on_remote_only=\"keep\"。"
            "\n   這是用戶的決定，先問再帶。")


def read_local_files(project_path: str) -> dict[str, str]:
    """遞迴掃描 src/ 和 actions/ 目錄，跳過 SDK 保護檔"""
    files: dict[str, str] = {}
    for scan_dir in ["src", "actions"]:
        base = os.path.join(project_path, scan_dir)
        if not os.path.isdir(base):
            continue
        for root, _, filenames in os.walk(base):
            for fname in filenames:
                full = os.path.join(root, fname)
                rel = os.path.relpath(full, project_path).replace("\\", "/")
                if rel in PROTECTED_FILES:
                    continue
                with open(full, "r", encoding="utf-8") as f:
                    content = f.read()
                files[rel] = content
    # package.json
    pkg = os.path.join(project_path, "package.json")
    if os.path.exists(pkg):
        with open(pkg, "r", encoding="utf-8") as f:
            files["package.json"] = f.read()
    return files


def build_vfs_json(local_files: dict[str, str]) -> dict:
    """組裝為 VFS JSON 格式"""
    return {"files": local_files}


def get_remote_vfs(base_url: str, token: str, app_id: str) -> tuple[dict, int]:
    """取得雲端 VFS 和版本號"""
    import httpx
    headers = {"Authorization": f"Bearer {token}"}
    resp = httpx.get(f"{base_url}/api/v1/builder/apps/{app_id}", headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data.get("vfs_state", {}), data.get("vfs_version", 0)


def diff_vfs(local: dict[str, str], remote: dict[str, str]) -> dict:
    """比較差異。`deleted` 只是「遠端有、本機沒有」的清單——sync_to_cloud() 只處理其中
    actions/ 底下的（見 `on_remote_only`），其餘要刪用 delete_remote_files()。"""
    remote_app = {k: v for k, v in remote.items() if k not in PROTECTED_FILES}
    added = [k for k in local if k not in remote_app]
    deleted = [k for k in remote_app if k not in local]
    modified = [k for k in local if k in remote_app and local[k] != remote_app[k]]
    return {"added": added, "modified": modified, "deleted": deleted,
            "unchanged": len(local) - len(added) - len(modified)}


def remote_only_actions(local: dict[str, str], remote: dict[str, str]) -> list[str]:
    """遠端有、本機沒有的 actions/ 路徑（排序）。只看 actions/：那是會被呼叫的面，
    其餘路徑有平台注入檔與本機不掃的檔，不能拿「本機沒有」當成該刪。"""
    return sorted(k for k in remote
                  if k.startswith("actions/") and k not in local and k not in PROTECTED_FILES)


def sync_to_cloud(base_url: str, token: str, app_id: str, files: dict[str, str],
                  expected_version: int, *, on_remote_only: str = "abort") -> dict:
    """PATCH VFS 到雲端；以目標平台限制預檢合併後的完整 VFS。

    `on_remote_only` 決定遠端殘留的 actions/ 檔（見 `remote_only_actions`）怎麼處理：
    "abort"（預設）寫入前中止並列出、"keep" 列出後照常同步。這裡不提供刪除——`files` 可能只是部分檔案。
    """
    import httpx
    from aigo_limits import get_limits, check_vfs
    from aigo_compile import format_skipped_files
    if on_remote_only not in REMOTE_ONLY_MODES:
        raise ValueError(f"on_remote_only 只能是 {REMOTE_ONLY_MODES}，收到 {on_remote_only!r}")
    remote, version = get_remote_vfs(base_url, token, app_id)
    if version != expected_version:
        raise ValueError("VFS 版本衝突：預檢前版本已改變，請重新讀取。")
    stale = remote_only_actions(files, remote)
    if stale and on_remote_only == "abort":
        raise RemoteOnlyFilesError(stale)
    if stale and on_remote_only == "keep":
        print("⚠️ 遠端還有本機沒有的 actions/ 檔（on_remote_only=\"keep\"，不刪，發布後仍可被呼叫）：\n"
              + "\n".join(f"   - {p}" for p in stale))
    limits = get_limits(base_url, token, app_id)
    if limits is not None:
        skipped = check_vfs({**remote, **files}, limits)
        if skipped:
            print("同步預檢（實際結果以編譯回應為準）：\n" + format_skipped_files(skipped))
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"files": files, "expected_version": expected_version}
    resp = httpx.patch(f"{base_url}/api/v1/builder/apps/{app_id}/source/files",
                       headers=headers, json=payload, timeout=60)
    if resp.status_code == 409:
        raise ValueError("VFS 版本衝突 (409)。請重新取得最新版本後重試。")
    resp.raise_for_status()
    # ★ 二次 GET 驗證
    from aigo_auth import get_app_info
    verify_app = get_app_info(base_url, token, app_id)
    v_after = verify_app.get('vfs_version', 0)
    if v_after <= expected_version:
        raise RuntimeError(f'VFS 同步驗證失敗：版本號未遞增 ({expected_version} → {v_after})')
    # 驗證檔案是否確實寫入
    remote_vfs = verify_app.get('vfs_state', {})
    for path in files:
        if path not in remote_vfs:
            raise RuntimeError(f'VFS 同步驗證失敗：檔案 {path} 未出現在遠端 VFS')
    return resp.json()


def delete_remote_files(base_url: str, token: str, app_id: str, paths: list[str],
                        expected_version: int) -> dict:
    """DELETE 遠端 VFS 檔（起手式殘留的 `_template.json`／示範 action 要用這個；PATCH 不會刪）。

    `expected_version` 必填（樂觀鎖，缺就 400）；回應帶新的 `vfs_version`。刪後二次 GET 驗證檔案真的不在。
    """
    import httpx
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    resp = httpx.request("DELETE", f"{base_url}/api/v1/builder/apps/{app_id}/source/files",
                         headers=headers, json={"paths": list(paths), "expected_version": expected_version},
                         timeout=60)
    if resp.status_code == 409:
        raise ValueError("VFS 版本衝突 (409)。請重新取得最新版本後重試。")
    resp.raise_for_status()
    from aigo_auth import get_app_info
    remote_vfs = get_app_info(base_url, token, app_id).get("vfs_state", {})
    still_there = [p for p in paths if p in remote_vfs]
    if still_there:
        raise RuntimeError(f"VFS 刪除驗證失敗：{still_there} 仍在遠端 VFS")
    return resp.json()


def validate_sync(base_url: str, token: str, app_id: str, expected_count: int) -> bool:
    """驗證同步後檔案數"""
    vfs, _ = get_remote_vfs(base_url, token, app_id)
    return len(vfs) >= expected_count
