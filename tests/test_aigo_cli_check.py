"""aigo_cli_check.py 的單元測試（stdlib unittest，零相依）。

執行：python3 -m unittest scripts/test_aigo_cli_check.py -v
"""

from __future__ import annotations

import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import aigo_cli_check as m  # noqa: E402


def _fake_bin(tmp: Path, body: str) -> Path:
    p = tmp / "aigo"
    p.write_text("#!/bin/sh\n" + body + "\n", encoding="utf-8")
    p.chmod(p.stat().st_mode | stat.S_IXUSR)
    return p


class ParseTests(unittest.TestCase):
    def test_parse_version_output_ok(self):
        self.assertEqual(m.parse_version_output("aigo 0.5.0\n"), "0.5.0")
        self.assertEqual(m.parse_version_output("aigo 0.4.0"), "0.4.0")
        self.assertEqual(m.parse_version_output("aigo v1.2.3"), "1.2.3")

    def test_parse_version_output_rejects_garbage(self):
        self.assertIsNone(m.parse_version_output(""))
        self.assertIsNone(m.parse_version_output("command not found"))
        self.assertIsNone(m.parse_version_output("aigo 0.5"))  # 不是三段 semver

    def test_parse_latest_tag(self):
        self.assertEqual(m.parse_latest_tag(json.dumps({"tag_name": "v0.5.0"})), "0.5.0")
        self.assertEqual(m.parse_latest_tag(json.dumps({"tag_name": "0.6.1"})), "0.6.1")
        self.assertIsNone(m.parse_latest_tag("not json"))
        self.assertIsNone(m.parse_latest_tag(json.dumps({"tag_name": "nightly"})))
        self.assertIsNone(m.parse_latest_tag(json.dumps({"message": "Not Found"})))

    def test_version_key_orders_numerically(self):
        self.assertLess(m.version_key("0.9.0"), m.version_key("0.10.0"))
        self.assertLess(m.version_key("0.4.0"), m.version_key("0.5.0"))


class EvaluateTests(unittest.TestCase):
    """evaluate() 是純函式：只看 (本地版本, 最新版本) 給結論，不碰網路與子行程。"""

    def test_missing_binary_is_blocking(self):
        r = m.evaluate(local=None, latest="0.5.0", found=False)
        self.assertEqual(r["status"], "missing")
        self.assertTrue(r["browser_login_blocked"])
        self.assertIn(m.INSTALL_CMD, r["message"])

    def test_unparseable_version_is_blocking(self):
        r = m.evaluate(local=None, latest="0.5.0", found=True)
        self.assertEqual(r["status"], "unknown_version")
        self.assertTrue(r["browser_login_blocked"])

    def test_below_min_blocks_browser_login_but_not_token(self):
        r = m.evaluate(local="0.4.0", latest="0.5.0", found=True)
        self.assertEqual(r["status"], "incompatible")
        self.assertTrue(r["browser_login_blocked"])
        self.assertIn("Deploy Token", r["message"])  # 明說 token 路徑不受影響
        self.assertIn(m.INSTALL_CMD, r["message"])
        self.assertIn("aigo update", r["message"])  # 明說別用 aigo update

    def test_at_min_and_latest_is_ok(self):
        r = m.evaluate(local="0.5.0", latest="0.5.0", found=True)
        self.assertEqual(r["status"], "ok")
        self.assertFalse(r["browser_login_blocked"])

    def test_behind_latest_but_compatible_is_advisory_only(self):
        r = m.evaluate(local="0.5.0", latest="0.6.0", found=True)
        self.assertEqual(r["status"], "behind_latest")
        self.assertFalse(r["browser_login_blocked"])

    def test_latest_unknown_fails_open(self):
        r = m.evaluate(local="0.5.0", latest=None, found=True)
        self.assertEqual(r["status"], "ok")
        self.assertFalse(r["browser_login_blocked"])
        self.assertTrue(r["latest_unknown"])
        r2 = m.evaluate(local="0.4.0", latest=None, found=True)
        self.assertEqual(r2["status"], "incompatible")  # 最低版門檻不靠網路

    def test_newer_than_latest_is_ok(self):
        r = m.evaluate(local="0.7.0", latest="0.6.0", found=True)
        self.assertEqual(r["status"], "ok")


class SubprocessTests(unittest.TestCase):
    def test_local_version_from_fake_binary(self):
        with tempfile.TemporaryDirectory() as d:
            p = _fake_bin(Path(d), 'echo "aigo 0.4.0"')
            self.assertEqual(m.local_version(str(p)), "0.4.0")

    def test_local_version_garbage_binary(self):
        with tempfile.TemporaryDirectory() as d:
            p = _fake_bin(Path(d), 'echo "something else"; exit 0')
            self.assertIsNone(m.local_version(str(p)))

    def test_local_version_failing_binary(self):
        with tempfile.TemporaryDirectory() as d:
            p = _fake_bin(Path(d), "exit 3")
            self.assertIsNone(m.local_version(str(p)))

    def test_local_version_hung_binary_is_bounded(self):
        with tempfile.TemporaryDirectory() as d:
            p = _fake_bin(Path(d), "sleep 30")
            with mock.patch.object(m, "VERSION_TIMEOUT", 0.5):
                self.assertIsNone(m.local_version(str(p)))

    def test_find_cli_prefers_path_then_local_bin(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d) / "home"
            (home / ".local" / "bin").mkdir(parents=True)
            fallback = _fake_bin(home / ".local" / "bin", 'echo "aigo 0.5.0"')
            with mock.patch.dict(os.environ, {"PATH": "/nonexistent", "HOME": str(home)}):
                with mock.patch.object(Path, "home", return_value=home):
                    self.assertEqual(m.find_cli(), str(fallback))
            with mock.patch.dict(os.environ, {"PATH": "/nonexistent"}):
                with mock.patch.object(Path, "home", return_value=Path(d) / "empty"):
                    self.assertIsNone(m.find_cli())


class MainTests(unittest.TestCase):
    def _run(self, argv, local, latest, found=True):
        buf = io.StringIO()
        with mock.patch.object(m, "find_cli", return_value="/x/aigo" if found else None), \
             mock.patch.object(m, "local_version", return_value=local), \
             mock.patch.object(m, "latest_version", return_value=latest), \
             redirect_stdout(buf):
            code = m.main(argv)
        return code, buf.getvalue()

    def test_exit_codes(self):
        self.assertEqual(self._run([], "0.5.0", "0.5.0")[0], 0)
        self.assertEqual(self._run([], "0.5.0", None)[0], 0)      # fail-open
        self.assertEqual(self._run([], "0.5.0", "0.6.0")[0], 0)   # advisory
        self.assertEqual(self._run([], "0.4.0", "0.5.0")[0], 1)
        self.assertEqual(self._run([], None, "0.5.0", found=False)[0], 1)

    def test_json_output(self):
        code, out = self._run(["--json"], "0.4.0", "0.5.0")
        data = json.loads(out)
        self.assertEqual(code, 1)
        self.assertEqual(data["status"], "incompatible")
        self.assertEqual(data["local"], "0.4.0")
        self.assertEqual(data["min_browser_login"], m.MIN_BROWSER_LOGIN_VERSION)

    def test_ok_is_one_line(self):
        code, out = self._run([], "0.5.0", "0.5.0")
        self.assertEqual(code, 0)
        self.assertEqual(len(out.strip().splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
