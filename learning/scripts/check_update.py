"""Student package integrity/status only. No network, updater registry or mutation."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath


def validate(root: Path) -> dict:
    root = root.resolve()
    meta = json.loads((root / "PACKAGE.json").read_text(encoding="utf-8"))
    if not isinstance(meta, dict) or meta.get("skill") != "aigo-learning" or meta.get("schema") != 1:
        raise ValueError("不是支援的 aigo-learning 套件")
    if not all(isinstance(meta.get(key), str) and meta[key] for key in ("version", "builder_version")):
        raise ValueError("套件版本欄位不完整")
    expected = meta.get("files")
    if not isinstance(expected, dict) or not expected:
        raise ValueError("套件檔案清單不完整")
    for name, digest in expected.items():
        rel = PurePosixPath(name)
        if rel.is_absolute() or ".." in rel.parts or "\\" in name or ":" in name:
            raise ValueError("套件路徑無效")
        path = root / name
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError(f"套件缺檔或路徑異常：{name}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f"套件內容已改變：{name}")
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()
              and not any(part in {"__pycache__", ".venv"} for part in p.relative_to(root).parts)}
    if actual != set(expected) | {"PACKAGE.json"}:
        raise ValueError("套件出現未列入清單的檔案；請教師檢查，不自動清除")
    return {"skill": meta["skill"], "version": meta["version"],
            "builder_version": meta["builder_version"], "integrity": "passed",
            "update_policy": "teacher-reviewed-package-only", "network_used": False}


def main() -> int:
    try:
        result = validate(Path(__file__).resolve().parents[1])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"integrity": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
