"""Export/verify packages; digest binds the whole manifest except itself, not only files."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path, PurePosixPath

from builder_entry import render_entry

FORMAT = "aigo-knowledge-manifest/1"


def digest(data):
    return hashlib.sha256(data).hexdigest()
def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
def safe_path(value):
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts
def reject_source_links(root, paths):
    for path in paths:
        current = path
        while True:
            if current.is_symlink():
                raise ValueError(f"source symlink rejected: {current.relative_to(root)}")
            if current == root:
                break
            if root not in current.parents:
                raise ValueError(f"source escapes root: {path}")
            current = current.parent
def parse_references(text, actual_paths=None):
    references = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 5 or cells[0] in {"檔案", "---"} or set(cells[0]) == {"-"}:
            continue
        path = cells[0].strip("`")
        if path.startswith("references/"):
            references.append({"path": path, "load": cells[2], "entry": cells[3], "boundary": cells[4]})
    references.sort(key=lambda item: item["path"])
    indexed = [item["path"] for item in references]
    if actual_paths is not None and indexed != sorted(actual_paths):
        missing = sorted(set(actual_paths) - set(indexed))
        stale = sorted(set(indexed) - set(actual_paths))
        raise ValueError(f"reference index mismatch; missing={missing}, stale={stale}")
    if len(indexed) != len(set(indexed)):
        raise ValueError("reference index contains duplicate paths")
    return references
def git_value(root, *args):
    try:
        result = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                                text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None
def package_digest(manifest):
    content = {key: value for key, value in manifest.items() if key != "package_digest"}
    canonical = json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return digest(canonical.encode("utf-8"))


def export_package(root, out, commit=None):
    root = root.absolute()
    out = out.absolute()
    if out.is_symlink():
        raise ValueError(f"output directory symlink rejected: {out}")
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise ValueError(f"output directory is not empty: {out}")

    references_dir = root / "references"
    reference_paths = sorted(references_dir.glob("*.md"))
    sources = [root, root / "SKILL.md", root / "builder/ENTRY.md", root / "VERSION",
               root / "CONTEXT.md", root / "LICENSE", root / "builder/compat.json",
               references_dir, *reference_paths]
    reject_source_links(root, sources)
    for source in sources[1:]:
        if not source.exists():
            raise ValueError(f"source missing: {source.relative_to(root)}")

    commit = commit or git_value(root, "rev-parse", "HEAD")
    if not commit:
        raise ValueError("cannot determine commit; pass --commit SHA")
    status = git_value(root, "status", "--porcelain")
    dirty = None if status is None else bool(status)
    compat = json.loads((root / "builder/compat.json").read_text(encoding="utf-8"))
    actual_refs = [path.relative_to(root).as_posix() for path in reference_paths]
    index_text = (references_dir / "reference-index.md").read_text(encoding="utf-8")
    references = parse_references(index_text, actual_refs)

    content = {
        "core.md": render_entry(root).encode(),
        "CONTEXT.md": (root / "CONTEXT.md").read_bytes(),
        "LICENSE": (root / "LICENSE").read_bytes(),
        "compat.json": (root / "builder/compat.json").read_bytes(),
    }
    for source in reference_paths:
        content[source.relative_to(root).as_posix()] = source.read_bytes()
    files = [{"path": path, "sha256": digest(data), "bytes": len(data)}
             for path, data in sorted(content.items())]
    manifest = {
        "format": FORMAT, "skill_name": "aigo-builder",
        "skill_version": (root / "VERSION").read_text(encoding="utf-8").strip(),
        "commit": commit, "dirty": dirty, "entry": "core.md",
        "license": {"spdx": "MIT", "file": "LICENSE"}, "compat": compat,
        "files": files, "references": references,
    }
    manifest["package_digest"] = package_digest(manifest)

    out.mkdir(parents=True, exist_ok=True)
    for relative, data in content.items():
        target = out / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    (out / "manifest.json").write_bytes(json_bytes(manifest))


def package_entries(directory):
    entries, links = set(), []
    if directory.is_symlink():
        links.append(".")
        return entries, links
    for base, dirs, files in os.walk(directory, followlinks=False):
        base_path = Path(base)
        for name in dirs + files:
            path = base_path / name
            relative = path.relative_to(directory).as_posix()
            if path.is_symlink():
                links.append(relative)
            elif path.is_file():
                entries.add(relative)
    return entries, links


def verify_package(directory):
    errors = []
    actual, links = package_entries(directory)
    errors.extend(f"symlink rejected: {path}" for path in links)
    if links:
        return errors, None
    manifest_path = directory / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("top level is not an object")
    except (OSError, ValueError) as error:
        errors.append(f"manifest.json: {error}")
        return errors, None
    if manifest.get("format") != FORMAT:
        errors.append(f"unknown format: {manifest.get('format')!r}")

    for label, value in (("entry", manifest.get("entry")),
                         ("license.file", manifest.get("license", {}).get("file")
                          if isinstance(manifest.get("license"), dict) else None)):
        if not safe_path(value):
            errors.append(f"unsafe {label} path: {value!r}")

    files = manifest.get("files")
    if not isinstance(files, list):
        errors.append("files must be a list")
        files = []
    listed = set()
    for number, item in enumerate(files):
        if not isinstance(item, dict):
            errors.append(f"files[{number}] must be an object")
            continue
        relative = item.get("path")
        if not safe_path(relative) or relative == "manifest.json":
            errors.append(f"unsafe files path: {relative!r}")
            continue
        if relative in listed:
            errors.append(f"duplicate files path: {relative}")
            continue
        listed.add(relative)
        target = directory / relative
        if not target.is_file() or target.is_symlink():
            errors.append(f"missing file: {relative}")
            continue
        data = target.read_bytes()
        actual_hash = digest(data)
        if item.get("sha256") != actual_hash:
            errors.append(f"sha256 mismatch: {relative}")
        if item.get("bytes") != len(data):
            errors.append(f"bytes mismatch: {relative}")

    for relative in sorted((actual - {"manifest.json"}) - listed):
        errors.append(f"unlisted file: {relative}")
    for relative in sorted(listed - (actual - {"manifest.json"})):
        if not any(error == f"missing file: {relative}" for error in errors):
            errors.append(f"missing file: {relative}")
    if manifest.get("package_digest") != package_digest(manifest):
        errors.append("package_digest mismatch")

    references = manifest.get("references")
    if not isinstance(references, list):
        errors.append("references must be a list")
        references = []
    else:
        if not references:
            errors.append("references list is empty")
        for item in references:
            relative = item.get("path") if isinstance(item, dict) else None
            if not safe_path(relative):
                errors.append(f"unsafe references path: {relative!r}")
    reference_paths = {item["path"] for item in references
                       if isinstance(item, dict) and safe_path(item.get("path"))}
    index = directory / "references/reference-index.md"
    indexed_reference_paths = ({item["path"] for item in
                                parse_references(index.read_text(encoding="utf-8"))}
                               if index.is_file() and not index.is_symlink() else set())
    file_reference_paths = {path for path in listed if path.startswith("references/")}
    if indexed_reference_paths != reference_paths or indexed_reference_paths != file_reference_paths:
        missing = sorted((indexed_reference_paths - reference_paths) |
                         (indexed_reference_paths - file_reference_paths))
        extra = sorted((reference_paths | file_reference_paths) - indexed_reference_paths)
        errors.append(f"references list does not match reference-index: missing={missing} extra={extra}")
    return errors, manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export")
    export.add_argument("--out", type=Path, required=True)
    export.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    export.add_argument("--commit")
    verify = commands.add_parser("verify")
    verify.add_argument("directory", type=Path)
    show = commands.add_parser("print-manifest")
    show.add_argument("directory", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "export":
            export_package(args.root, args.out, args.commit)
        elif args.command == "verify":
            errors, manifest = verify_package(args.directory)
            if errors:
                for error in errors:
                    print(f"ERROR: {error}", file=sys.stderr)
                return 1
            print(f"OK {manifest['skill_version']} {manifest['commit']} {manifest['package_digest'][:16]}")
        else:
            manifest = json.loads((args.directory / "manifest.json").read_text(encoding="utf-8"))
            print(f"{manifest['skill_name']} {manifest['skill_version']} {manifest['commit']} "
                  f"{manifest['package_digest']}")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
