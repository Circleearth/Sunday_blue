import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from sunday_blue.storage import Config,Store
from sunday_blue.modules.database import ModuleDB,day
from sunday_blue.modules.rewards import Rewards
from sunday_blue.modules.focus import Focus
from sunday_blue.modules.relations import Relations
from sunday_blue.modules.social import Social,recent_context
from sunday_blue.modules.memory_bridge import private_support
from sunday_blue.models import resolve_api

ROOT=Path(__file__).resolve().parents[1]


class ModuleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'tests',prefix='sunday-test-')
        self.config=Config(self.temp.name);self.root=self.config.root;self.store=Store(self.config.data)
        self.db=ModuleDB(self.root);self.rewards=Rewards(self.db);self.time=[0]
        self.focus=Focus(self.db,clock=lambda:self.time[0]);self.relations=Relations(self.db)
        self.social=Social(self.db,self.config);self.config.value['api']['model']='fixture'
    def tearDown(self):self.temp.cleanup()
    def run_focus(self,seconds=125):
        self.focus.start('学习','合成测试','rui')
        for _ in range(seconds//5):self.time[0]+=5;self.focus.checkpoint()
        return self.focus.finish()
    def test_focus_pause_finish_atomic_and_module_owned(self):
        result=self.run_focus();self.assertTrue(result['valid']);self.assertEqual(result['coins_earned'],2)
        self.assertEqual(self.focus.finish(),result)
        self.assertEqual(len(self.focus.records()),1);self.assertEqual(self.rewards.balances()['coins'],2)
        self.relations.project();self.relations.project()
        self.assertEqual(next(r for r in self.relations.list() if r['role_id']=='rui')['affinity'],51)
        self.config.registry.update('rui',state='archived')
        self.assertEqual(len(self.focus.records()),1);self.assertEqual(self.rewards.balances()['coins'],2)
    def test_pause_sleep_restart_and_short_runs_do_not_inflate(self):
        self.focus.start('工作');self.time[0]=10;self.focus.pause();self.time[0]=10000
        self.assertEqual(self.focus.status()['elapsed'],10)
        self.focus.resume();self.time[0]+=300;self.focus.checkpoint()
        self.assertEqual(self.focus.status()['state'],'paused');self.assertEqual(self.focus.status()['elapsed'],10)
        self.assertFalse(self.focus.finish()['valid']);self.assertEqual(self.focus.records(),[])
        self.focus.start('家务');self.time[0]+=20;self.focus.checkpoint()
        restarted=Focus(self.db,clock=lambda:200000)
        self.assertEqual(restarted.status()['state'],'paused');self.assertEqual(restarted.status()['elapsed'],20)
    def test_shop_idempotency_separate_budget_and_gifts(self):
        self.run_focus(300)
        reward=self.rewards.add('现实奖励',2,'budget',cents=100)
        item=self.rewards.redeem(reward,'same-click')
        self.assertEqual(self.rewards.redeem(reward,'same-click')['id'],item['id'])
        self.assertEqual(self.rewards.balances(),{'coins':3,'budget_cents':0})
        with self.assertRaises(ValueError):self.rewards.confirm_budget(item['id'])
        self.rewards.adjust_budget(500,'用户确认预算','budget1')
        self.rewards.confirm_budget(item['id']);self.rewards.confirm_budget(item['id'])
        self.assertEqual(self.rewards.balances(),{'coins':3,'budget_cents':400})
        gift=self.rewards.add('一杯茶的心意',1,'gift',role_id='luna');self.rewards.redeem(gift,'gift1');self.relations.project()
        self.assertEqual(next(r for r in self.relations.list() if r['role_id']=='luna')['affinity'],51)
    def test_relationship_no_absence_penalty_and_negative_daily_bound(self):
        for i in range(5):self.relations.report_setback('rui','明确报告未达成')
        value=next(r for r in self.relations.list() if r['role_id']=='rui')
        self.assertEqual(value['affinity'],49)
        with patch('sunday_blue.modules.relations.time.time',return_value=10**12):
            value=next(r for r in self.relations.list() if r['role_id']=='rui');self.assertAlmostEqual(value['mood'],0)
        self.assertEqual(next(r for r in self.relations.list() if r['role_id']=='mia')['affinity'],50)
    def test_group_private_context_is_speakers_own_and_private_sees_recent_group(self):
        sid=self.store.create('rui');self.store.add(sid,'user','RUI_PRIVATE_MARKER')
        red=self.store.create('red');self.store.add(red,'user','RED_PRIVATE_MARKER')
        gid=self.social.create_group('家庭会议',['rui','mia'])
        cfg=self.social.get_settings();cfg.update(max_turns=1,daily_tokens=200000);self.social.set_settings(cfg)
        trigger=self.social.post(gid,'@rui 最近怎么样')
        captured=[]
        class Fake:
            config={'model':'fixture'}
            def complete(inner,system,messages,**kwargs):
                captured.append(system);return [{'type':'text','text':'我记得你刚才说的，慢慢来。'}],{},'stop'
        with patch('sunday_blue.modules.social.RoleProvider',return_value=Fake()):self.social.generate(gid,trigger)
        self.assertIn('RUI_PRIVATE_MARKER',captured[0]);self.assertNotIn('RED_PRIVATE_MARKER',captured[0])
        self.assertIn('我记得你刚才',recent_context(self.root,'mia'))
        self.assertEqual(recent_context(self.root,'red'),'')
        self.social.set_memory_support(gid,False)
        trigger=self.social.post(gid,'@rui 再聊一句')
        with patch('sunday_blue.modules.social.RoleProvider',return_value=Fake()):self.social.generate(gid,trigger)
        self.assertNotIn('RUI_PRIVATE_MARKER',captured[-1])
    def test_summary_idempotent_membership_and_budget_gate(self):
        gid=self.social.create_group('家庭会议',['rui','mia']);self.social.post(gid,'讨论共同计划')
        class Fake:
            config={'model':'fixture'}
            def complete(inner,*a,**kw):return [{'type':'text','text':'我们讨论了计划，尚未确认。'}],{},'stop'
        with patch('sunday_blue.modules.social.RoleProvider',return_value=Fake()) as factory:
            first=self.social.summarize(gid);second=self.social.summarize(gid)
        self.assertEqual(first['id'],second['id']);self.assertEqual(factory.call_count,1)
        self.assertIn('尚未确认',recent_context(self.root,'rui'));self.assertEqual(recent_context(self.root,'red'),'')
        cfg=self.social.get_settings();cfg['daily_calls']=1;self.social.set_settings(cfg)
        with self.assertRaises(ValueError):self.social._reserve('rui',gid,'test',256)
    def test_proactive_opt_in_quiet_focus_and_real_events(self):
        gid=self.social.create_group('家庭会议',['rui'],share_activity=True);self.run_focus()
        self.assertIsNone(self.social.proactive_candidate())
        self.social.set_settings(self.social.get_settings()|{'proactive_enabled':True,'group_id':gid,'quiet_start':0,'quiet_end':0})
        self.assertIsNone(self.social.proactive_candidate(True))
        candidate=self.social.proactive_candidate(False);self.assertEqual(candidate[0],gid)
        self.assertIn('学习',self.social.messages(gid)[0]['content'])
        self.assertIsNone(self.social.proactive_candidate(False))
    def test_role_model_override_and_safe_reasoning(self):
        self.config.value['roles']['rui']['model_profile']={'enabled':True,'model':'strong','reasoning':'anthropic_budget','thinking_budget':1024,'max_tokens':4096}
        self.assertEqual(resolve_api(self.config.value,'rui')['model'],'strong')
        self.assertEqual(resolve_api(self.config.value,'mia')['model'],'fixture')
        self.assertEqual(resolve_api(self.config.value,'rui','social')['thinking_budget'],0)
        self.config.value['roles']['rui']['model_profile']['protocol']='openai'
        with self.assertRaises(ValueError):resolve_api(self.config.value,'rui')

    def test_event_plugin_feedback_is_opt_in_and_not_replayed(self):
        import shutil
        from PySide6.QtWidgets import QApplication
        from sunday_blue.modules.hub import ModuleHub
        app=QApplication.instance() or QApplication([])
        shutil.copytree(ROOT/'extensions/plugins/focus-cheer',self.root/'extensions/plugins/focus-cheer')
        self.config.value['roles']['rui']['native_plugins']={'focus-cheer':True}
        self.run_focus()
        hub=ModuleHub(self.config,self.store,start_timer=False);captured=[]
        hub.feedback.connect(lambda role,text:captured.append((role,text)))
        hub._plugin_events();hub._plugin_events()
        self.assertEqual(len(captured),1);self.assertEqual(captured[0][0],'rui')
        self.assertIn('学习 2 分钟',captured[0][1])
        hub.close();hub.deleteLater();app.processEvents()
