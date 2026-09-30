"""Offline tests for report_issue.py authentication and rate-limit handling (no network)."""
import argparse
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import httpx
import report_issue

API = 'https://ticket.test.invalid'
AIGO_URL = f'{API}/api/auth/aigo'
LOGIN_URL = f'{API}/api/auth/login'
CREDS = {
    'email': 'aigo.acme.dev.abc123@ticket.example', 'password': 'derived-digest',
    'contact_email': 'dev@example.com', 'display_name': 'dev', 'tenant': 'acme',
}


def response(status, data=None, headers=None):
    return httpx.Response(status, json=data if data is not None else {}, headers=headers,
                          request=httpx.Request('POST', API))


class FakeClient:
    """Routes client.post(url) to a queue of responses (or exceptions) per URL; records calls."""

    def __init__(self, routes):
        self.routes = {url: list(items) for url, items in routes.items()}
        self.calls = []

    def post(self, url, json=None, headers=None, content=None):
        self.calls.append((url, json))
        item = self.routes[url].pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def urls(self):
        return [u for u, _ in self.calls]


class AuthTestBase(unittest.TestCase):
    def setUp(self):
        patches = [
            patch.object(report_issue, '_api_base', return_value=API),
            patch.object(report_issue, 'resolve_base_url', return_value='https://acme.ai-go.app'),
            patch.object(report_issue, 'load_env_file'),
            patch.object(report_issue, 'derive_credentials', return_value=dict(CREDS)),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.get_token = patch.object(report_issue.aigo_auth, 'get_token', return_value='aigo-tok-1').start()
        self.addCleanup(patch.stopall)


class VerifiedAuthTest(AuthTestBase):
    def test_verified_success_sends_only_tenant_and_token(self):
        client = FakeClient({AIGO_URL: [response(200, {'access_token': 'tk', 'verified': True})]})
        self.assertEqual(report_issue.authenticate(client, '.'), ('tk', 'acme', 'verified'))
        self.assertEqual(client.calls, [(AIGO_URL, {'tenant': 'acme', 'aigo_token': 'aigo-tok-1'})])
        report_issue.derive_credentials.assert_not_called()

    def test_404_and_405_fall_back_to_legacy(self):
        for status in (404, 405):
            with self.subTest(status=status):
                client = FakeClient({
                    AIGO_URL: [response(status)],
                    LOGIN_URL: [response(200, {'access_token': 'legacy'})],
                })
                self.assertEqual(report_issue.authenticate(client, '.'), ('legacy', 'acme', 'legacy'))
                self.assertEqual(client.urls(), [AIGO_URL, LOGIN_URL])
                self.assertEqual(client.calls[1][1]['password'], 'derived-digest')

    def test_401_refreshes_once_then_retries_success(self):
        self.get_token.side_effect = ['aigo-old', 'aigo-new']
        client = FakeClient({AIGO_URL: [
            response(401, {'error': 'aigo_token_invalid'}),
            response(200, {'access_token': 'tk2'}),
        ]})
        self.assertEqual(report_issue.authenticate(client, '.'), ('tk2', 'acme', 'verified'))
        self.assertEqual(self.get_token.call_args_list[1].kwargs, {'force': True})
        self.assertEqual(client.calls[1][1]['aigo_token'], 'aigo-new')

    def test_401_twice_errors_without_legacy_fallback(self):
        client = FakeClient({AIGO_URL: [
            response(401, {'error': 'aigo_token_invalid'}),
            response(401, {'error': 'aigo_token_invalid'}),
        ]})
        with self.assertRaises(RuntimeError) as ctx:
            report_issue.authenticate(client, '.')
        self.assertIn('aigo_auth.py login', str(ctx.exception))
        self.assertEqual(self.get_token.call_count, 2)
        self.assertEqual(client.urls(), [AIGO_URL, AIGO_URL])
        report_issue.derive_credentials.assert_not_called()

    def test_502_and_timeout_fall_back_to_legacy(self):
        for first in (response(502, {'error': 'aigo_unreachable'}), httpx.ReadTimeout('slow')):
            with self.subTest(first=first):
                client = FakeClient({
                    AIGO_URL: [first],
                    LOGIN_URL: [response(200, {'access_token': 'legacy'})],
                })
                self.assertEqual(report_issue.authenticate(client, '.'), ('legacy', 'acme', 'legacy'))

    def test_platform_unreachable_falls_back_to_legacy(self):
        self.get_token.side_effect = httpx.ConnectError('down')
        client = FakeClient({LOGIN_URL: [response(200, {'access_token': 'legacy'})]})
        self.assertEqual(report_issue.authenticate(client, '.'), ('legacy', 'acme', 'legacy'))

    def test_429_on_auth_exits_without_retry(self):
        client = FakeClient({AIGO_URL: [response(429, {'error': 'rate_limited', 'retry_after': 42})]})
        with patch('time.sleep') as sleep, self.assertRaises(report_issue.RateLimited) as ctx:
            report_issue.authenticate(client, '.')
        self.assertIn('42', str(ctx.exception))
        self.assertEqual(len(client.calls), 1)
        sleep.assert_not_called()

    def test_token_never_printed(self):
        client = FakeClient({AIGO_URL: [response(502)], LOGIN_URL: [response(200, {'access_token': 'legacy'})]})
        with patch('builtins.print') as pr:
            report_issue.authenticate(client, '.')
        printed = ' '.join(str(a) for c in pr.call_args_list for a in c.args)
        self.assertNotIn('aigo-tok-1', printed)


class GatingTest(AuthTestBase):
    def _assert_legacy_only(self, client):
        with patch('builtins.print'):
            self.assertEqual(report_issue.authenticate(client, '.'), ('legacy', 'acme', 'legacy'))
        self.assertEqual(client.urls(), [LOGIN_URL])
        self.get_token.assert_not_called()

    def test_non_production_tenant_hosts_skip_verified(self):
        for base in ('https://acme.uat.ai-go.app', 'https://acme-uat.example.test',
                     'http://localhost:8000', 'http://acme.ai-go.app', 'https://ai-go.app'):
            with self.subTest(base=base), patch.object(report_issue, 'resolve_base_url', return_value=base):
                self.get_token.reset_mock()
                self._assert_legacy_only(FakeClient({LOGIN_URL: [response(200, {'access_token': 'legacy'})]}))

    def test_plain_http_api_never_receives_token(self):
        with patch.object(report_issue, '_api_base', return_value='http://ticket.example.test'):
            client = FakeClient({'http://ticket.example.test/api/auth/login': [response(200, {'access_token': 'legacy'})]})
            with patch('builtins.print'):
                self.assertEqual(report_issue.authenticate(client, '.')[2], 'legacy')
        self.get_token.assert_not_called()
        self.assertNotIn('aigo_token', str(client.calls))

    def test_http_localhost_api_allowed_for_testing(self):
        for api in ('http://localhost:8787', 'http://127.0.0.1:8787'):
            with self.subTest(api=api), patch.object(report_issue, '_api_base', return_value=api):
                client = FakeClient({f'{api}/api/auth/aigo': [response(200, {'access_token': 'tk'})]})
                self.assertEqual(report_issue.authenticate(client, '.'), ('tk', 'acme', 'verified'))


class SubmitRateLimitTest(AuthTestBase):
    def _args(self, **kw):
        base = dict(title='t', given='g', when='w', then='r', expected='e', context=None, body=None,
                    body_file=None, image=None, ruled_out='a\nb\nc', ruled_out_file=None,
                    user_confirmed=True, project='.')
        base.update(kw)
        return argparse.Namespace(**base)

    def _run_submit(self, routes, **kw):
        client = FakeClient(routes)
        cm = MagicMock()
        cm.__enter__.return_value = client
        with patch.object(report_issue.httpx, 'Client', return_value=cm), \
                patch.dict('os.environ', {'URFIT_TICKET_PREFLIGHT': '1'}):
            return client, report_issue.cmd_submit(self._args(**kw))

    def test_429_on_ticket_submit_raises_once(self):
        with self.assertRaises(report_issue.RateLimited) as ctx:
            self._run_submit({
                AIGO_URL: [response(200, {'access_token': 'tk'})],
                f'{API}/api/tickets/preflight': [response(200, {'decision': 'none'})],
                f'{API}/api/tickets': [response(429, {'error': 'rate_limited', 'retry_after': 7})],
            })
        self.assertIn('7', str(ctx.exception))

    def test_429_on_preflight_is_skipped_and_submit_proceeds(self):
        client, code = self._run_submit({
            AIGO_URL: [response(200, {'access_token': 'tk'})],
            f'{API}/api/tickets/preflight': [response(429, {'retry_after': 5})],
            f'{API}/api/tickets': [response(201, {'ticket_id': 'x1', 'status': 'new'})],
        })
        self.assertEqual(code, 0)
        self.assertEqual(client.urls().count(f'{API}/api/tickets'), 1)

    def test_429_on_image_upload_raises(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        img = Path(tmp.name) / 'shot.png'
        img.write_bytes(b'\x89PNG')
        with self.assertRaises(report_issue.RateLimited):
            self._run_submit({
                AIGO_URL: [response(200, {'access_token': 'tk'})],
                f'{API}/api/tickets/preflight': [response(200, {'decision': 'none'})],
                f'{API}/api/uploads': [response(429, {'retry_after': 3})],
            }, image=[str(img)])

    def test_main_exit_code_nonzero_on_rate_limit(self):
        with patch.object(report_issue, 'cmd_list', side_effect=report_issue.RateLimited('x')), \
                patch.object(sys, 'argv', ['report_issue.py', 'list']), patch('builtins.print'):
            # parser binds func at parse time; patching module attr before main() parses is enough
            self.assertEqual(report_issue.main(), 1)


if __name__ == '__main__':
    unittest.main()
