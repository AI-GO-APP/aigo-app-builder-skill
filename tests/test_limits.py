"""Offline contract tests: python -m unittest discover -s tests."""
import sys
import unittest
import warnings
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import httpx
from aigo_limits import get_limits, check_vfs
from aigo_compile import compile_app, format_skipped_files
from aigo_sync import sync_to_cloud

LIMITS = {'vfs': {'max_file_count': 2, 'max_file_size_bytes': 6, 'build_timeout_ms': 99}}


def response(status, data):
    return httpx.Response(status, json=data, request=httpx.Request('GET', 'https://test.invalid'))


class LimitsTest(unittest.TestCase):
    def test_discovery_reads_target_app(self):
        with patch('httpx.get', return_value=response(200, LIMITS)) as get:
            self.assertEqual(get_limits('https://test.invalid/', 'token', 'app-id'), LIMITS)
            self.assertEqual(get.call_args.args[0], 'https://test.invalid/api/v1/builder/apps/app-id/limits')
            self.assertEqual(get.call_args.kwargs['headers']['Authorization'], 'Bearer token')

    def test_old_or_unavailable_service_is_unknown(self):
        for status, data in [(404, {}), (503, {}), (200, {}), (200, {'vfs': {'max_file_count': True}})]:
            with self.subTest(status=status, data=data), patch('httpx.get', return_value=response(status, data)):
                with self.assertWarns(UserWarning):
                    self.assertIsNone(get_limits('https://test.invalid', 't', 'a'))

    def test_auth_failure_is_not_swallowed(self):
        with patch('httpx.get', return_value=response(403, {})), self.assertRaises(httpx.HTTPStatusError):
            get_limits('https://test.invalid', 't', 'a')

    def test_utf8_count_and_skip_semantics(self):
        skipped = check_vfs({'a.ts': '中中', 'b.ts': '中中中', 'tsconfig.json': '{}', 'node_modules/x': ''}, LIMITS)
        self.assertEqual([x['path'] for x in skipped], ['b.ts', 'node_modules/x', 'tsconfig.json'])
        self.assertEqual(skipped[0]['size'], 9)
        self.assertEqual(skipped[0]['reason'], 'exceeds_max_file_size')
        with self.assertRaises(ValueError):
            check_vfs({'a': '', 'b': 'oversized', 'c': ''}, LIMITS)
        self.assertEqual(check_vfs({'../escape': ''}, LIMITS)[0]['reason'], 'path_traversal')

    def test_sync_checks_remote_plus_local_before_writing(self):
        with patch('aigo_limits.get_limits', return_value=LIMITS), patch('aigo_sync.get_remote_vfs', return_value=({'sdk.ts': '', 'old.ts': ''}, 1)), patch('httpx.patch') as write:
            with self.assertRaises(ValueError):
                sync_to_cloud('https://test.invalid', 't', 'a', {'new.ts': ''}, 1)
            write.assert_not_called()

    def test_compile_preserves_and_prints_success_and_failure_diagnostics(self):
        for success in (True, False):
            report = [{'path': 'large.ts', 'size': 9, 'reason': 'exceeds_max_file_size'}]
            data = {'success': success, 'skipped_files': report}
            with patch('httpx.post', return_value=response(200, data)), patch('builtins.print') as out:
                self.assertEqual(compile_app('https://test.invalid', 't', 'a'), data)
                self.assertIn('large.ts', out.call_args.args[0])

    def test_publish_prints_diagnostics_on_success_and_rollback(self):
        from aigo_publish import publish_app
        report = [{'path': 'large.ts', 'size': 9, 'reason': 'exceeds_max_file_size'}]
        with patch('httpx.post', return_value=response(200, {'skipped_files': report})), patch('aigo_auth.get_app_info', return_value={'status': 'published'}), patch('builtins.print') as out:
            result = publish_app('https://test.invalid', 't', 'a', skip_preflight=True)
            self.assertEqual(result['skipped_files'], report)
            self.assertIn('large.ts', out.call_args.args[0])
        with patch('httpx.post', return_value=response(422, {'detail': {'skipped_files': report}})), patch('builtins.print') as out:
            with self.assertRaises(RuntimeError):
                publish_app('https://test.invalid', 't', 'a', skip_preflight=True, auto_rollback=True)
            self.assertIn('large.ts', out.call_args.args[0])

    def test_unknown_is_not_empty(self):
        self.assertEqual(format_skipped_files([]), '')
        self.assertIn('無法確認', format_skipped_files(None))


if __name__ == '__main__':
    unittest.main()
