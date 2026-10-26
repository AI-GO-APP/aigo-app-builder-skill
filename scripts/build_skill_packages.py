"""Build isolated Builder/learning zip artifacts; never installs or updates skills.

python scripts/build_skill_packages.py --variant both --output <new-directory>
After reviewing changed technical sources, refresh the lock explicitly:
python scripts/build_skill_packages.py --review-sources --review-note <reason>
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
LOCK = "learning/sources.lock.json"
LEARNING_INPUTS = ("SKILL.md", "VERSION", "references/teaching.md", "references/practice-area.md",
                   "references/technical-use.md", "references/operations.md", "exercises/practice-sequence.md",
                   "scripts/check_update.py", "scripts/learning_scope.py")
TOOLS = ("aigo_auth.py", "aigo_cli_check.py", "aigo_limits.py", "aigo_scaffold.py", "aigo_sync.py",
         "aigo_compile.py", "aigo_publish.py", "aigo_typecheck.py", "pyproject.toml", "uv.lock")
# Only these technical sections are exported. Workflow/admin/report/updater files never enter learning.
EXCERPTS = {
    "technical/vfs.md": ("references/custom-app-dev-guide.md", [
        "## 3. VFS 標準檔案樹", "## 4. 程式碼注入 API", "## 5. 編譯 API",
        "## 9. Shadow DOM CSS 規範", "## 10. VFS 注入規範"]),
    "technical/actions.md": ("references/custom-app-dev-guide.md", ["## 7. Server-Side Actions"]),
    "technical/data-placement.md": ("references/custom-app-dev-guide.md", [
        "## 19. 資料承載體總決策（★ SSOT——所有分流指引以本節為準）"]),
    "technical/data-references.md": ("references/custom-app-dev-guide.md", ["## 20. Data Reference 探索 API"]),
    "technical/frontend-states.md": ("references/custom-app-dev-guide.md", [
        "## 30. 前端資料狀態：載入中／有資料／空資料／錯誤，加上送出中（★ 核心規則 30 的寫法）"]),
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read(root: Path, name: str) -> bytes:
    rel = PurePosixPath(name)
    if rel.is_absolute() or ".." in rel.parts or "\\" in name or ":" in name:
        raise ValueError(f"Unsafe path: {name}")
    path = root / name
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Symlink/outside source refused: {name}")
    return path.read_bytes()


def source_names() -> list[str]:
    return sorted({"VERSION", *(f"scripts/{name}" for name in TOOLS),
                   *(path for path, _ in EXCERPTS.values())})


def source_hashes(root: Path) -> dict[str, str]:
    return {name: digest(read(root, name)) for name in source_names()}


def review_sources(root: Path, note: str) -> dict:
    if not note.strip():
        raise ValueError("Review note required")
    lock = {"schema": 1, "builder_version": read(root, "VERSION").decode().strip(),
            "review_note": note, "sources": source_hashes(root)}
    (root / LOCK).write_text(json.dumps(lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return lock


def reviewed_sources(root: Path) -> dict:
    lock = json.loads(read(root, LOCK))
    if lock.get("schema") != 1 or lock.get("sources") != source_hashes(root):
        raise ValueError("Shared sources changed or lock incomplete; review compatibility before refreshing sources.lock.json")
    if lock["builder_version"] != read(root, "VERSION").decode().strip():
        raise ValueError("Builder version does not match reviewed sources")
    return lock


def sections(text: str) -> dict[str, str]:
    """Recognize H2 boundaries outside fenced code; examples contain Markdown headings."""
    lines = text.splitlines(keepends=True)
    starts: list[tuple[str, int]] = []
    fence = ""
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        marker = re.match(r"(`{3,}|~{3,})", stripped)
        if marker:
            if not fence:
                fence = marker[1][0]
            elif marker[1][0] == fence:
                fence = ""
        if not fence and line.startswith("## "):
            heading = line.strip()
            if any(h == heading for h, _ in starts):
                raise ValueError(f"Duplicate source heading: {heading}")
            starts.append((heading, i))
    return {heading: "".join(lines[start:starts[n + 1][1] if n + 1 < len(starts) else len(lines)])
            for n, (heading, start) in enumerate(starts)}


def excerpt(root: Path, source: str, headings: list[str]) -> bytes:
    available = sections(read(root, source).decode("utf-8"))
    try:
        body = "\n".join(available[heading] for heading in headings)
    except KeyError as exc:
        raise ValueError(f"Reviewed heading missing: {source} {exc}") from exc
    # References into the professional workflow must not become student context routing.
    # Explicitly label unavailable supplemental material; do not pretend links resolve.
    body = re.sub(r"(?:references/)?([A-Za-z][A-Za-z0-9_-]*)\.md",
                  lambda m: f"教師補充〈{m[1]}〉（未附帶；本題需要時請教師核對）", body)
    body = re.sub(r"(?:scripts/)?((?:aigo_[a-z_]+|check_update|report_issue)\.py)",
                  lambda m: m[0] if m[1] in TOOLS else f"教師補充工具〈{m[1][:-3]}〉（未附帶）", body)
    return ("# 同源技術摘錄\n\n原章節編號保留；資料來源雜湊見 PACKAGE.json。這是技術參考，不是執行授權。\n"
            "教師補充代表未附帶的進階資料，不要尋找一般版入口；歷史測試不代表當前租戶驗證。\n\n" + body).encode("utf-8")


def learning_files(root: Path) -> dict[str, bytes]:
    lock = reviewed_sources(root)
    files = {name: read(root, f"learning/{name}") for name in LEARNING_INPUTS}
    for name in TOOLS:
        files[f"scripts/{name}"] = read(root, f"scripts/{name}")
    for name, (source, headings) in EXCERPTS.items():
        files[name] = excerpt(root, source, headings)
    files["LICENSE"] = read(root, "LICENSE")
    check_dependencies(files)
    check_student_links(files)
    meta = {"schema": 1, "skill": "aigo-learning", "version": files["VERSION"].decode().strip(),
            "builder_version": lock["builder_version"], "review_note": lock["review_note"],
            "update_policy": "teacher-reviewed-package-only", "sources": lock["sources"],
            "excerpts": EXCERPTS, "files": {name: digest(data) for name, data in sorted(files.items())}}
    files["PACKAGE.json"] = (json.dumps(meta, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    return files


def check_dependencies(files: dict[str, bytes]) -> None:
    for name, data in files.items():
        if not name.endswith(".py"):
            continue
        for node in ast.walk(ast.parse(data, filename=name)):
            modules = ([node.module] if isinstance(node, ast.ImportFrom)
                       else [entry.name for entry in node.names] if isinstance(node, ast.Import) else [])
            for module in modules:
                if module and module.startswith("aigo_") and f"scripts/{module}.py" not in files:
                    raise ValueError(f"Missing tool dependency: {name} -> {module}")


def check_student_links(files: dict[str, bytes]) -> None:
    for name, data in files.items():
        if not name.endswith(".md"):
            continue
        for link in re.findall(r"\]\(([^)]+)\)", data.decode("utf-8")):
            if link.startswith(("https://", "http://", "#")):
                continue
            path = PurePosixPath(name).parent / link.split("#")[0]
            if ".." in path.parts or path.as_posix() not in files:
                raise ValueError(f"Student reference not self-contained: {name} -> {link}")


def builder_files(root: Path) -> dict[str, bytes]:
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0")
    # The professional entry, tools and references are copied byte-for-byte, with no student subtree.
    roots = {".gitignore", "SKILL.md", "CONTEXT.md", "VERSION", "README.md", "CHANGELOG.md", "LICENSE"}
    prefixes = ("references/", "resources/", "scripts/", "tests/", "evals/", "docs/")
    excluded = ("evals/learning/", "docs/learning/", "tests/test_learning", "scripts/build_skill_packages.py")
    return {name: read(root, name) for name in tracked if name and
            (name in roots or name.startswith(prefixes)) and not name.startswith(excluded)}


def build(root: Path, output: Path, variant: str = "both") -> dict[str, dict]:
    if variant not in {"builder", "learning", "both"}:
        raise ValueError("Unknown variant")
    # Validate all inputs before creating output. Never overwrite an existing release/install/workspace.
    bundles = {}
    if variant in {"builder", "both"}:
        bundles["aigo-builder"] = builder_files(root)
    if variant in {"learning", "both"}:
        bundles["aigo-learning"] = learning_files(root)
    if output.resolve() == root.resolve() or output.resolve().is_relative_to(root / "learning"):
        raise ValueError("Output must not be the source skill directory")
    output.mkdir(parents=True, exist_ok=False)
    receipts = {}
    for skill, files in bundles.items():
        dest = output / skill
        for name, data in sorted(files.items()):
            path = dest / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        archive = output / f"{skill}.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for name, data in sorted(files.items()):
                item = zipfile.ZipInfo(f"{skill}/{name}", date_time=(2020, 1, 1, 0, 0, 0))
                item.compress_type = zipfile.ZIP_DEFLATED
                item.external_attr = 0o100644 << 16
                zf.writestr(item, data)
        receipts[skill] = {"archive": archive.name, "sha256": digest(archive.read_bytes()), "files": len(files)}
    (output / "RECEIPTS.json").write_text(json.dumps(receipts, indent=2) + "\n", encoding="utf-8")
    return receipts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=("builder", "learning", "both"), default="both")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--review-sources", action="store_true")
    parser.add_argument("--review-note", default="")
    args = parser.parse_args()
    try:
        if args.review_sources:
            review_sources(ROOT, args.review_note)
            print("Reviewed-source lock written; no installed skills changed.")
        elif args.output:
            print(json.dumps(build(ROOT, args.output, args.variant), indent=2))
        else:
            parser.error("--output required unless reviewing sources")
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Build failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
