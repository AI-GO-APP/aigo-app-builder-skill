"""Offline contract tests: python -m unittest discover -s tests."""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import httpx
import aigo_cron_health as cron
import aigo_env_diff as env

SECRET = 'do-not-print-this-value-9f8e7d'
A = {'env_vars': {'SHARED_KEY': SECRET, 'ONLY_A': 'x', 'EMPTY_A': '', 'DIFF': 'one', 'BUILD_KEY': 'v'},
     'env_availability': {'BUILD_KEY': 'both'}, 'always_on': False, 'persistent_disk': True}
B = {'env_vars': {'SHARED_KEY': SECRET, 'ONLY_B': 'y', 'EMPTY_A': 'set', 'DIFF': 'two', 'BUILD_KEY': 'v'},
     'env_availability': {'BUILD_KEY': 'runtime'}, 'always_on': True, 'persistent_disk': False}


def response(status, data):
    return httpx.Response(status, json=data, request=httpx.Request('GET', 'https://test.invalid'))


class EnvDiffTest(unittest.TestCase):
    def test_diff_summary(self):
        s = env.diff_settings(A, B)['summary']
        self.assertEqual(s['only_in_a'], ['ONLY_A'])
        self.assertEqual(s['only_in_b'], ['ONLY_B'])
        self.assertEqual(s['empty_in_a'], ['EMPTY_A'])
        self.assertEqual(s['empty_in_b'], [])
        self.assertEqual(s['same_value'], ['BUILD_KEY', 'SHARED_KEY'])
        self.assertEqual(s['availability_differs'], ['BUILD_KEY'])

    def test_no_value_or_hash_in_any_output(self):
        import hashlib
        digest = hashlib.sha256(SECRET.encode()).hexdigest()
        result = env.diff_settings(A, B)
        for text in (env.format_text(result, {'a': 'a', 'b': 'b'}), json.dumps(result)):
            self.assertNotIn(SECRET, text)
            self.assertNotIn(digest[:8], text)
        exp = env.check_expect(A, ['SHARED_KEY'])
        self.assertNotIn(SECRET, env.format_text(exp, {'app': 'a'}) + json.dumps(exp))

    def test_expect_parsing_and_gate(self):
        keys, invalid, injected = env.parse_expect(
            '# header\nSHARED_KEY  # note\n\nEMPTY_A\nMISSING\nbad-key\nSHARED_KEY\nAIGO_DATA_DIR\nPORT\n')
        self.assertEqual(keys, ['SHARED_KEY', 'EMPTY_A', 'MISSING'])
        self.assertEqual(invalid, ['bad-key'])
        self.assertEqual(injected, ['AIGO_DATA_DIR', 'PORT'])
        s = env.check_expect(A, keys)['summary']
        self.assertEqual(s['missing'], ['MISSING'])
        self.assertEqual(s['empty'], ['EMPTY_A'])

    def expect_file(self, text):
        with tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False) as f:
            f.write(text)
        self.addCleanup(os.unlink, f.name)
        return f.name

    def run_main(self, argv, get=None, token=None):
        auth = patch('aigo_auth.get_token', side_effect=token) if token else patch('aigo_auth.get_token', return_value='t')
        err, out = io.StringIO(), io.StringIO()
        with auth, patch('aigo_auth.resolve_base_url', return_value='https://test.invalid'), \
                patch('httpx.get', return_value=get), redirect_stdout(out), redirect_stderr(err):
            code = env.main(argv)
        return code, out.getvalue() + err.getvalue()

    def test_403_exit_2_without_body(self):
        code, text = self.run_main(['--a', 'x', '--b', 'y'], get=response(403, {'detail': SECRET}))
        self.assertEqual(code, 2)
        self.assertIn('403', text)
        self.assertNotIn(SECRET, text)

    def test_login_failure_exit_2(self):
        failure = httpx.HTTPStatusError('bad', request=httpx.Request('POST', 'https://test.invalid'),
                                        response=httpx.Response(401, text=SECRET))
        for exc in (failure, RuntimeError(SECRET), httpx.ConnectError(SECRET)):
            with self.subTest(exc=type(exc).__name__):
                code, text = self.run_main(['--a', 'x', '--b', 'y'], token=exc)
                self.assertEqual(code, 2)
                self.assertNotIn(SECRET, text)

    def test_missing_env_vars_is_shape_error(self):
        for body in ({'always_on': False}, {'env_vars': None}, [1]):
            with self.subTest(body=body):
                self.assertEqual(self.run_main(['--a', 'x', '--b', 'y'], get=response(200, body))[0], 2)

    def test_unreadable_expect_file_and_injected_keys(self):
        self.assertEqual(self.run_main(['--app', 'id', '--expect', '/nonexistent/keys.txt'], get=response(200, A))[0], 2)
        code, text = self.run_main(['--app', 'id', '--expect', self.expect_file('SHARED_KEY\nAIGO_TOKEN\nPORT\n')],
                                   get=response(200, A))
        self.assertEqual(code, 0)
        self.assertIn('AIGO_TOKEN', text)

    def test_main_exit_codes_and_reads_only(self):
        name = self.expect_file('SHARED_KEY\nMISSING\n')
        with patch('aigo_auth.get_token', return_value='t'), patch('aigo_auth.resolve_base_url', return_value='https://test.invalid'), \
                patch('httpx.get', return_value=response(200, A)) as get, redirect_stdout(io.StringIO()) as out:
            self.assertEqual(env.main(['--app', 'id', '--expect', name]), 1)
            self.assertEqual(env.main(['--a', 'x', '--b', 'y', '--json']), 0)
            self.assertTrue(get.call_args.args[0].endswith('/api/v1/hosted-apps/y/runtime-settings'))
        self.assertNotIn(SECRET, out.getvalue())


NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def mk(**kw):
    c = {'id': 'c1', 'app_id': 'app', 'action_name': 'tick', 'name': 'n', 'schedule_kind': 'every_n_minutes',
         'schedule_fields': {'n': 10}, 'timezone': 'Asia/Taipei', 'active': True, 'paused_reason': None,
         'last_status': 'success', 'lastcall': (NOW - timedelta(minutes=5)).isoformat(),
         'nextcall': (NOW + timedelta(minutes=5)).isoformat(), 'consecutive_errors': 0, 'consecutive_403': 0,
         'params': {'token': SECRET}}
    c.update(kw)
    return c


class CronHealthTest(unittest.TestCase):
    def codes(self, c):
        return {(f['level'], f['code']) for f in cron.assess(c, NOW)}

    def test_healthy(self):
        self.assertEqual(self.codes(mk()), set())

    def test_flags(self):
        self.assertIn(('red', 'paused'), self.codes(mk(active=False, paused_reason='consecutive_errors')))
        self.assertIn(('yellow', 'paused'), self.codes(mk(active=False, paused_reason='manual')))
        self.assertIn(('yellow', 'paused'), self.codes(mk(active=False, paused_reason=None)))
        self.assertIn(('red', 'paused'), self.codes(mk(active=False, paused_reason='something_new')))
        self.assertIn(('red', 'last_status'), self.codes(mk(last_status='timeout')))
        self.assertIn(('yellow', 'last_status'), self.codes(mk(last_status='error', consecutive_errors=1)))
        self.assertIn(('red', 'last_status'), self.codes(mk(last_status='error', consecutive_errors=5)))
        self.assertIn(('yellow', 'last_status'), self.codes(mk(last_status='skipped')))
        past = (NOW - timedelta(minutes=1)).isoformat()
        self.assertIn(('red', 'stale'), self.codes(mk(lastcall=(NOW - timedelta(minutes=21)).isoformat(), nextcall=past)))
        self.assertIn(('yellow', 'stale'), self.codes(mk(lastcall=(NOW - timedelta(minutes=21)).isoformat())))
        self.assertNotIn('stale', {c for _, c in self.codes(mk(lastcall=(NOW - timedelta(minutes=19)).isoformat(), nextcall=past))})
        self.assertIn(('red', 'stale'), self.codes(mk(schedule_kind='daily', schedule_fields={'hh': 1, 'mm': 0}, nextcall=None,
                                                      lastcall=(NOW - timedelta(days=3)).isoformat().replace('+00:00', 'Z'))))
        for kind, fields in (('every_n_minutes', {'n': '10'}), ('every_n_minutes', None), ('cron_expr', {})):
            self.assertIn(('yellow', 'interval_unknown'), self.codes(mk(schedule_kind=kind, schedule_fields=fields)))
        self.assertIn(('red', 'consecutive_errors'), self.codes(mk(consecutive_errors=5)))
        self.assertIn(('yellow', 'consecutive_errors'), self.codes(mk(consecutive_errors=2)))
        self.assertIn(('red', 'consecutive_403'), self.codes(mk(consecutive_403=1)))
        self.assertIn(('yellow', 'never_ran'), self.codes(mk(lastcall=None)))

    def test_schedule_text_never_crashes(self):
        for fields in ({'hh': None, 'mm': None}, {'hh': '9', 'mm': 'x'}, {}, None):
            cron._schedule_text({'kind': 'daily', 'fields': fields, 'timezone': None})
        self.assertIn('09:05', cron._schedule_text({'kind': 'daily', 'fields': {'hh': '9', 'mm': 5}}))
        self.assertIn('?:?', cron._schedule_text({'kind': 'weekly', 'fields': {'weekday': 1}}))

    def test_paginated_shape_is_unknown(self):
        with patch('httpx.get', return_value=response(200, {'items': [], 'total': 3})), self.assertRaises(ValueError):
            cron.fetch_crons('https://test.invalid', 't', None)

    def test_expect_action_and_no_params_leak(self):
        r = cron.check([mk()], NOW, 'app', ['tick', 'run_other'])
        self.assertEqual(r['missing_actions'], ['run_other'])
        self.assertTrue(r['red'])
        self.assertFalse(cron.check([mk()], NOW, 'app', ['tick'])['red'])
        self.assertNotIn(SECRET, cron.format_text(r) + json.dumps(r))
        self.assertIn(cron.NOTE, cron.format_text(r))

    def test_main_only_gets(self):
        with patch('aigo_auth.get_token', return_value='t'), patch('aigo_auth.resolve_base_url', return_value='https://test.invalid'), \
                patch('httpx.get', return_value=response(200, [])) as get, patch('httpx.post') as post, \
                patch('httpx.patch') as p, patch('httpx.delete') as d, redirect_stdout(io.StringIO()):
            self.assertEqual(cron.main(['--app', 'app', '--expect-action', 'tick']), 1)
            self.assertEqual(get.call_args.args[0], 'https://test.invalid/api/v1/builder/apps/app/crons')
            self.assertEqual(cron.main(['--all']), 0)
            self.assertEqual(get.call_args.args[0], 'https://test.invalid/api/v1/app-crons')
            for m in (post, p, d):
                m.assert_not_called()
        with patch('aigo_auth.get_token', return_value='t'), patch('aigo_auth.resolve_base_url', return_value='https://test.invalid'), \
                patch('httpx.get', return_value=response(403, {'detail': SECRET})), redirect_stdout(io.StringIO()), \
                redirect_stderr(io.StringIO()) as err:
            self.assertEqual(cron.main(['--all']), 2)
        self.assertIn('403', err.getvalue())
        self.assertNotIn(SECRET, err.getvalue())
        with patch('aigo_auth.get_token', side_effect=RuntimeError(SECRET)), redirect_stdout(io.StringIO()), \
                redirect_stderr(io.StringIO()) as err:
            self.assertEqual(cron.main(['--all']), 2)
        self.assertNotIn(SECRET, err.getvalue())


if __name__ == '__main__':
    unittest.main()
