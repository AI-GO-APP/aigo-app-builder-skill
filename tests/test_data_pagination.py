"""Offline tests for aigo_data.py pagination inference and permission map."""
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import httpx
import aigo_data
from aigo_data import call, infer_pagination, permission_for

ROWS = [{'id': i} for i in range(7)]


def fake_session(handler):
    seen = []

    def wrapped(request):
        seen.append(dict(request.url.params))
        return handler(request)

    client = httpx.Client(base_url='https://test.invalid', transport=httpx.MockTransport(wrapped))
    return SimpleNamespace(client=client), seen


def skip_envelope(request):
    q = request.url.params
    skip, limit = int(q.get('skip', 0)), int(q.get('limit', 100))
    return httpx.Response(200, json={'items': ROWS[skip:skip + limit], 'total': len(ROWS), 'skip': skip, 'limit': limit})


def page_envelope(request):
    q = request.url.params
    page, size = int(q.get('page', 1)), int(q.get('page_size', 25))
    return httpx.Response(200, json={'items': ROWS[(page - 1) * size:page * size], 'total': len(ROWS),
                                     'page': page, 'page_size': size})


def bare_list(request):
    q = request.url.params
    skip, limit = int(q.get('skip', 0)), int(q.get('limit', 100))
    return httpx.Response(200, json=ROWS[skip:skip + limit])


class InferTest(unittest.TestCase):
    def test_shapes(self):
        self.assertEqual(infer_pagination([]), 'skip')
        self.assertEqual(infer_pagination({'items': [], 'total': 0, 'skip': 0, 'limit': 100}), 'skip')
        self.assertEqual(infer_pagination({'items': [], 'total': 0, 'page': 1, 'page_size': 25}), 'page')
        self.assertEqual(infer_pagination({'items': [], 'total': 0, 'limit': 5, 'offset': 0}), 'offset')
        self.assertEqual(infer_pagination({'items': [], 'total': 0}), 'page')
        self.assertIsNone(infer_pagination({'id': 1, 'name': 'x'}))
        self.assertIsNone(infer_pagination({'items': []}))

    def test_explicit_params_win(self):
        self.assertEqual(infer_pagination([], {'page_size': '10'}), 'page')
        self.assertEqual(infer_pagination({'items': [], 'total': 0, 'page': 1}, {'skip': '0'}), 'skip')


class CallAllTest(unittest.TestCase):
    def check(self, handler, params, expect_keys, paging='auto'):
        s, seen = fake_session(handler)
        rows = call(s, 'GET', '/api/v1/x', params=params, all_pages=True, paging=paging)
        self.assertEqual(rows, ROWS)
        self.assertTrue(any(expect_keys <= set(p) for p in seen), seen)
        return seen

    def test_skip_envelope(self):
        self.check(skip_envelope, {'limit': '3'}, {'skip', 'limit'})

    def test_page_envelope(self):
        self.check(page_envelope, {'page_size': '3'}, {'page', 'page_size'})

    def test_bare_list(self):
        self.check(bare_list, {'limit': '3'}, {'skip', 'limit'})

    def test_explicit_override(self):
        seen = self.check(skip_envelope, {'limit': '3'}, {'skip', 'limit'}, paging='skip')
        self.assertIn('skip', seen[0])  # no auto probe request

    def test_single_page_needs_no_refetch(self):
        s, seen = fake_session(skip_envelope)
        self.assertEqual(call(s, 'GET', '/api/v1/x', all_pages=True), ROWS)
        self.assertEqual(len(seen), 1)

    def test_endpoint_ignoring_paging_stops(self):
        s, _ = fake_session(lambda r: httpx.Response(200, json=ROWS[:3]))
        with redirect_stdout(io.StringIO()):
            rows = call(s, 'GET', '/api/v1/x', params={'limit': '3'}, all_pages=True)
        self.assertEqual(rows, ROWS[:3])


class OpenapiGoneTest(unittest.TestCase):
    def test_legacy_subcommand_explains_without_login(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = aigo_data.main(['openapi', 'paths', '--prefix', '/api/v1/sale'])
        self.assertEqual(code, 2)
        self.assertIn('openapi.json', buf.getvalue())


class PermissionMapTest(unittest.TestCase):
    def test_platform_mapping(self):
        self.assertEqual(permission_for('GET', '/api/v1/members'), 'hr.member_manage')
        self.assertEqual(permission_for('GET', '/api/v1/members/abc'), 'hr.member_manage')
        self.assertIsNone(permission_for('GET', '/api/v1/members/roles'))
        self.assertEqual(permission_for('POST', '/api/v1/members/roles'), 'system.roles_manage')
        self.assertEqual(permission_for('GET', '/api/v1/erp/analytic/plans'), 'accounting.read')
        self.assertEqual(permission_for('PATCH', '/api/v1/erp/analytic/accounts/1'), 'accounting.write')
        self.assertEqual(permission_for('DELETE', '/api/v1/erp/analytic/plans/1'), 'accounting.delete')
        self.assertEqual(permission_for('GET', '/api/v1/erp/partner-banks'), 'system.partner_banks')
        self.assertEqual(permission_for('GET', '/api/v1/erp/currencies'), 'system.reference_data')


if __name__ == '__main__':
    unittest.main()
