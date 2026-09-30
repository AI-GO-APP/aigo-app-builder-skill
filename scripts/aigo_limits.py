"""Read limits from the target platform; never substitute copied platform values."""
import warnings


def get_limits(base_url: str, token: str, app_id: str) -> dict | None:
    import httpx
    try:
        response = httpx.get(
            f"{base_url.rstrip('/')}/api/v1/builder/apps/{app_id}/limits",
            headers={"Authorization": f"Bearer {token}"}, timeout=10,
        )
        if response.status_code in (404, 503):
            warnings.warn("平台目前無法提供開發限制；不使用舊版固定數值，請檢查編譯回應。", stacklevel=2)
            return None
        response.raise_for_status()
        data = response.json()
        vfs = data["vfs"]
        for key in ("max_file_count", "max_file_size_bytes", "build_timeout_ms"):
            if type(vfs[key]) is not int or vfs[key] <= 0:
                raise ValueError(f"invalid vfs limit: {key}")
        return data
    except (httpx.TransportError, ValueError, KeyError, TypeError) as exc:
        warnings.warn(f"開發限制查詢失敗（{type(exc).__name__}）；額度未知，請檢查編譯回應。", stacklevel=2)
        return None


def check_vfs(vfs: dict[str, str], limits: dict | None) -> list[dict]:
    """Preflight the merged VFS. Count overflow blocks; skipped inputs are warnings."""
    if limits is None:
        return []  # unknown, never interpret this as a compiler skip report
    from pathlib import PurePosixPath
    cap = limits["vfs"]
    counted = 0
    skipped = []
    for path, content in sorted(vfs.items()):
        name = PurePosixPath(path).name
        reason = None
        if "node_modules" in path:
            reason = "node_modules_filtered"
        elif name.startswith("tsconfig.") and name.endswith(".json"):
            reason = "tsconfig_stripped"
        else:
            counted += 1
            depth = 0
            escaped = False
            for part in PurePosixPath(path.lstrip("/")).parts:
                if part == "..":
                    depth -= 1
                    escaped = escaped or depth < 0
                elif part != ".":
                    depth += 1
            if escaped or depth == 0:
                reason = "path_traversal"
            elif len(content.encode("utf-8")) > cap["max_file_size_bytes"]:
                reason = "exceeds_max_file_size"
        if reason:
            skipped.append({"path": path, "size": len(content.encode("utf-8")), "reason": reason})
    if counted > cap["max_file_count"]:
        raise ValueError(f"合併後 VFS 檔案數 {counted} 超過平台上限 {cap['max_file_count']}")
    return skipped
