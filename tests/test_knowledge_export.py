"""Reproducible, offline knowledge-package export contracts."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/aigo_knowledge.py"
sys.path.insert(0, str(ROOT / "scripts"))
from builder_entry import render_entry


class KnowledgeExportTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.home = self.base / "home"
        self.home.mkdir()
        self.env = {**os.environ, "HOME": str(self.home)}

    def tearDown(self):
        self.temporary.cleanup()

    def run_cli(self, *args, check=False):
        with patch.dict(os.environ, {"HOME": str(self.home)}):
            return subprocess.run(
                ["python3", str(SCRIPT), *map(str, args)], cwd=self.base,
                env=self.env, capture_output=True, text=True, check=check,
            )

    def export(self, name="package"):
        out = self.base / name
        result = self.run_cli("export", "--root", ROOT, "--commit", "abc123", "--out", out)
        self.assertEqual(result.returncode, 0, result.stderr)
        return out

    def verify_fails(self, package, fragment):
        result = self.run_cli("verify", package)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(fragment, result.stdout + result.stderr)

    def rewrite_manifest_digest(self, path, manifest):
        unsigned = {key: value for key, value in manifest.items() if key != "package_digest"}
        canonical = json.dumps(unsigned, sort_keys=True, ensure_ascii=False,
                               separators=(",", ":"))
        manifest["package_digest"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        path.write_text(json.dumps(manifest))

    def test_standalone_source_has_no_update_or_network_dependencies(self):
        source = SCRIPT.read_text(encoding="utf-8")
        for forbidden in ("check_" + "update", "http" + "x", "url" + "lib", "sock" + "et"):
            self.assertNotIn(forbidden, source)
        self.assertLessEqual(len(source.splitlines()), 260)

    def test_two_exports_are_byte_reproducible(self):
        first, second = self.export("one"), self.export("two")
        self.assertEqual((first / "manifest.json").read_bytes(), (second / "manifest.json").read_bytes())
        self.assertEqual((first / "core.md").read_bytes(), (second / "core.md").read_bytes())

    def test_manifest_and_exported_content_match_sources(self):
        out = self.export()
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        references = sorted((ROOT / "references").glob("*.md"))
        self.assertEqual(manifest["skill_version"], (ROOT / "VERSION").read_text().strip())
        self.assertEqual(manifest["compat"], json.loads((ROOT / "builder/compat.json").read_text()))
        self.assertEqual(manifest["entry"], "core.md")
        self.assertEqual((out / "core.md").read_text(), render_entry(ROOT))
        self.assertEqual(len(manifest["references"]), len(references))
        self.assertEqual([item["path"] for item in manifest["files"]],
                         sorted(item["path"] for item in manifest["files"]))
        self.assertNotIn(str(ROOT), (out / "manifest.json").read_text())
        expected = {key: value for key, value in manifest.items() if key != "package_digest"}
        canonical = json.dumps(expected, sort_keys=True, ensure_ascii=False,
                               separators=(",", ":"))
        self.assertEqual(manifest["package_digest"],
                         hashlib.sha256(canonical.encode("utf-8")).hexdigest())

    def test_export_then_verify_succeeds(self):
        out = self.export()
        result = self.run_cli("verify", out)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stdout, r"^OK 1\.71\.0 abc123 [0-9a-f]{16}\n$")

    def test_modified_reference_reports_sha256(self):
        out = self.export()
        target = out / "references/dev-rules.md"
        target.write_text(target.read_text() + "x")
        result = self.run_cli("verify", out)
        self.assertNotEqual(result.returncode, 0)
        output = result.stdout + result.stderr
        self.assertIn("references/dev-rules.md", output)
        self.assertIn("sha256", output)

    def test_missing_reference_fails(self):
        out = self.export()
        (out / "references/dev-rules.md").unlink()
        self.verify_fails(out, "references/dev-rules.md")

    def test_extra_file_fails(self):
        out = self.export()
        (out / "extra.txt").write_text("extra")
        self.verify_fails(out, "extra.txt")

    def test_parent_traversal_manifest_path_fails(self):
        out = self.export()
        manifest_path = out / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["files"][0]["path"] = "../x.md"
        manifest_path.write_text(json.dumps(manifest))
        self.verify_fails(out, "../x.md")

    def test_symlink_in_package_fails(self):
        out = self.export()
        link = out / "link"
        try:
            link.symlink_to(out / "core.md")
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        self.verify_fails(out, "symlink")

    def test_export_and_verify_leave_home_and_repo_unchanged(self):
        before = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                                capture_output=True, text=True, check=True).stdout
        out = self.export()
        self.run_cli("verify", out, check=True)
        after = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                               capture_output=True, text=True, check=True).stdout
        self.assertEqual(list(self.home.iterdir()), [])
        self.assertEqual(after, before)

    def test_nonempty_output_is_rejected_without_changes(self):
        out = self.base / "occupied"
        out.mkdir()
        sentinel = out / "keep.txt"
        sentinel.write_bytes(b"untouched")
        result = self.run_cli("export", "--root", ROOT, "--commit", "abc123", "--out", out)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not empty", result.stdout + result.stderr)
        self.assertEqual(sentinel.read_bytes(), b"untouched")
        self.assertEqual(list(out.iterdir()), [sentinel])

    def test_unknown_manifest_format_fails(self):
        out = self.export()
        path = out / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest["format"] = "unknown/9"
        path.write_text(json.dumps(manifest))
        self.verify_fails(out, "format")

    def test_package_digest_mismatch_fails(self):
        out = self.export()
        path = out / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest["package_digest"] = "0" * 64
        path.write_text(json.dumps(manifest))
        self.verify_fails(out, "package_digest")

    def test_changed_skill_version_without_new_digest_fails(self):
        out = self.export()
        path = out / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest["skill_version"] = "9.99.9"
        path.write_text(json.dumps(manifest))
        self.verify_fails(out, "package_digest")

    def test_changed_compat_protocol_without_new_digest_fails(self):
        out = self.export()
        path = out / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest["compat"]["protocol_major"] = 2
        path.write_text(json.dumps(manifest))
        self.verify_fails(out, "package_digest")

    def test_empty_references_with_valid_digest_fails(self):
        out = self.export()
        path = out / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest["references"] = []
        self.rewrite_manifest_digest(path, manifest)
        self.verify_fails(out, "references")

    def test_reference_removed_only_from_manifest_with_valid_digest_fails(self):
        out = self.export()
        path = out / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest["references"] = manifest["references"][1:]
        self.rewrite_manifest_digest(path, manifest)
        self.verify_fails(out, "reference-index")

    def test_reference_index_entry_missing_from_package_fails(self):
        out = self.export()
        missing = "references/dev-rules.md"
        (out / missing).unlink()
        path = out / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest["files"] = [item for item in manifest["files"] if item["path"] != missing]
        manifest["references"] = [item for item in manifest["references"]
                                  if item["path"] != missing]
        self.rewrite_manifest_digest(path, manifest)
        self.verify_fails(out, "reference-index")


if __name__ == "__main__":
    unittest.main()
