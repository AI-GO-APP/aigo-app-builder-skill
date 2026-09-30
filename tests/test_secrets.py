"""Offline tests for aigo_secrets.py: the secret value must never reach stdout/stderr."""
import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
    def test_requires_mode_600(self):
        with tempfile.TemporaryDirectory() as d:
            for mode in (0o644, 0o640, 0o400, 0o700):
                with self.subTest(mode=oct(mode)):
                    with self.assertRaises(s.SecretFileError) as cm:
                        s.read_secret_file(secret_file(d, mode, name=f'k{mode:o}.env'))
                    self.assertNotIn(VALUE, str(cm.exception))
            self.assertEqual(s.read_secret_file(secret_file(d)), VALUE)

    def test_missing_empty_and_directory(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(s.SecretFileError):
                s.read_secret_file(Path(d) / 'nope')
            with self.assertRaises(s.SecretFileError):
                s.read_secret_file(secret_file(d, content='\n'))
            with self.assertRaises(s.SecretFileError):
                s.read_secret_file(d)


class ApiTest(unittest.TestCase):
    def run_quiet(self, fn, *a, **kw):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            result = fn(*a, **kw)
        self.assertNotIn(VALUE, out.getvalue() + err.getvalue())
        return result

    def test_create_sends_value_only_in_body(self):
        with tempfile.TemporaryDirectory() as d:
            f = secret_file(d)
            with patch('httpx.get', return_value=response(200, [])), \
                    patch('httpx.post', return_value=response(201, {'id': '1', 'key_name': 'API_KEY'})) as post:
                self.assertEqual(self.run_quiet(s.set_secret, BASE, 't', 'app', 'API_KEY', f), 'created')
            self.assertEqual(post.call_args.args[0], f'{BASE}/api/v1/actions/apps/app/secrets')
            self.assertEqual(post.call_args.kwargs['json'], {'key_name': 'API_KEY', 'value': VALUE, 'description': ''})
            self.assertNotIn(VALUE, post.call_args.args[0])
            self.assertNotIn(VALUE, str(post.call_args.kwargs['headers']))

    def test_existing_key_is_updated(self):
        with tempfile.TemporaryDirectory() as d:
            f = secret_file(d)
            listing = [{'id': 'sid', 'key_name': 'API_KEY'}]
            with patch('httpx.get', return_value=response(200, listing)), \
                    patch('httpx.put', return_value=response(200, {})) as put:
                self.assertEqual(self.run_quiet(s.set_secret, BASE, 't', 'app', 'API_KEY', f), 'updated')
            self.assertEqual(put.call_args.args[0], f'{BASE}/api/v1/actions/secrets/sid')
            self.assertEqual(put.call_args.kwargs['json'], {'value': VALUE})

    def test_failure_message_has_no_value(self):
        with tempfile.TemporaryDirectory() as d:
            f = secret_file(d)
            with patch('httpx.get', return_value=response(200, [])), \
                    patch('httpx.post', return_value=response(422, {'detail': VALUE})):
                with self.assertRaises(RuntimeError) as cm:
                    self.run_quiet(s.set_secret, BASE, 't', 'app', 'API_KEY', f)
            self.assertNotIn(VALUE, str(cm.exception))

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


if __name__ == '__main__':
    unittest.main()
