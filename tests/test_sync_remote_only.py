"""Offline contract tests: 本機已刪、遠端還在的 actions/ 檔不得被 sync 安靜地留下。

python -m unittest discover -s tests
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import httpx
from aigo_sync import RemoteOnlyFilesError, remote_only_actions, sync_to_cloud

BASE = 'https://test.invalid'
LOCAL = {'actions/keep.py': 'new', 'actions/manifest.json': '{"keep": {}}', 'src/App.tsx': ''}
REMOTE = {
    'actions/keep.py': 'old',
    'actions/manifest.json': '{"keep": {}, "_probe_kb": {}}',
    'actions/_probe_kb.py': 'probe',
    'actions/_shared/util.py': 'shared',
    'src/App.tsx': '',
    'src/old_page.tsx': '',
    'src/api.ts': '',
    '_template.json': '{}',
}
STALE = ['actions/_probe_kb.py', 'actions/_shared/util.py']


def response(status, data):
    return httpx.Response(status, json=data, request=httpx.Request('GET', BASE))


def app_info(vfs, version):
    return {'vfs_state': vfs, 'vfs_version': version}


class RemoteOnlyActionsTest(unittest.TestCase):
    def test_only_actions_paths_missing_locally_are_reported(self):
        self.assertEqual(remote_only_actions(LOCAL, REMOTE), STALE)

    def test_protected_paths_are_never_reported(self):
        with patch('aigo_sync.PROTECTED_FILES', {'actions/_probe_kb.py'}):
            self.assertEqual(remote_only_actions(LOCAL, REMOTE), ['actions/_shared/util.py'])

    def test_nothing_reported_when_local_covers_remote_actions(self):
        self.assertEqual(remote_only_actions(REMOTE, REMOTE), [])
        self.assertEqual(remote_only_actions(LOCAL, {}), [])


class SyncRemoteOnlyTest(unittest.TestCase):
    def run_sync(self, remote, after_patch, **kwargs):
        infos = [app_info(after_patch, 8)]
        with patch('aigo_limits.get_limits', return_value=None), \
                patch('aigo_sync.get_remote_vfs', return_value=(remote, 7)), \
                patch('httpx.patch', return_value=response(200, {'vfs_version': 8})) as write, \
                patch('httpx.request', return_value=response(200, {'vfs_version': 9})) as delete, \
                patch('aigo_auth.get_app_info', side_effect=infos), \
                patch('builtins.print') as out:
            try:
                result = sync_to_cloud(BASE, 't', 'app', LOCAL, 7, **kwargs)
                error = None
            except Exception as exc:  # noqa: BLE001 - 測試要看例外型別
                result, error = None, exc
        printed = '\n'.join(str(c.args[0]) for c in out.call_args_list if c.args)
        return result, error, write, delete, printed

    def test_default_aborts_before_writing_and_names_the_files(self):
        _, error, write, delete, _ = self.run_sync(REMOTE, {**REMOTE, **LOCAL})
        self.assertIsInstance(error, RemoteOnlyFilesError)
        self.assertEqual(error.paths, STALE)
        self.assertIn('actions/_probe_kb.py', str(error))
        self.assertIn('on_remote_only', str(error))
        write.assert_not_called()
        delete.assert_not_called()

    def test_keep_writes_without_deleting_and_still_names_the_files(self):
        result, error, write, delete, printed = self.run_sync(REMOTE, {**REMOTE, **LOCAL}, on_remote_only='keep')
        self.assertIsNone(error)
        self.assertEqual(result, {'vfs_version': 8})
        write.assert_called_once()
        delete.assert_not_called()
        self.assertIn('actions/_probe_kb.py', printed)

    def test_sync_itself_never_deletes(self):
        # files 可能只是部分檔案；刪除只由讀了完整本機專案的 full_deploy() 做
        with patch('aigo_sync.get_remote_vfs') as read, patch('httpx.patch') as write, patch('httpx.request') as delete:
            with self.assertRaises(ValueError):
                sync_to_cloud(BASE, 't', 'app', LOCAL, 7, on_remote_only='delete')
            read.assert_not_called()
            write.assert_not_called()
            delete.assert_not_called()

    def test_no_stale_actions_means_plain_sync(self):
        remote = {k: v for k, v in REMOTE.items() if k not in STALE}
        result, error, write, delete, _ = self.run_sync(remote, {**remote, **LOCAL})
        self.assertIsNone(error)
        self.assertEqual(result, {'vfs_version': 8})
        write.assert_called_once()
        delete.assert_not_called()

    def test_unknown_mode_is_rejected_before_any_request(self):
        with patch('aigo_sync.get_remote_vfs') as read, patch('httpx.patch') as write:
            with self.assertRaises(ValueError):
                sync_to_cloud(BASE, 't', 'app', LOCAL, 7, on_remote_only='prune')
            read.assert_not_called()
            write.assert_not_called()


class FullDeployRemoteOnlyTest(unittest.TestCase):
    def test_full_deploy_forwards_mode_and_stops_on_abort(self):
        from aigo_publish import full_deploy
        with patch('aigo_auth.get_app_info', return_value={'id': 'app', 'name': 'n'}), \
                patch('aigo_sync.read_local_files', return_value=LOCAL), \
                patch('aigo_sync.get_remote_vfs', return_value=(REMOTE, 7)), \
                patch('aigo_sync.sync_to_cloud', side_effect=RemoteOnlyFilesError(STALE)) as sync, \
                patch('aigo_compile.compile_app') as compile_app, \
                patch('builtins.print'):
            with self.assertRaises(RemoteOnlyFilesError):
                full_deploy(BASE, 't', 'app', 'slug', '/tmp/project', on_remote_only='abort')
            self.assertEqual(sync.call_args.kwargs['on_remote_only'], 'abort')
            compile_app.assert_not_called()

    def deploy(self, remote, **kwargs):
        from aigo_publish import full_deploy
        calls = []
        with patch('aigo_auth.get_app_info', return_value={'id': 'app', 'name': 'n', 'status': 'published'}), \
                patch('aigo_sync.read_local_files', return_value=LOCAL), \
                patch('aigo_sync.get_remote_vfs', return_value=(remote, 7)), \
                patch('aigo_sync.delete_remote_files',
                      side_effect=lambda *a, **k: calls.append(('delete', a)) or {'vfs_version': 8}), \
                patch('aigo_sync.sync_to_cloud',
                      side_effect=lambda *a, **k: calls.append(('sync', a, k)) or {'vfs_version': 9}), \
                patch('aigo_compile.compile_app', return_value={'success': True, 'skipped_files': []}), \
                patch('aigo_publish.publish_app', return_value={'status': 'published'}) as publish, \
                patch('builtins.print'):
            full_deploy(BASE, 't', 'app', 'slug', '/tmp/project', **kwargs)
        return calls, publish

    def test_delete_removes_only_the_approved_paths_before_syncing(self):
        calls, publish = self.deploy(REMOTE, on_remote_only='delete', delete_paths=list(STALE),
                                     confirm_removal=True)
        self.assertEqual([c[0] for c in calls], ['delete', 'sync'])
        self.assertEqual(calls[0][1], (BASE, 't', 'app', STALE, 7))
        self.assertEqual(calls[1][1], (BASE, 't', 'app', LOCAL, 8))
        self.assertEqual(calls[1][2], {'on_remote_only': 'keep'})
        self.assertEqual(publish.call_args.kwargs, {'confirm_removal': True})

    def test_delete_leaves_stale_paths_the_user_did_not_approve(self):
        # 確認之後別人才加的 action、或用戶決定留下的共用模組：不在清單內就不刪
        calls, _ = self.deploy(REMOTE, on_remote_only='delete', delete_paths=['actions/_probe_kb.py'])
        self.assertEqual(calls[0][1], (BASE, 't', 'app', ['actions/_probe_kb.py'], 7))
        self.assertEqual(calls[1][2], {'on_remote_only': 'keep'})

    def test_delete_requires_approved_paths(self):
        for kwargs in ({}, {'delete_paths': []}):
            with self.assertRaises(ValueError):
                self.deploy(REMOTE, on_remote_only='delete', **kwargs)

    def test_delete_paths_without_delete_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            self.deploy(REMOTE, on_remote_only='keep', delete_paths=['actions/_probe_kb.py'])

    def test_delete_refuses_paths_that_are_not_remote_only_actions(self):
        # 本機還有的、actions/ 以外的、遠端根本沒有的——任何一條混進來都整個拒絕，什麼都不刪
        for bad in ('actions/keep.py', 'src/old_page.tsx', '_template.json', 'actions/gone.py'):
            calls = []
            with self.subTest(bad=bad):
                from aigo_publish import full_deploy
                with patch('aigo_auth.get_app_info', return_value={'id': 'app', 'name': 'n'}), \
                        patch('aigo_sync.read_local_files', return_value=LOCAL), \
                        patch('aigo_sync.get_remote_vfs', return_value=(REMOTE, 7)), \
                        patch('aigo_sync.delete_remote_files',
                              side_effect=lambda *a, **k: calls.append('delete')), \
                        patch('aigo_sync.sync_to_cloud', side_effect=lambda *a, **k: calls.append('sync')), \
                        patch('builtins.print'):
                    with self.assertRaises(ValueError):
                        full_deploy(BASE, 't', 'app', 'slug', '/tmp/project', on_remote_only='delete',
                                    delete_paths=['actions/_probe_kb.py', bad])
                self.assertEqual(calls, [])

    def test_abort_message_separates_non_action_files_and_flags_missing_local_actions(self):
        err = RemoteOnlyFilesError(STALE + ['actions/manifest.json'], local_has_actions=False)
        self.assertEqual(err.actions, ['actions/_probe_kb.py'])
        self.assertEqual(err.others, ['actions/_shared/util.py', 'actions/manifest.json'])
        self.assertIn('共用模組', str(err))
        self.assertIn('本機沒有任何 actions/ 檔', str(err))
        self.assertIn('delete_paths', str(err))
        self.assertNotIn('本機沒有任何 actions/ 檔', str(RemoteOnlyFilesError(STALE)))

    def test_keep_is_forwarded_and_nothing_is_deleted(self):
        calls, _ = self.deploy(REMOTE, on_remote_only='keep')
        self.assertEqual([c[0] for c in calls], ['sync'])
        self.assertEqual(calls[0][2], {'on_remote_only': 'keep'})

    def test_unknown_mode_is_rejected_before_any_request(self):
        from aigo_publish import full_deploy
        with patch('aigo_auth.get_app_info') as info, patch('aigo_sync.get_remote_vfs') as read:
            with self.assertRaises(ValueError):
                full_deploy(BASE, 't', 'app', 'slug', '/tmp/project', on_remote_only='prune')
            info.assert_not_called()
            read.assert_not_called()


if __name__ == '__main__':
    unittest.main()
