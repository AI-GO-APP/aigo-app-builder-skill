"""Offline contracts for shared rules and their on-demand reference index."""
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BEGIN = "<!-- shared-rules:begin -->"
END = "<!-- shared-rules:end -->"
TOPICS = {"hashrouter", "protected_sdk", "python_action", "data_reference", "shadow_dom"}


def extract_shared_rules(text: str) -> str:
    """Return the content between the shared-rules markers."""
    begin = text.index(BEGIN) + len(BEGIN)
    end = text.index(END, begin)
    return text[begin:end].strip()


def parse_reference_index(text: str) -> list[dict[str, str]]:
    rows = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 5 or cells[0] in {"檔案", "---"} or set(cells[0]) == {"-"}:
            continue
        rows.append(dict(zip(("檔案", "用途", "載入時機", "入口", "邊界"), cells)))
    return rows


class SharedRulesContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        cls.context = (ROOT / "CONTEXT.md").read_text(encoding="utf-8")
        cls.samples = json.loads(
            (ROOT / "tests/fixtures/shared-rules/samples.json").read_text(encoding="utf-8")
        )
        index_path = ROOT / "references/reference-index.md"
        cls.index = index_path.read_text(encoding="utf-8") if index_path.exists() else ""

    def test_shared_rule_markers_are_exactly_one_pair(self):
        self.assertEqual(self.skill.count(BEGIN), 1)
        self.assertEqual(self.skill.count(END), 1)
        self.assertLess(self.skill.index(BEGIN), self.skill.index(END))

    def test_shared_rule_block_is_nonempty_and_has_required_content(self):
        block = extract_shared_rules(self.skill)
        self.assertTrue(block)
        self.assertIn("核心規則", block)
        self.assertIn("ctx.http.call", block)

    def test_samples_cover_required_topics(self):
        self.assertGreaterEqual(len(self.samples), 6)
        self.assertTrue(TOPICS.issubset({sample["topic"] for sample in self.samples}))

    def test_samples_have_the_contract_shape(self):
        expected = {"rule_id", "topic", "source", "anchor", "must_contain"}
        for sample in self.samples:
            with self.subTest(rule_id=sample.get("rule_id")):
                self.assertEqual(set(sample), expected)
                self.assertIn(sample["topic"], TOPICS)
                self.assertTrue(all(isinstance(sample[key], str) and sample[key] for key in expected - {"must_contain"}))
                self.assertTrue(sample["must_contain"])
                self.assertTrue(all(isinstance(fragment, str) and fragment for fragment in sample["must_contain"]))

    def test_sample_sources_and_anchors_exist(self):
        for sample in self.samples:
            with self.subTest(rule_id=sample["rule_id"]):
                source = ROOT / sample["source"]
                self.assertTrue(source.is_file(), sample["source"])
                self.assertIn(sample["anchor"], source.read_text(encoding="utf-8"))

    def test_sample_fragments_exist_verbatim_in_source(self):
        for sample in self.samples:
            text = (ROOT / sample["source"]).read_text(encoding="utf-8")
            for fragment in sample["must_contain"]:
                with self.subTest(rule_id=sample["rule_id"], fragment=fragment):
                    self.assertIn(fragment, text)

    def test_reference_index_file_set_matches_repository(self):
        rows = parse_reference_index(self.index)
        actual = {row["檔案"].strip("`") for row in rows}
        expected = {"CONTEXT.md"} | {
            path.relative_to(ROOT).as_posix() for path in (ROOT / "references").glob("*.md")
        }
        self.assertEqual(actual, expected)
        self.assertEqual(len(actual), len(rows), "reference index must not contain duplicate file rows")

    def test_reference_index_rows_have_five_valid_columns(self):
        table_lines = [line for line in self.index.splitlines() if line.startswith("|")]
        self.assertGreaterEqual(len(table_lines), 3)
        for line in table_lines:
            with self.subTest(line=line):
                self.assertEqual(len(line.strip().strip("|").split("|")), 5)
        rows = parse_reference_index(self.index)
        self.assertTrue(rows)
        for row in rows:
            with self.subTest(file=row["檔案"]):
                self.assertTrue(all(row.values()))
                self.assertIn(row["載入時機"], {"核心", "按需"})
                self.assertIn(row["入口"], {"IDE", "Builder", "兩者"})
                self.assertIn(row["邊界"], {"資料結構", "業務資料", "無"})

    def test_new_docs_reference_only_existing_markdown_files(self):
        self.assertIn("## 資料結構與業務資料：邊界", self.context)
        section = self.context.split("## 資料結構與業務資料：邊界", 1)[-1]
        for source, text in (("references/reference-index.md", self.index), ("CONTEXT.md", section)):
            for target in re.findall(r"references/[A-Za-z0-9_.-]+\.md", text):
                with self.subTest(source=source, target=target):
                    self.assertTrue((ROOT / target).is_file())

    def test_skill_reference_table_links_reference_index(self):
        reference_table = self.skill.split("## 參考文件", 1)[1]
        self.assertIn("references/reference-index.md", reference_table)


if __name__ == "__main__":
    unittest.main()
