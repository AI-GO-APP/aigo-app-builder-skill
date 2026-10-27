"""Offline tests for aigo_auth.browser_login: the local callback that receives the token from the tenant's /auth/cli page."""
import base64
import contextlib
import io
import json
import os
import socket
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import aigo_auth as a

BASE = 'https://t.ai-go.app'


def fake_jwt(exp):
    part = base64.urlsafe_b64encode(json.dumps({'exp': exp}).encode()).decode().rstrip('=')
    return f'h.{part}.s'


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def post(port, body, origin=BASE, path='/callback', method='POST'):
    req = urllib.request.Request(f'http://127.0.0.1:{port}{path}', data=json.dumps(body).encode() if body is not None else None,
                                 method=method, headers={'Content-Type': 'application/json', 'Origin': origin})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


class BrowserLoginTest(unittest.TestCase):
    def run_login(self, port, timeout=5):
        out = {}

        def target():
            with contextlib.redirect_stdout(io.StringIO()) as buf:
                try:
                    out['result'] = a.browser_login(BASE, timeout=timeout, open_browser=False)
                except RuntimeError as e:
                    out['error'] = str(e)
            out['stdout'] = buf.getvalue()

        t = threading.Thread(target=target)
        with patch.dict(os.environ, {'AIGO_LOGIN_CALLBACK_PORT': str(port)}):
            t.start()
            for _ in range(50):  # 等伺服器起來
                with contextlib.suppress(OSError), socket.create_connection(('127.0.0.1', port), timeout=0.1):
                    break
                time.sleep(0.05)
        return t, out

    def test_receives_token_and_derives_expiry_from_jwt(self):
        port = free_port()
        t, out = self.run_login(port)
        token = fake_jwt(time.time() + 3600)
        status, headers, _ = post(port, {'access_token': token, 'refresh_token': 'r1'})
        t.join(5)
        self.assertEqual(status, 200)
        self.assertEqual(headers.get('Access-Control-Allow-Origin'), BASE)
        self.assertEqual(out['result']['access_token'], token)
        self.assertEqual(out['result']['refresh_token'], 'r1')
        self.assertTrue(3500 < out['result']['expires_in'] <= 3600)
        self.assertIn(f'{BASE}/auth/cli?port={port}', out['stdout'])
        self.assertNotIn(token, out['stdout'])

    def test_preflight_allows_private_network(self):
        port = free_port()
        t, out = self.run_login(port, timeout=2)
        status, headers, _ = post(port, None, method='OPTIONS')
        self.assertEqual(status, 204)
        self.assertEqual(headers.get('Access-Control-Allow-Private-Network'), 'true')
        post(port, {'access_token': fake_jwt(time.time() + 60)})
        t.join(5)

    def test_rejects_missing_token_and_foreign_origin_then_keeps_waiting(self):
        port = free_port()
        t, out = self.run_login(port)
        self.assertEqual(post(port, {'refresh_token': 'x'})[0], 400)
        self.assertEqual(post(port, {'access_token': 'evil'}, origin='https://evil.example')[0], 403)
        self.assertEqual(post(port, {'access_token': 'x'}, path='/other')[0], 404)
        self.assertEqual(post(port, {'access_token': fake_jwt(time.time() + 60), 'expires_in': 120})[0], 200)
        t.join(5)
        self.assertEqual(out['result']['expires_in'], 120)

    def test_timeout_raises(self):
        port = free_port()
        t, out = self.run_login(port, timeout=0.5)
        t.join(5)
        self.assertIn('login --browser', out['error'])


class OriginTest(unittest.TestCase):
    def test_origin_allowed(self):
        self.assertTrue(a._origin_allowed(BASE, BASE))
        self.assertTrue(a._origin_allowed('https://other.ai-go.app', BASE))
        self.assertFalse(a._origin_allowed('https://ai-go.app.evil.com', BASE))
        self.assertFalse(a._origin_allowed('', BASE))


if __name__ == '__main__':
    unittest.main()
