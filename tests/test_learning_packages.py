"""Offline regression tests: isolation, source drift, executable scope checks, release integrity."""
from __future__ import annotations

import contextlib
import copy
import io
import json
import runpy
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_skill_packages as pack

scope = runpy.run_path(str(ROOT / "learning/scripts/learning_scope.py"))
integrity = runpy.run_path(str(ROOT / "learning/scripts/check_update.py"))
ROLE = "11111111-1111-4111-8111-111111111111"
APP = "22222222-2222-4222-8222-222222222222"
OTHER = "33333333-3333-4333-8333-333333333333"
BASE = "https://course.ai-go.app"


class PackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = pack.learning_files(ROOT)

    def make_package(self, dest):
        for name, data in self.files.items():
            path = dest / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

    def test_sources_are_reviewed_and_have_complete_dependency_closure(self):
        pack.reviewed_sources(ROOT)
        pack.check_dependencies(self.files)
        pack.check_student_links(self.files)

    def test_student_updater_is_distinct_and_admin_workflows_not_exported(self):
        self.assertNotEqual(self.files["scripts/check_update.py"], (ROOT / "scripts/check_update.py").read_bytes())
        for omitted in ("references/member-admin.md", "references/pre-report-self-grill.md",
                        "scripts/report_issue.py", "SKILL-builder.md", "learning/SKILL.md"):
            self.assertNotIn(omitted, self.files)
        with self.assertRaises(ValueError):
            pack.check_dependencies({"scripts/test.py": b"from aigo_missing import run\n"})

    def test_shared_tools_are_exact_source_bytes(self):
        for name in pack.TOOLS:
            self.assertEqual(self.files[f"scripts/{name}"], (ROOT / "scripts" / name).read_bytes())

    def test_original_professional_files_unchanged_and_package_has_single_entry(self):
        original = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", "main"], cwd=ROOT).decode().splitlines()
        for name in original:
            expected = subprocess.check_output(["git", "show", f"main:{name}"], cwd=ROOT)
            self.assertEqual((ROOT / name).read_bytes(), expected, name)
        professional = pack.builder_files(ROOT)
        for name in original:
            self.assertEqual(professional[name], (ROOT / name).read_bytes(), name)
        self.assertEqual([n for n in professional if n.endswith("SKILL.md")], ["SKILL.md"])

    def test_source_drift_blocks_student_build_before_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "source"
            root.mkdir()
            for name in [*pack.source_names(), pack.LOCK]:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / name).read_bytes())
            source = root / "scripts/aigo_sync.py"
            source.write_bytes(source.read_bytes() + b"\n# changed upstream\n")
            output = Path(temp) / "release"
            with self.assertRaisesRegex(ValueError, "Shared sources changed"):
                pack.build(root, output, "learning")
            self.assertFalse(output.exists())

    def test_unlisted_student_scripts_and_notes_are_not_distributed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in [*pack.source_names(), pack.LOCK, "LICENSE",
                         *(f"learning/{name}" for name in pack.LEARNING_INPUTS)]:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / name).read_bytes())
            (root / "learning/scripts/report_issue.py").write_text("raise Exception('must not ship')")
            (root / "learning/references/student-private-notes.md").write_text("unlisted private notes")
            files = pack.learning_files(root)
            self.assertNotIn("scripts/report_issue.py", files)
            self.assertNotIn("references/student-private-notes.md", files)

    def test_missing_or_renamed_heading_fails_instead_of_empty_excerpt(self):
        with self.assertRaisesRegex(ValueError, "heading missing"):
            pack.excerpt(ROOT, "references/custom-app-dev-guide.md", ["## renamed"])

    def test_code_fence_headings_do_not_split_source(self):
        text = "## One\n```md\n## example\n```\nbody\n## Two\ntail\n"
        result = pack.sections(text)
        self.assertEqual(set(result), {"## One", "## Two"})
        self.assertIn("## example", result["## One"])

    def test_duplicate_heading_fails(self):
        with self.assertRaises(ValueError):
            pack.sections("## One\na\n## One\nb\n")

    def test_bare_unshipped_tool_in_excerpt_is_explicitly_unavailable(self):
        for name, data in self.files.items():
            if name.startswith("technical/"):
                self.assertNotIn(b"aigo_data.py", data, name)

    def test_malformed_manifest_shapes_are_reported_as_integrity_failure(self):
        for value in ([], None, 3, {"schema": 1, "skill": "aigo-learning"}):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                (root / "PACKAGE.json").write_text(json.dumps(value), encoding="utf-8")
                with self.assertRaises(ValueError):
                    integrity["validate"](root)

    def test_archive_determinism_and_both_package_integrity(self):
        with tempfile.TemporaryDirectory() as temp:
            a, b = Path(temp) / "a", Path(temp) / "b"
            first = pack.build(ROOT, a)
            second = pack.build(ROOT, b)
            self.assertEqual(first, second)
            self.assertEqual(integrity["validate"](a / "aigo-learning")["integrity"], "passed")
            before = (a / "aigo-learning.zip").read_bytes()
            with self.assertRaises(FileExistsError):
                pack.build(ROOT, a)
            self.assertEqual(before, (a / "aigo-learning.zip").read_bytes())

    def test_integrity_detects_mutation_missing_file_and_extra_file(self):
        for change in ("modify", "missing", "extra"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temp:
                dest = Path(temp)
                self.make_package(dest)
                if change == "modify":
                    (dest / "SKILL.md").write_text("altered", encoding="utf-8")
                elif change == "missing":
                    (dest / "VERSION").unlink()
                else:
                    (dest / "unexpected.env").write_text("not-a-real-secret", encoding="utf-8")
                with self.assertRaises(ValueError):
                    integrity["validate"](dest)

    def test_integrity_refuses_traversal_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_package(root)
            meta = json.loads((root / "PACKAGE.json").read_text(encoding="utf-8"))
            meta["files"]["../outside"] = "0" * 64
            (root / "PACKAGE.json").write_text(json.dumps(meta))
            with self.assertRaisesRegex(ValueError, "路徑無效"):
                integrity["validate"](root)

    def test_student_status_is_offline_and_does_not_write_registry(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_package(root)
            before = {n: (root / n).read_bytes() for n in self.files}
            with mock.patch("socket.socket", side_effect=AssertionError("Network forbidden")):
                result = integrity["validate"](root)
            self.assertFalse(result["network_used"])
            self.assertEqual(before, {n: (root / n).read_bytes() for n in self.files})


class ScopeTests(unittest.TestCase):
    def setUp(self):
        self.profile = {"tenant_url": BASE, "student_email": "student@example.test", "role_id": ROLE,
                        "apps": {"practice": APP}}
        self.config = {"base_url": BASE, "email": "student@example.test",
                       "apps": {"practice": {"id": APP, "kind": "custom"}}}
        self.info = {"id": APP, "access_mode": "internal", "access_role_ids": [ROLE]}

    def local(self, alias="practice", base=BASE):
        return scope["check_local"](self.profile, self.config, base, alias)

    def test_exact_scope_passes_without_claiming_isolation(self):
        result = scope["check_remote"](self.local(), self.info)
        self.assertEqual(result["scope_check"], "passed")
        self.assertEqual(result["mutations"], 0)
        self.assertFalse(result["data_isolation_verified"])
        self.assertFalse(result["cross_role_access_verified"])

    def test_host_override_stops_before_auth(self):
        for host in ("https://other.ai-go.app", "https://ai-go.app", "http://course.ai-go.app",
                     "https://course.ai-go.app.evil.test", "https://course.ai-go.app/api/v1",
                     "https://user:pass@course.ai-go.app"):
            with self.subTest(host=host), self.assertRaises(ValueError):
                self.local(base=host)

    def test_unknown_or_implicit_app_refused(self):
        for alias in ("", "other", APP, "pract"):
            with self.subTest(alias=alias), self.assertRaises(ValueError):
                self.local(alias)

    def test_local_other_app_hosted_and_wrong_identity_refused(self):
        for field, value in (("id", OTHER), ("kind", "hosted")):
            config = copy.deepcopy(self.config)
            config["apps"]["practice"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                scope["check_local"](self.profile, config, BASE, "practice")
        self.config["email"] = "teacher@example.test"
        with self.assertRaises(ValueError):
            self.local()

    def test_unknown_or_broader_remote_audience_refused(self):
        for roles in (None, [], [OTHER], [ROLE, OTHER], "invalid", [None], ["not-uuid"]):
            info = {**self.info, "access_role_ids": roles}
            with self.subTest(roles=roles), self.assertRaises((ValueError, TypeError)):
                scope["check_remote"](self.local(), info)

    def test_incomplete_remote_and_external_refused(self):
        for info in ({}, {**self.info, "id": OTHER}, {**self.info, "access_mode": "external"}):
            with self.subTest(info=info), self.assertRaises(ValueError):
                scope["check_remote"](self.local(), info)

    def test_remote_teacher_token_refused(self):
        with self.assertRaises(ValueError):
            scope["check_identity"](self.local(), {"email": "teacher@example.test"})

    def test_null_identity_fields_fail_with_actionable_error(self):
        self.config["email"] = None
        with self.assertRaisesRegex(ValueError, "身分"):
            self.local()
        self.config["email"] = "student@example.test"
        with self.assertRaisesRegex(ValueError, "身分"):
            scope["check_identity"](self.local(), {"email": None})

    def test_cli_only_reads_identity_then_bound_app(self):
        with tempfile.TemporaryDirectory() as temp:
            ws = Path(temp)
            (ws / ".aigo").mkdir()
            (ws / ".aigo/config.json").write_text(json.dumps(self.config))
            (ws / ".aigo/learning.json").write_text(json.dumps(self.profile))
            fake_auth = types.SimpleNamespace(resolve_base_url=mock.Mock(return_value=BASE),
                                             get_token=mock.Mock(return_value="fake-test-token"),
                                             get_app_info=mock.Mock(return_value=self.info))
            response = types.SimpleNamespace(raise_for_status=mock.Mock(),
                                             json=mock.Mock(return_value={"email": self.profile["student_email"]}))
            fake_http = types.SimpleNamespace(get=mock.Mock(return_value=response))
            with mock.patch.dict(sys.modules, {"aigo_auth": fake_auth, "httpx": fake_http}), contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(scope["main"](["--workspace", str(ws), "--app", "practice"]), 0)
            fake_http.get.assert_called_once()
            fake_auth.get_app_info.assert_called_once_with(BASE, "fake-test-token", APP)
            self.assertNotIn("fake-test-token", out.getvalue())
            # A cached/inherited teacher identity is rejected before any App read.
            response.json.return_value = {"email": "teacher@example.test"}
            fake_auth.get_app_info.reset_mock()
            with mock.patch.dict(sys.modules, {"aigo_auth": fake_auth, "httpx": fake_http}), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(scope["main"](["--workspace", str(ws), "--app", "practice"]), 1)
            fake_auth.get_app_info.assert_not_called()
            # Invalid scope never authenticates or calls the API.
            fake_auth.get_token.reset_mock()
            with mock.patch.dict(sys.modules, {"aigo_auth": fake_auth, "httpx": fake_http}), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(scope["main"](["--workspace", str(ws), "--app", "other"]), 1)
            fake_auth.get_token.assert_not_called()


if __name__ == "__main__":
    unittest.main()
