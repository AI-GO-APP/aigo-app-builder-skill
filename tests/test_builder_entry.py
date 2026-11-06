"""Offline Builder template, scenario and external IDE regression contracts."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from builder_entry import extract_shared_rules, render_entry

BEGIN = '<!-- shared-rules:begin -->'
END = '<!-- shared-rules:end -->'
INCLUDE = '<!-- include: SKILL.md#shared-rules -->'
SCOPES = {'app', 'protected_files', 'limits', 'tables', 'references', 'roles', 'services', 'schedules'}


class BuilderEntryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill = (ROOT / 'SKILL.md').read_text(encoding='utf-8')
        cls.entry = (ROOT / 'builder/ENTRY.md').read_text(encoding='utf-8')
        cls.rendered = render_entry(ROOT)
        cls.scenarios = {p.stem: json.loads(p.read_text(encoding='utf-8'))
                         for p in (ROOT / 'builder/scenarios').glob('*.json')}

    def test_exact_shared_block_inclusion(self):
        begin = self.skill.index(BEGIN) + len(BEGIN)
        end = self.skill.index(END)
        block = self.skill[begin:end].strip()
        before, after = self.entry.split(INCLUDE)
        self.assertEqual(self.rendered, (before + block + after).rstrip() + '\n')
        self.assertEqual(self.rendered.count(block), 1)
        self.assertNotIn(INCLUDE, self.rendered)

    def test_template_does_not_duplicate_shared_rules(self):
        samples = json.loads((ROOT / 'tests/fixtures/shared-rules/samples.json').read_text())
        block = extract_shared_rules(self.skill)
        selected = [s for s in samples if s['source'] == 'SKILL.md' and s['anchor'] in block]
        self.assertGreaterEqual(len(selected), 3)
        for sample in selected:
            for fragment in sample['must_contain']:
                with self.subTest(rule=sample['rule_id'], fragment=fragment):
                    self.assertNotIn(fragment, self.entry)
                    self.assertIn(fragment, self.rendered)

    def test_forbidden_ide_and_publish_commands(self):
        for fragment in ('check_update.py', 'aigo_auth.py', 'AIGO_PASSWORD', '.aigo/.env',
                         'uv run', 'reset --hard', 'full_deploy(', 'publish_app(', '--force',
                         'auto_rollback=true', 'confirm_removal=true', 'confirm_egress_gaps=true'):
            with self.subTest(fragment=fragment):
                self.assertNotIn(fragment, self.rendered)

    def test_builder_contract_vocabulary(self):
        for fragment in ('request_context', 'propose_operation', 'complete', 'not_requested',
                         'forbidden', 'unavailable', 'partial', 'no_modify', 'publish_request',
                         '最多 3 次', '最多 8 次', 'confirmed=true', '成功證據只來自平台回傳的結果'):
            self.assertIn(fragment, self.rendered)

    def test_template_and_script_size(self):
        self.assertTrue(self.entry.startswith('## 目錄\n'))
        self.assertEqual(self.entry.splitlines().count(INCLUDE), 1)
        self.assertLessEqual(len(self.entry.splitlines()), 220)
        self.assertLessEqual(len((ROOT / 'scripts/builder_entry.py').read_text().splitlines()), 120)

    def test_scenario_fields_and_anchors(self):
        required = {'css-only', 'missing-service', 'forbidden-partial', 'publish-request', 'unknown-scope'}
        self.assertTrue(required <= self.scenarios.keys())
        for ident, case in self.scenarios.items():
            with self.subTest(case=ident):
                self.assertEqual(set(case), {'source_note', 'id', 'title', 'user_request', 'context', 'expected', 'entry_anchors'})
                self.assertEqual(case['id'], ident)
                self.assertIn('dff661c31', case['source_note'])
                self.assertTrue(case['title'] and case['user_request'])
                expected = case['expected']
                self.assertEqual(set(expected), {'request_scopes', 'forbidden_actions', 'confirmation_required', 'notes'})
                self.assertIsInstance(expected['confirmation_required'], bool)
                self.assertIsInstance(expected['request_scopes'], list)
                self.assertTrue(set(expected['request_scopes']) <= SCOPES)
                self.assertTrue(expected['forbidden_actions'] and expected['notes'])
                self.assertGreaterEqual(len(case['entry_anchors']), 2)
                for anchor in case['entry_anchors']:
                    self.assertTrue(anchor)
                    self.assertIn(anchor, self.rendered)

    def test_snapshot_envelopes_and_core_data(self):
        fields = {'app': {'app_id', 'name', 'slug', 'status', 'execution_mode', 'source_version', 'capabilities'},
                  'protected_files': {'policy_version', 'no_modify', 'no_delete'}, 'limits': {'vfs', 'source'}}
        for ident, case in self.scenarios.items():
            with self.subTest(case=ident):
                ctx = case['context']
                self.assertEqual(set(ctx), {'protocol', 'app_id', 'fetched_at', 'scopes'})
                self.assertEqual(ctx['protocol'], {'major': 3, 'minor': 0})
                self.assertTrue(fields.keys() <= ctx['scopes'].keys() <= SCOPES)
                for name, env in ctx['scopes'].items():
                    self.assertTrue({'scope', 'fetched_at', 'status', 'completeness'} <= env.keys())
                    self.assertTrue(env.keys() <= {'scope', 'revision', 'fetched_at', 'status', 'completeness', 'data'})
                    self.assertEqual(env['scope'], name)
                    self.assertIn(env['status'], {'ready', 'forbidden', 'unavailable', 'not_requested'})
                    self.assertIn(env['completeness'], {'complete', 'partial'})
                    if env['status'] == 'ready':
                        self.assertTrue(env['revision'] and env['data'])
                    else:
                        self.assertIsNone(env.get('revision'))
                    if env['status'] in {'not_requested', 'forbidden'}:
                        self.assertIsNone(env.get('data'))
                    if name in fields:
                        extra = {'unexpected'} if ident == 'unknown-scope' and name == 'app' else set()
                        self.assertEqual(set(env['data']), fields[name] | extra)
                app = ctx['scopes']['app']['data']
                self.assertEqual(app['app_id'], ctx['app_id'])
                self.assertEqual(app['capabilities'], {'manage': True, 'publish_direct': False, 'publish_request': True})
                protected = ctx['scopes']['protected_files']['data']
                self.assertTrue(set(protected['no_modify']) <= set(protected['no_delete']))
                limits = ctx['scopes']['limits']
                self.assertEqual(limits['status'], 'unavailable')
                self.assertIn(limits['data']['source'], {'cached', 'fallback'})
                self.assertEqual(set(limits['data']['vfs']), {'max_file_count', 'max_file_size_bytes', 'build_timeout_ms'})
                self.assertTrue(all(type(v) is int and v > 0 for v in limits['data']['vfs'].values()))

    def test_css_only_needs_no_additional_scopes(self):
        self.assertEqual(self.scenarios['css-only']['expected']['request_scopes'], [])

    def test_service_and_publish_require_confirmation(self):
        for ident in ('missing-service', 'publish-request'):
            self.assertTrue(self.scenarios[ident]['expected']['confirmation_required'])
        self.assertNotIn('services', self.scenarios['missing-service']['context']['scopes'])
        self.assertIn('propose_operation', self.scenarios['missing-service']['expected']['notes'])
        self.assertIn('auto_publish', self.scenarios['publish-request']['expected']['forbidden_actions'])

    def test_unknown_snapshot_is_rejected(self):
        case = self.scenarios['unknown-scope']
        self.assertIn('拒絕整份 snapshot', case['expected']['notes'])
        self.assertIn('accept_snapshot', case['expected']['forbidden_actions'])
        self.assertIn('unexpected', case['context']['scopes']['app']['data'])

    def test_partial_and_forbidden_do_not_mean_absent(self):
        case = self.scenarios['forbidden-partial']
        self.assertEqual(case['context']['scopes']['tables']['completeness'], 'partial')
        self.assertEqual(case['context']['scopes']['references']['status'], 'forbidden')
        self.assertTrue({'create_table', 'assume_absent'} <= set(case['expected']['forbidden_actions']))

    def test_external_ide_remains_unchanged(self):
        for fragment in ('## Phase -1', '## Phase 1：', '## Phase 4', BEGIN, END):
            self.assertIn(fragment, self.skill)
        try:
            result = subprocess.run(['git', 'diff', '--quiet', 'HEAD', '--', 'SKILL.md', 'CONTEXT.md'], cwd=ROOT)
        except FileNotFoundError:
            self.skipTest('git unavailable: cannot verify HEAD diff')
        self.assertEqual(result.returncode, 0)

    def test_extract_rejects_missing_duplicate_or_reversed_markers(self):
        for value in (BEGIN + 'body', END, BEGIN + BEGIN + END, BEGIN + END + END, END + BEGIN):
            with self.subTest(value=value), self.assertRaises(ValueError):
                extract_shared_rules(value)

    def test_render_rejects_missing_or_duplicate_include(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'builder').mkdir()
            (root / 'SKILL.md').write_text(self.skill)
            for value in ('no include', INCLUDE + '\n' + INCLUDE):
                (root / 'builder/ENTRY.md').write_text(value)
                with self.subTest(value=value), self.assertRaises(ValueError):
                    render_entry(root)

    def test_cli_is_standalone_and_writes_only_explicit_output(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'core.md'
            command = [sys.executable, '-S', str(ROOT / 'scripts/builder_entry.py'), '--root', str(ROOT)]
            result = subprocess.run(command, cwd=directory, capture_output=True, text=True, check=True)
            self.assertEqual(result.stdout, self.rendered)
            self.assertFalse(result.stderr)
            subprocess.run(command + ['--out', str(out)], cwd=directory, check=True)
            self.assertEqual(out.read_text(), self.rendered)
            self.assertTrue(self.rendered.endswith('\n') and not self.rendered.endswith('\n\n'))


if __name__ == '__main__':
    unittest.main()
