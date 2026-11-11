from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
from sunday_blue.storage import Config,Store
from sunday_blue.modules.database import ModuleDB,day
from sunday_blue.modules.duties import Duties,assigned
from sunday_blue.modules.duty_tools import dispatch,schema
from sunday_blue.modules.organizer import Organizer
from sunday_blue.capabilities import TurnCapabilities
from sunday_blue.agent import Agent,system_prompt
from sunday_blue.native_plugins import enabled
from sunday_blue.role_lifecycle import RoleLifecycle
ROOT=Path(__file__).resolve().parents[1]

class DutyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'tests',prefix='sunday-test-');self.config=Config(self.temp.name);self.db=ModuleDB(self.config.root);self.duties=Duties(self.db)
    def tearDown(self):self.temp.cleanup()
    def test_slot_reassignment_preserves_queue_and_removes_old_rights(self):
        row=self.duties.capture('原文','请记下这段原文',files='notes.txt');self.duties.assign('recorder','mia')
        self.assertEqual(assigned(self.config.root,'mia'),['recorder']);self.assertEqual(Duties(self.db).handoffs()[0]['id'],row['id'])
        with self.assertRaises(PermissionError):dispatch(self.config.root,'kia','capture',{'title':'x','body':'x'},actual_text='x')
        result=dispatch(self.config.root,'mia','capture',{'title':'新记录','body':'new'},actual_text='new');self.assertIn('record_id',result)
        self.assertIn('快速捕获',system_prompt(self.config.root,'mia',self.config.snapshot()))
        self.assertIn('当前没有分配管理职责',system_prompt(self.config.root,'kia',self.config.snapshot()))
        self.assertEqual(len(self.duties.slots()),7)
    def test_handoff_transaction_dedup_failure_and_original_kept(self):
        a=self.duties.capture('A','body',request='归类');b=self.duties.capture('B','body');self.assertEqual(a['id'],b['id'])
        self.duties.fail_handoff(a['id'],'需要确认分类');self.assertEqual(self.duties.handoffs()[0]['status'],'failed')
        self.duties.complete_handoff(a['id'],'生活备忘',title='可检索标题',note='归类完成');self.assertEqual(self.duties.handoffs(),[])
        self.duties.complete_handoff(a['id'],'生活备忘');self.assertEqual(len(self.duties.handoffs(True)),1)
        record=Organizer(self.db).search()[0];self.assertEqual(record['body'],'body');self.assertEqual(record['status'],'proposal')
        with self.db.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM record_revisions').fetchone()[0],1)
    def test_approval_denial_and_assignment_change_prevent_write(self):
        args={'kind':'walk','minutes':20,'intensity':'light'}
        result=dispatch(self.config.root,'red','exercise_record',args,approve=lambda *a:False,actual_text='walk')
        self.assertEqual(result['status'],'denied')
        def reassign(*a):self.duties.assign('exercise','mia');return True
        with self.assertRaises(PermissionError):dispatch(self.config.root,'red','exercise_record',args,approve=reassign,actual_text='walk')
        from sunday_blue.modules.life import Life
        self.assertEqual(Life(self.db).exercises(),[])
    def test_daily_field_isolation_and_capture_requires_user_original(self):
        from sunday_blue.modules.life import Life
        Life(self.db).save_daily(day(),meal='private meal',sleep_hours=8,note='private recovery')
        result=dispatch(self.config.root,'ewa','daily_record',{'day':day(),'meal':'new meal'},approve=lambda *a:True,actual_text='new meal')
        self.assertNotIn('sleep_hours',result);self.assertNotIn('note',result);self.assertEqual(Life(self.db).daily()['sleep_hours'],8)
        with self.assertRaises(PermissionError):dispatch(self.config.root,'ewa','daily_record',{'day':day(),'sleep_hours':2},approve=lambda *a:True,actual_text='x')
        result=dispatch(self.config.root,'ewa','summary',{});self.assertEqual(set(result),{'day','diet'})
        with self.assertRaises(ValueError):dispatch(self.config.root,'kia','capture',{'title':'x','body':'inferred'},actual_text='raw words')
        with self.assertRaises(PermissionError):dispatch(self.config.root,'kia','organize',{'id':'none','category':'生活备忘'})
    def test_on_demand_tools_and_explicit_disable(self):
        cfg=self.config.snapshot();quiet=TurnCapabilities(self.config.root,cfg,'red','你好')
        self.assertNotIn('duties',quiet.active);self.assertIn('duties',quiet.catalog)
        route=TurnCapabilities(self.config.root,cfg,'red','记录运动');self.assertTrue(route.snapshot()['features']['duties'])
        self.assertIn('exercise_record',schema(self.config.root,'red')[0]['input_schema']['properties']['action']['enum'])
        cfg['roles']['red'].setdefault('capabilities',{})['duties']=False
        self.assertNotIn('duties',TurnCapabilities(self.config.root,cfg,'red','运动').catalog)
        self.assertFalse(enabled(self.config.snapshot()|{'_plugin_root':str(self.config.root)},'kia','kia-organizer'))
    def test_role_archive_blocked_only_when_assigned(self):
        life=RoleLifecycle(self.config,Store(self.config.data))
        self.assertTrue(any('固定职责' in s for s in life.dependencies('rui')))
        self.duties.assign('director',None);self.assertFalse(any('固定职责' in s for s in life.dependencies('rui')))
    def test_agent_toolset_real_bridge(self):
        store=Store(self.config.data);sid=store.create('red');cfg=self.config.snapshot();agent=Agent(self.config.root,cfg,store,sid)
        agent.routing=TurnCapabilities(self.config.root,cfg,'red','运动记录');agent.config=agent.routing.snapshot()
        names=[t['name'] for t in agent._toolset()[0]];self.assertIn('duty_action',names)
        self.duties.assign('exercise','mia');self.assertNotIn('duty_action',[t['name'] for t in agent._toolset()[0]])
