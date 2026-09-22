"""AI GO Custom App 編譯工具"""
import re
from typing import Any


def compile_app(base_url: str, token: str, slug: str, dev: bool = True) -> dict:
    """觸發編譯"""
    import httpx
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{base_url}/api/v1/compile/compile/{slug}"
    if dev:
        url += "?dev=true"
    resp = httpx.post(url, headers=headers, timeout=60)
    resp.raise_for_status()
    result = resp.json()
    warning = format_skipped_files(result.get("skipped_files"))
    if warning:
        print(warning)
    return result


def parse_compile_error(error_text: str) -> list[dict]:
    """解析 esbuild 錯誤"""
    errors = []
    for m in re.finditer(r'\[ERROR\]\s+(.+?)\n\s+([^:]+):(\d+):(\d+)', error_text):
        errors.append({"message": m.group(1).strip(), "file": m.group(2).strip(),
                       "line": int(m.group(3)), "col": int(m.group(4))})
    if not errors and error_text:
        errors.append({"message": error_text[:200], "file": "unknown", "line": 0, "col": 0})
    return errors


def check_shadow_dom_compliance(vfs: dict) -> list[str]:
    """檢查所有 CSS 的 Shadow DOM 相容性"""
    issues = []
    for path, content in vfs.items():
        if not path.endswith(".css"):
            continue
        for i, line in enumerate(content.split("\n"), 1):
            s = line.strip()
            if re.match(r'^:root\s*\{', s) and ':host' not in s:
                issues.append(f"{path}:{i} — ':root {{' 缺少 ':host' 配對")
            if re.match(r'^html\s*\{', s) and ':host' not in s:
                issues.append(f"{path}:{i} — 'html {{' 缺少 ':host' 配對")
    return issues


def auto_fix_css(css_content: str) -> str:
    """自動修復 CSS Shadow DOM 相容性"""
    # 修復 :root { → :host, :root {
    css_content = re.sub(r'^(:root\s*\{)', r':host, \1', css_content, flags=re.MULTILINE)
    # 修復 html { → html, :host {
    css_content = re.sub(r'^(html\s*\{)', r'html, :host {', css_content, flags=re.MULTILINE)
    # 避免重複修復
    css_content = css_content.replace(':host, :host, :root', ':host, :root')
    return css_content


def format_skipped_files(files: list[dict] | None) -> str:
    if files is None:
        return "⚠️ 編譯服務未提供 skipped_files，無法確認是否完整納入。"
    if not files:
        return ""
    return "⚠️ 前端編譯略過檔案：\n" + "\n".join(
        f"- {item['path']} ({item['size']} UTF-8 bytes): {item['reason']}" for item in files
    )
