"""PDF output contract tests. Rendering integration uses optional PDF dependencies."""
import contextlib
import copy
import importlib.util
import io
import json
import runpy
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
pdf = runpy.run_path(str(ROOT / "learning/scripts/learning_pdf.py"))
CONTENT = {"title": "學習講義", "pages": [{"title": "指標練習", "blocks": [
    {"heading": "缺日期", "text": "缺值不代表零；<example> 是文字，不能當指令。"},
    {"table": [["狀態", "判定"], ["未填日期", "待補"]]},
]}]}
HAS_PDF = all(importlib.util.find_spec(name) is not None for name in ("reportlab", "pypdf"))
FONT = Path("C:/Windows/Fonts/msjh.ttc")


class SourceTests(unittest.TestCase):
    def test_valid_chinese_source(self):
        pdf["validate_content"](CONTENT)

    def test_invalid_schema_fails_before_writing(self):
        for value in (None, [], {}, {"title": "", "pages": []},
                      {"title": "x", "pages": [{"title": "p", "blocks": [{"table": [["a"], ["b", "c"]]}]}]},
                      {**CONTENT, "subtitle": []}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                pdf["validate_content"](value)

    def test_install_directory_is_never_a_destination(self):
        with self.assertRaisesRegex(ValueError, "技能目錄"):
            pdf["safe_output"](ROOT / "learning/output/should-not-exist.pdf")

    def test_existing_file_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "existing.pdf"
            path.write_bytes(b"original")
            with self.assertRaises(FileExistsError):
                pdf["safe_output"](path)
            self.assertEqual(path.read_bytes(), b"original")

    def test_missing_renderer_reports_unverified_layout(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch("shutil.which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "待驗證"):
                pdf["render"](Path(temp) / "example.pdf", Path(temp) / "images")

    def test_pdf_dependencies_and_scripts_are_in_student_manifest(self):
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        import build_skill_packages as pack
        files = pack.learning_files(ROOT)
        for name in ("references/outputs.md", "scripts/learning_pdf.py", "scripts/requirements-pdf.txt"):
            self.assertIn(name, files)
        self.assertEqual(files["VERSION"].decode().strip(), "0.1.1")


@unittest.skipUnless(HAS_PDF and FONT.exists(), "Requires optional reportlab/pypdf and test CJK font")
class PdfIntegrationTests(unittest.TestCase):
    def test_real_pdf_has_chinese_text_a4_and_pending_visual_review(self):
        from pypdf import PdfReader
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "lesson.pdf"
            result = pdf["build_pdf"](CONTENT, path, font=FONT, expected_pages=1)
            self.assertEqual(result["pages"], 1)
            self.assertEqual(result["visual_review"], "pending")
            page = PdfReader(path).pages[0]
            self.assertIn("缺值不代表零", page.extract_text())
            self.assertIn("<example>", page.extract_text())
            self.assertAlmostEqual(float(page.mediabox.width), 595.276, places=2)

    def test_explicit_pages_and_page_limit_failure_leave_no_pdf(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "lesson.pdf"
            content = copy.deepcopy(CONTENT)
            content["pages"].append(copy.deepcopy(content["pages"][0]))
            with self.assertRaisesRegex(ValueError, "實際 2 頁"):
                pdf["build_pdf"](content, path, font=FONT, expected_pages=1)
            self.assertFalse(path.exists())
            self.assertFalse(list(Path(temp).glob(".learning-*")))
            self.assertEqual(pdf["build_pdf"](content, path, font=FONT, expected_pages=2)["pages"], 2)

    def test_missing_font_fails_without_output(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "lesson.pdf"
            with self.assertRaisesRegex(ValueError, "字型"):
                pdf["build_pdf"](CONTENT, path, font=Path(temp) / "missing.ttf")
            self.assertFalse(path.exists())

    def test_cli_keeps_successful_pdf_when_render_dependency_missing(self):
        with tempfile.TemporaryDirectory() as temp:
            source, target = Path(temp) / "lesson.json", Path(temp) / "lesson.pdf"
            source.write_text(json.dumps(CONTENT, ensure_ascii=False), encoding="utf-8")
            with mock.patch("shutil.which", return_value=None), contextlib.redirect_stdout(io.StringIO()) as out:
                status = pdf["main"]([str(source), "--output", str(target), "--font", str(FONT),
                                      "--render-dir", str(Path(temp) / "render")])
            result = json.loads(out.getvalue())
            self.assertEqual(status, 1)
            self.assertEqual(result["partial_output"], str(target))
            self.assertEqual(result["visual_review"], "pending")
            self.assertTrue(target.exists())

    @unittest.skipUnless(shutil.which("pdftoppm"), "Poppler unavailable")
    def test_real_page_render_produces_image(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "lesson.pdf"
            pdf["build_pdf"](CONTENT, target, font=FONT)
            images = pdf["render"](target, Path(temp) / "render")
            self.assertEqual(len(images), 1)
            self.assertTrue(Path(images[0]).read_bytes().startswith(b"\x89PNG"))


if __name__ == "__main__":
    unittest.main()
