"""Offline tests for aigo_template.py (read-only template inventory / preview download)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import httpx
import aigo_template as t


def response(status, data):
    return httpx.Response(status, json=data, request=httpx.Request('GET', 'https://test.invalid'))


VFS = {
    'src/App.tsx': 'export default 1',
    'actions/approve_billing.py': (
        'def execute(ctx):\n'
        '    rows = ctx.db.query("cnst_billings")\n'
        '    ctx.db.insert("cnst_billings", {"a": 1})\n'
        '    ctx.http.call("billing-api", "/x")\n'
        '    ctx.approval.submit({})\n'
        '    ctx.mcp.trigger("sync")\n'
        '    ctx.response.json({})\n'
    ),
    'actions/broken.py': 'def (',
    'README.md': '# x',
}
DETAIL = {
    'access_mode': 'internal',
    'data_center_schema': {'version': 1, 'tables': [{'key': 'cnst_billings', 'fields': []}]},
    'data_references_schema': [{'table_name': 'crm_leads', 'columns': ['id']}],
    'setup_schema': {'BILLING_API_KEY': {'required': True}},  # 平台真實形狀：扁平 {KEY: {required}}
}


class SuiteTest(unittest.TestCase):
    def test_suite_is_slug_prefix(self):
        self.assertEqual(t.suite_of('cnst-billing'), 'cnst')
        self.assertEqual(t.suite_of('gmail'), 'gmail')

    def test_group_excludes_starters_and_orders_by_size(self):
        tpls = [{'slug': s} for s in ('food-b', 'food-a', 'cnst-x', 'starter-internal', 'starter-external')]
        groups = t.group_by_suite(tpls + [{'slug': None}, 'junk'])
        self.assertEqual(list(groups), ['food', 'cnst'])
        self.assertEqual([x['slug'] for x in groups['food']], ['food-a', 'food-b'])


class InventoryTest(unittest.TestCase):
    def test_inferred_inventory_from_schema_and_code(self):
        inv = t.inventory_effects(VFS, DETAIL)
        self.assertEqual(inv['source'], 'inferred')
        self.assertEqual(inv['owned_tables'], ['cnst_billings'])
        self.assertEqual(inv['data_references'], ['crm_leads'])
        self.assertEqual(inv['setup_keys'], ['BILLING_API_KEY'])
        self.assertEqual(list(inv['http_slugs']), ['billing-api'])
        self.assertEqual(sorted(inv['ctx_calls']), ['approval', 'db', 'http', 'mcp'])
        self.assertEqual(len(inv['ctx_calls']['db']['insert']), 1)
        self.assertNotIn('response', inv['ctx_calls'])
        self.assertFalse(inv['has_ports_layer'])
        self.assertIn('ports 層：無', t.format_inventory('cnst-billing', inv))

    def test_platform_overwritten_meta_is_inferred(self):
        # preview 的 _template_meta.json 是平台覆寫的這個形狀，帶不出 effects
        meta = {'factory_key': 'cnst-billing', 'template_version': '1.0.0', 'generated_at': 'x', 'source': 'storage'}
        inv = t.inventory_effects(dict(VFS, **{'_template_meta.json': json.dumps(meta)}), DETAIL)
        self.assertEqual(inv['source'], 'inferred')
        self.assertIn('推斷清單', t.format_inventory('cnst-billing', inv))

    def test_future_declared_effects_path(self):
        # 預留路徑：平台日後保留 effects 時才會走到
        effects = [{'id': 'billing.approved', 'kind': 'output',
                    'default_binding': {'via': 'owned_table', 'ref': 'cnst_billings'}, 'alternatives': ['http']}]
        vfs = dict(VFS, **{'_template_meta.json': json.dumps({'effects': effects}),
                           'actions/_shared/ports.py': ''})
        inv = t.inventory_effects(vfs, DETAIL)
        self.assertEqual(inv['source'], 'declared')
        self.assertTrue(inv['has_ports_layer'])
        self.assertIn('billing.approved', t.format_inventory('cnst-billing', inv))

    def test_meta_without_effects_is_inferred(self):
        vfs = dict(VFS, **{'_template_meta.json': json.dumps({'template_version': '1.0.0'})})
        self.assertEqual(t.inventory_effects(vfs, {})['source'], 'inferred')
        self.assertIsNone(t.declared_effects({'_template_meta.json': 'not json'}))


class PreviewTest(unittest.TestCase):
    def test_fetch_hits_preview_endpoint_with_token(self):
        with patch('httpx.get', return_value=response(200, {'slug': 's', 'files': {'a.ts': 'x'}})) as get:
            self.assertEqual(t.fetch_template_preview('https://test.invalid/', 'tok', 'cnst-billing'), {'a.ts': 'x'})
            self.assertEqual(get.call_args.args[0], 'https://test.invalid/api/v1/templates/cnst-billing/preview')
            self.assertEqual(get.call_args.kwargs['headers']['Authorization'], 'Bearer tok')

    def test_fetch_errors_are_not_swallowed(self):
        with patch('httpx.get', return_value=response(404, {'detail': '模板不存在或已下架'})):
            with self.assertRaises(httpx.HTTPStatusError):
                t.fetch_template_preview('https://test.invalid', 't', 'nope')
        with patch('httpx.get', return_value=response(200, {'slug': 's'})):
            with self.assertRaises(ValueError):
                t.fetch_template_preview('https://test.invalid', 't', 's')

    def test_write_preview_skips_unsafe_paths(self):
        files = {'src/App.tsx': 'a', '../escape.txt': 'x', '/abs.txt': 'x', 'a/../../b': 'x',
                 './actions/x.py': 'p', 'bin.png': None, 'C:/x.txt': 'x', 'C:x.txt': 'x', 'a\\b.txt': 'x',
                 'nul\x00.txt': 'x', 'src/a.ts:stream': 'x'}
        with tempfile.TemporaryDirectory() as d:
            dest = Path(d) / 'tpl'
            written = t.write_preview(files, dest)
            self.assertEqual(sorted(written), ['actions/x.py', 'src/App.tsx'])
            self.assertEqual((dest / 'src/App.tsx').read_text(encoding='utf-8'), 'a')
            self.assertFalse((Path(d) / 'escape.txt').exists())

    def test_write_preview_path_clash_leaves_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            dest = Path(d) / 'tpl'
            with self.assertRaises(ValueError):
                t.write_preview({'a': 'file', 'a/b.ts': 'x', 'z.ts': 'y'}, dest)
            self.assertFalse(dest.exists())
            self.assertEqual(list(Path(d).iterdir()), [])

    def test_write_preview_into_existing_empty_dir(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(t.write_preview({'a.ts': 'x'}, d), ['a.ts'])
            self.assertEqual((Path(d) / 'a.ts').read_text(encoding='utf-8'), 'x')

    def test_write_preview_refuses_non_empty_dir(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'keep.txt').write_text('mine')
            with self.assertRaises(FileExistsError):
                t.write_preview({'a.ts': 'x'}, d)

    def test_list_passes_category(self):
        with patch('httpx.get', return_value=response(200, [{'slug': 'food-a'}])) as get:
            self.assertEqual(t.list_templates('https://test.invalid', 't', 'operations'), [{'slug': 'food-a'}])
            self.assertEqual(get.call_args.kwargs['params'], {'category': 'operations'})


if __name__ == '__main__':
    unittest.main()
