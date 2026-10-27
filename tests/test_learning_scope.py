"""Offline course checks and ordinary workspace compatibility."""
import contextlib,io,json,sys,tempfile,types,unittest
from pathlib import Path
from unittest import mock
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import aigo_learning_scope as scope
import aigo_publish as publish
import aigo_sync as sync
import aigo_compile as compile_tool
import aigo_auth
APP='22222222-2222-4222-8222-222222222222'
ROLE='11111111-1111-4111-8111-111111111111'
BASE='https://course.ai-go.app'

class LearningScopeTests(unittest.TestCase):
    def fixture(self,root):
        (root/'.aigo').mkdir()
        config={'base_url':BASE,'email':'student@example.test','apps':{'practice':{'kind':'custom','id':APP,'slug':'practice'}}}
        profile={'tenant_url':BASE,'student_email':'student@example.test','role_id':ROLE,'apps':{'practice':APP}}
        for name,value in [('config.json',config),('learning.json',profile)]:
            (root/'.aigo'/name).write_text(json.dumps(value),encoding='utf-8')
        return {'id':APP,'slug':'practice','access_mode':'internal','access_role_ids':[ROLE],'status':'published','vfs_state':{}}
    def response(self,value):return types.SimpleNamespace(raise_for_status=lambda:None,json=lambda:value)
    def test_ordinary_workspace_no_network_or_behavior_change(self):
        with tempfile.TemporaryDirectory() as temp,mock.patch.object(Path,'cwd',return_value=Path(temp)),mock.patch.dict('os.environ',{},clear=True),mock.patch('httpx.get') as get:
            self.assertEqual(scope.guard_learning_write(BASE,'fake',app_id=APP),{'course_scope':'not-applicable'})
            get.assert_not_called()
    def test_course_marker_without_setup_stops_before_network(self):
        with tempfile.TemporaryDirectory() as temp,mock.patch.dict('os.environ',{},clear=True):
            root=Path(temp);(root/'AGENTS.md').write_text('<!-- aigo-learning-workspace -->')
            with mock.patch.object(Path,'cwd',return_value=root),mock.patch('httpx.get') as get:
                with self.assertRaises(FileNotFoundError):scope.guard_learning_write(BASE,'fake',app_id=APP)
                get.assert_not_called()
    def test_wrong_app_stops_before_identity_or_mutation(self):
        with tempfile.TemporaryDirectory() as temp,mock.patch.dict('os.environ',{},clear=True):
            root=Path(temp);self.fixture(root)
            with mock.patch.object(Path,'cwd',return_value=root),mock.patch('httpx.get') as get:
                with self.assertRaises(ValueError):scope.guard_learning_write(BASE,'fake',app_id='33333333-3333-4333-8333-333333333333')
                get.assert_not_called()
    def test_wrong_identity_stops_before_reading_app(self):
        with tempfile.TemporaryDirectory() as temp,mock.patch.dict('os.environ',{},clear=True):
            root=Path(temp);self.fixture(root)
            with mock.patch.object(Path,'cwd',return_value=root),mock.patch('httpx.get',return_value=self.response({'email':'teacher@example.test'})),mock.patch('aigo_auth.get_app_info') as info:
                with self.assertRaises(ValueError):scope.guard_learning_write(BASE,'fake',app_id=APP)
                info.assert_not_called()
    def test_same_identity_app_and_group_pass_without_claiming_isolation(self):
        with tempfile.TemporaryDirectory() as temp,mock.patch.dict('os.environ',{},clear=True):
            root=Path(temp);info=self.fixture(root)
            with mock.patch.object(Path,'cwd',return_value=root),mock.patch('httpx.get',return_value=self.response({'email':'student@example.test'})),mock.patch('aigo_auth.get_app_info',return_value=info):
                result=scope.guard_learning_write(BASE,'fake',slug='practice')
                self.assertEqual(result['scope_check'],'passed');self.assertFalse(result['data_isolation_verified'])
    def test_explicit_marker_only_subdirectory_stops_without_network(self):
        with tempfile.TemporaryDirectory() as temp,mock.patch.dict('os.environ',{},clear=True):
            base=Path(temp);ordinary=base/'ordinary';ordinary.mkdir();course=base/'course';child=course/'apps/practice';child.mkdir(parents=True)
            (course/'AGENTS.md').write_text('<!-- aigo-learning-workspace -->')
            with mock.patch.object(Path,'cwd',return_value=ordinary),mock.patch('httpx.get') as get:
                with self.assertRaises(FileNotFoundError):scope.guard_learning_write(BASE,'fake',app_id=APP,workspace=child)
                get.assert_not_called()
    def test_full_deploy_preserves_scope_between_helpers_and_resets_after_error(self):
        with tempfile.TemporaryDirectory() as temp,mock.patch.dict('os.environ',{},clear=True):
            base=Path(temp);ordinary=base/'ordinary';ordinary.mkdir();course=base/'course';course.mkdir();valid=self.fixture(course);child=course/'apps/practice';child.mkdir(parents=True)
            wrong={**valid,'access_role_ids':[]}
            with mock.patch.object(Path,'cwd',return_value=ordinary),mock.patch('httpx.get',return_value=self.response({'email':'student@example.test'})) as get,mock.patch('aigo_auth.get_app_info',side_effect=[valid,valid,wrong]),mock.patch('httpx.patch') as patch,mock.patch('httpx.post') as post:
                with self.assertRaises(ValueError):publish.full_deploy(BASE,'fake',APP,'practice',str(child))
                self.assertEqual(sum(c.args[0].endswith('/auth/me') for c in get.call_args_list),2);patch.assert_not_called();post.assert_not_called()
                before=get.call_count
                self.assertIsNone(scope._COURSE_WORKSPACE.get())
                self.assertEqual(scope.guard_learning_write(BASE,'fake',app_id=APP),{'course_scope':'not-applicable'})
                self.assertEqual(get.call_count,before)
    def test_all_custom_mutation_helpers_recheck_group_including_skip_preflight(self):
        for name,call in [
            ('publish',lambda:publish.publish_app(BASE,'fake',APP)),
            ('publish-skip-egress',lambda:publish.publish_app(BASE,'fake',APP,skip_preflight=True)),
            ('sync',lambda:sync.sync_to_cloud(BASE,'fake',APP,{},1)),
            ('delete',lambda:sync.delete_remote_files(BASE,'fake',APP,['actions/test.py'],1)),
            ('compile',lambda:compile_tool.compile_app(BASE,'fake','practice')),
            ('full-deploy',lambda:publish.full_deploy(BASE,'fake',APP,'practice','.'))]:
            with self.subTest(name=name),tempfile.TemporaryDirectory() as temp,mock.patch.dict('os.environ',{},clear=True):
                root=Path(temp);info=self.fixture(root);info['access_role_ids']=[]
                with mock.patch.object(Path,'cwd',return_value=root),mock.patch('httpx.get',return_value=self.response({'email':'student@example.test'})),mock.patch('aigo_auth.get_app_info',return_value=info),mock.patch('httpx.post') as post,mock.patch('httpx.patch') as patch,mock.patch('httpx.request') as request:
                    with self.assertRaises(ValueError):call()
                    post.assert_not_called();patch.assert_not_called();request.assert_not_called()

if __name__=='__main__':unittest.main()
