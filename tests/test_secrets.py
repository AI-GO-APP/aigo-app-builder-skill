"""Offline tests for aigo_secrets.py: the secret value must never reach stdout/stderr."""
import contextlib
import io
import os
import re
import sys
import tempfile
import traceback
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import httpx
import aigo_secrets as s

VALUE = 'sk-TOPSECRET-123'
BASE = 'https://t.ai-go.app'


def response(status, data):
    return httpx.Response(status, json=data, request=httpx.Request('GET', 'https://test.invalid'))


def secret_file(d, mode=0o600, content=VALUE + '\n', name='k.env'):
    p = Path(d) / name
    p.write_text(content, encoding='utf-8')
    os.chmod(p, mode)
    return p


class SecretFileTest(unittest.TestCase):
    @unittest.skipIf(os.name == 'nt', 'posix only')
    def test_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            real = secret_file(d, name='real.env')
            link = Path(d) / 'link.env'
            os.symlink(real, link)
            with self.assertRaises(s.SecretFileError):
                s.read_secret_file(link)

    @unittest.skipIf(os.name == 'nt', 'posix only')
    def test_non_utf8_error_has_no_value_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'bad.env'
            p.write_bytes(b'sk-\xff\xfeSECRET')
            os.chmod(p, 0o600)
            with self.assertRaises(s.SecretFileError) as cm:
                s.read_secret_file(p)
            msg = str(cm.exception)
            self.assertNotIn('SECRET', msg)
            self.assertNotIn('xff', msg)
            self.assertIsNone(cm.exception.__cause__)

    @unittest.skipIf(os.name == 'nt', 'posix only')
    def test_requires_mode_600(self):
        with tempfile.TemporaryDirectory() as d:
            for mode in (0o644, 0o640, 0o400, 0o700):
                with self.subTest(mode=oct(mode)):
                    with self.assertRaises(s.SecretFileError) as cm:
                        s.read_secret_file(secret_file(d, mode, name=f'k{mode:o}.env'))
                    self.assertNotIn(VALUE, str(cm.exception))
            self.assertEqual(s.read_secret_file(secret_file(d)), VALUE)

    @unittest.skipIf(os.name == 'nt', 'posix only')
    def test_missing_empty_and_directory(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(s.SecretFileError):
                s.read_secret_file(Path(d) / 'nope')
            with self.assertRaises(s.SecretFileError):
                s.read_secret_file(secret_file(d, content='\n'))
            with self.assertRaises(s.SecretFileError):
                s.read_secret_file(d)

    @unittest.skipUnless(os.name == 'nt', 'Windows only')
    def test_windows_file_rejected_with_env_alternative(self):
        with self.assertRaisesRegex(s.SecretFileError, '--from-env'):
            s.read_secret_file('not-read')


class ApiTest(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {'AIGO_TEST_SECRET': VALUE})
        env.start()
        self.addCleanup(env.stop)

    def run_quiet(self, fn, *a, **kw):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            result = fn(*a, **kw)
        self.assertNotIn(VALUE, out.getvalue() + err.getvalue())
        return result

    def test_create_sends_value_only_in_body(self):
        with patch('httpx.get', return_value=response(200, [])), \
                patch('httpx.post', return_value=response(201, {'id': '1', 'key_name': 'API_KEY'})) as post:
            self.assertEqual(self.run_quiet(s.set_secret, BASE, 't', 'app', 'API_KEY', env_name='AIGO_TEST_SECRET'), 'created')
        self.assertEqual(post.call_args.args[0], f'{BASE}/api/v1/actions/apps/app/secrets')
        self.assertEqual(post.call_args.kwargs['json'], {'key_name': 'API_KEY', 'value': VALUE, 'description': ''})
        self.assertNotIn(VALUE, post.call_args.args[0])
        self.assertNotIn(VALUE, str(post.call_args.kwargs['headers']))

    def test_existing_key_is_updated(self):
        listing = [{'id': 'sid', 'key_name': 'API_KEY'}]
        with patch('httpx.get', return_value=response(200, listing)), \
                patch('httpx.put', return_value=response(200, {})) as put:
            self.assertEqual(self.run_quiet(s.set_secret, BASE, 't', 'app', 'API_KEY', env_name='AIGO_TEST_SECRET'), 'updated')
        self.assertEqual(put.call_args.args[0], f'{BASE}/api/v1/actions/secrets/sid')
        self.assertEqual(put.call_args.kwargs['json'], {'value': VALUE})

    def test_failure_message_has_no_value(self):
        with patch('httpx.get', return_value=response(200, [])), \
                patch('httpx.post', return_value=response(422, {'detail': VALUE})):
            with self.assertRaises(RuntimeError) as cm:
                self.run_quiet(s.set_secret, BASE, 't', 'app', 'API_KEY', env_name='AIGO_TEST_SECRET')
        self.assertNotIn(VALUE, str(cm.exception))

    def test_redirect_is_not_reported_as_success(self):
        with patch('httpx.get', return_value=response(200, [])), \
                patch('httpx.post', return_value=response(302, {})):
            with self.assertRaises(RuntimeError):
                self.run_quiet(s.set_secret, BASE, 't', 'app', 'API_KEY', env_name='AIGO_TEST_SECRET')
        with patch('httpx.get', return_value=response(200, [{'id': 'sid', 'key_name': 'API_KEY'}])), \
                patch('httpx.delete', return_value=response(302, {})):
            with self.assertRaises(RuntimeError):
                self.run_quiet(s.delete_secret, BASE, 't', 'app', 'API_KEY', confirm=True)

    @unittest.skipIf(os.name == 'nt', 'posix only')
    def test_file_source_still_sends_raw_value(self):
        with tempfile.TemporaryDirectory() as d:
            f = secret_file(d)
            with patch('httpx.get', return_value=response(200, [])), \
                    patch('httpx.post', return_value=response(201, {})) as post:
                self.assertEqual(s.set_secret(BASE, 't', 'app', 'K', f), 'created')
            self.assertEqual(post.call_args.kwargs['json']['value'], VALUE)

    @unittest.skipIf(os.name == 'nt', 'posix only')
    def test_env_shaped_file_is_rejected_without_leaking(self):
        with tempfile.TemporaryDirectory() as d:
            multi = secret_file(d, content=f'API_KEY={VALUE}\nCRON_KEY=b\n', name='multi')
            with self.assertRaises(s.SecretFileError) as cm:
                s.read_secret_file(multi)
            self.assertNotIn(VALUE, str(cm.exception))
            prefixed = secret_file(d, content=f'API_KEY={VALUE}\n', name='prefixed')
            with patch('httpx.get') as get, patch('httpx.post') as post:
                with self.assertRaises(s.SecretFileError) as cm:
                    self.run_quiet(s.set_secret, BASE, 't', 'app', 'API_KEY', prefixed)
                get.assert_not_called()
                post.assert_not_called()
            self.assertNotIn(VALUE, str(cm.exception))

    @unittest.skipIf(os.name == 'nt', 'posix only')
    def test_multiline_values_like_pem_are_allowed(self):
        pem = '-----BEGIN PRIVATE KEY-----\nYWJj=\nZGVm==\n-----END PRIVATE KEY-----'
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(s.read_secret_file(secret_file(d, content=pem + '\n', name='pem')), pem)

    def test_refuses_non_https(self):
        with tempfile.TemporaryDirectory() as d, patch('httpx.post') as post:
            with self.assertRaises(ValueError):
                s.set_secret('http://t.ai-go.app', 't', 'app', 'K', secret_file(d))
            post.assert_not_called()

    def test_list_keeps_metadata_only(self):
        listing = [{'id': '1', 'key_name': 'K', 'value': VALUE, 'encrypted_value': 'x'}]
        with patch('httpx.get', return_value=response(200, listing)):
            rows = s.list_secrets(BASE, 't', 'app')
        self.assertEqual(rows[0]['key_name'], 'K')
        self.assertNotIn(VALUE, str(rows))

    def test_delete_requires_confirm(self):
        with patch('httpx.delete') as delete:
            with self.assertRaises(PermissionError):
                s.delete_secret(BASE, 't', 'app', 'K', confirm=False)
            delete.assert_not_called()
        with patch('httpx.get', return_value=response(200, [{'id': 'sid', 'key_name': 'K'}])), \
                patch('httpx.delete', return_value=response(200, {'status': 'deleted'})) as delete:
            self.assertTrue(s.delete_secret(BASE, 't', 'app', 'K', confirm=True))
            self.assertEqual(delete.call_args.args[0], f'{BASE}/api/v1/actions/secrets/sid')

    def test_no_read_value_command(self):
        self.assertFalse(any('value' in n and n != 'read_secret_file' for n in dir(s) if callable(getattr(s, n))))
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            s.main(['get', 'app', 'K'])

    def test_env_missing_empty_and_placeholder_never_call_api(self):
        for value in (None, '', ' \r\n', s.PENDING_SECRET, f' {s.PENDING_SECRET}\n'):
            with self.subTest(value=value), patch.dict(os.environ, {}, clear=True), \
                    patch('httpx.get') as get, patch('httpx.post') as post:
                if value is not None:
                    os.environ['AIGO_TEST_SECRET'] = value
                with self.assertRaises(s.SecretFileError) as cm:
                    s.set_secret(BASE, 't', 'app', 'K', env_name='AIGO_TEST_SECRET')
                self.assertNotIn(VALUE, str(cm.exception))
                get.assert_not_called()
                post.assert_not_called()

    def test_sources_mutually_exclusive(self):
        for kwargs in ({}, {'value_file': 'file', 'env_name': 'AIGO_TEST_SECRET'}):
            with self.subTest(kwargs=kwargs), patch('httpx.get') as get:
                with self.assertRaises(s.SecretFileError):
                    s.set_secret(BASE, 't', 'app', 'K', **kwargs)
                get.assert_not_called()
        for argv in (['set', 'app', 'K'], ['set', 'app', 'K', '--from-env', 'VAR', '--from-file', 'file']):
            with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                s.main(argv)

    def test_env_preserves_multiline_value_and_description(self):
        pem = '-----BEGIN PRIVATE KEY-----\nYWJj=\n-----END PRIVATE KEY-----\n'
        with patch.dict(os.environ, {'AIGO_TEST_SECRET': pem}), \
                patch('httpx.get', return_value=response(200, [{'id': 'sid', 'key_name': 'K'}])), \
                patch('httpx.put', return_value=response(200, {})) as put:
            s.set_secret(BASE, 't', 'app', 'K', description='用途', env_name='AIGO_TEST_SECRET')
        self.assertEqual(put.call_args.kwargs['json'], {'value': pem, 'description': '用途'})

    def test_env_name_error_does_not_echo_input(self):
        with self.assertRaises(s.SecretFileError) as cm:
            s.set_secret(BASE, 't', 'app', 'K', env_name=VALUE)
        self.assertNotIn(VALUE, str(cm.exception))

    def test_transport_and_response_errors_do_not_leak(self):
        for method in ('get', 'post', 'put'):
            with self.subTest(method=method), \
                    patch('httpx.get', return_value=response(200, [] if method != 'put' else [{'id': 'sid', 'key_name': 'K'}])), \
                    patch(f'httpx.{method}', side_effect=httpx.ConnectError(VALUE)):
                try:
                    s.set_secret(BASE, 't', 'app', 'K', env_name='AIGO_TEST_SECRET')
                except RuntimeError:
                    self.assertNotIn(VALUE, traceback.format_exc())
                else:
                    self.fail('expected sanitized failure')
        with patch('httpx.get', return_value=response(403, {'detail': VALUE})):
            with self.assertRaises(RuntimeError) as cm:
                s.list_secrets(BASE, 't', 'app')
            self.assertNotIn(VALUE, str(cm.exception))

    def test_create_key_uses_placeholder(self):
        with patch('httpx.get', return_value=response(200, [])), \
                patch('httpx.post', return_value=response(201, {})) as post:
            self.assertEqual(s.create_key(BASE, 't', 'app', 'K', '供 sync action 使用'), 'created')
        self.assertEqual(post.call_args.kwargs['json'], {
            'key_name': 'K', 'value': s.PENDING_SECRET, 'description': '供 sync action 使用'})

    def test_create_key_never_modifies_existing(self):
        with patch('httpx.get', return_value=response(200, [{'id': 'sid', 'key_name': 'K'}])), \
                patch('httpx.post') as post, patch('httpx.put') as put:
            self.assertEqual(s.create_key(BASE, 't', 'app', 'K', 'new description'), 'exists')
            post.assert_not_called()
            put.assert_not_called()

    def test_create_key_conflict_is_not_an_update(self):
        for second_listing, expected in (([{'id': 'sid', 'key_name': 'K'}], 'exists'), ([], None)):
            with self.subTest(second_listing=second_listing), \
                    patch('httpx.get', side_effect=[response(200, []), response(200, second_listing)]), \
                    patch('httpx.post', return_value=response(409, {'detail': VALUE})) as post, \
                    patch('httpx.put') as put:
                if expected:
                    self.assertEqual(s.create_key(BASE, 't', 'app', 'K', '用途'), expected)
                else:
                    with self.assertRaisesRegex(RuntimeError, '409') as cm:
                        s.create_key(BASE, 't', 'app', 'K', '用途')
                    self.assertNotIn(VALUE, str(cm.exception))
                self.assertEqual(post.call_count, 1)
                put.assert_not_called()

    def test_create_key_errors_and_description(self):
        with patch('httpx.get') as get:
            with self.assertRaises(ValueError):
                s.create_key(BASE, 't', 'app', 'K', ' ')
            get.assert_not_called()
        for code in (302, 422, 500):
            with self.subTest(code=code), patch('httpx.get', return_value=response(200, [])), \
                    patch('httpx.post', return_value=response(code, {'detail': VALUE})):
                with self.assertRaises(RuntimeError) as cm:
                    s.create_key(BASE, 't', 'app', 'K', '用途')
                self.assertNotIn(VALUE, str(cm.exception))


class CliTest(unittest.TestCase):
    def run_cli(self, argv, listing):
        import aigo_auth
        app = SimpleNamespace(id='app-id', base_url=BASE, describe=lambda: '測試 App')
        out = io.StringIO()
        with patch.object(aigo_auth, 'find_workspace', return_value=None), \
                patch.object(aigo_auth, 'resolve_app', return_value=app), \
                patch.object(aigo_auth, 'get_token', return_value='fake-token'), \
                patch('httpx.get', return_value=response(200, listing)) as get, \
                contextlib.redirect_stdout(out):
            self.assertEqual(s.main(argv), 0)
        self.assertNotIn(VALUE, out.getvalue())
        self.assertTrue(all('/value' not in call.args[0] for call in get.call_args_list))
        return out.getvalue()

    def test_status_never_claims_configured_from_metadata(self):
        output = self.run_cli(['status', 'app'], [{'key_name': 'K', 'description': '已填值',
                                                  'value': VALUE, 'updated_at': 'now'}])
        self.assertIn('設定狀態未確認', output)
        self.assertNotIn('已填值', output)

    def test_create_key_cli_link_and_pending_state(self):
        with patch('httpx.post', return_value=response(201, {})):
            output = self.run_cli(['create-key', 'app', 'K', '--description', '用途'], [])
        self.assertIn('待貼值', output)
        self.assertIn(f'{BASE}/builder/app-id', output)

    def test_set_env_cli(self):
        with patch.dict(os.environ, {'AIGO_TEST_SECRET': VALUE}), \
                patch('httpx.post', return_value=response(201, {})) as post:
            self.run_cli(['set', 'app', 'K', '--from-env', 'AIGO_TEST_SECRET'], [])
        self.assertEqual(post.call_args.kwargs['json']['value'], VALUE)


class ActionExampleTest(unittest.TestCase):
    def test_documented_action_blocks_missing_and_placeholder_before_http(self):
        guide = (Path(__file__).resolve().parents[1] / 'references/custom-app-dev-guide.md').read_text(encoding='utf-8')
        section = guide.split('### 25.1 ', 1)[1].split('### 25.2 ', 1)[0]
        code = re.search(r'```python\n(.*?)```', section, re.S).group(1)
        namespace = {}
        exec(compile(code, 'dev-guide-section-25.1', 'exec'), namespace)
        for value in (None, '', ' \n', s.PENDING_SECRET, f' {s.PENDING_SECRET}\n', VALUE):
            with self.subTest(value=value):
                ctx = SimpleNamespace(secrets=Mock(), http=Mock(), response=Mock())
                ctx.secrets.get.return_value = value
                ctx.http.call.return_value = {'status': 200, 'data': []}
                namespace['execute'](ctx)
                if value == VALUE:
                    ctx.http.call.assert_called_once()
                    self.assertEqual(ctx.http.call.call_args.kwargs['headers']['Authorization'], f'Bearer {VALUE}')
                else:
                    ctx.http.call.assert_not_called()
                    self.assertEqual(ctx.response.json.call_args.args[0]['status'], 'not_configured')


if __name__ == '__main__':
    unittest.main()
