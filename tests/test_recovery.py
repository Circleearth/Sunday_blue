import tempfile,time,unittest
from pathlib import Path
from datetime import datetime,timedelta
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from sunday_blue.storage import Config,Store
from sunday_blue.modules.database import ModuleDB
from sunday_blue.modules.hub import ModuleHub
from sunday_blue.modules.recovery import Recovery
APP=QApplication.instance() or QApplication([])
ROOT=Path(__file__).resolve().parents[1]
class RecoveryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'tests',prefix='sunday-test-');self.cfg=Config(self.tmp.name);self.h=ModuleHub(self.cfg,Store(self.cfg.data),start_timer=False);self.db=self.h.db;self.now=time.time();self.r=Recovery(self.db,lambda:self.now)
 def tearDown(self):self.h.close();self.h.deleteLater();APP.processEvents();self.tmp.cleanup()
 def test_end_work_real_summary_idempotent_and_no_coin_cost(self):
  task=self.h.work.create('实际任务');clock=[0];self.h.focus.clock=lambda:clock[0];self.h.focus.start('工作',task_id=task)
  for _ in range(30):clock[0]+=5;self.h.focus.checkpoint()
  self.h.work.update(task,progress=40);self.h.focus.finish();before=self.h.rewards.balances()
  result=self.r.end_work(5);self.assertEqual(result['minutes'],2.5);self.assertEqual(len(result['progress']),1);self.assertEqual(result['completed'],[])
  until=self.r.status()['until'];self.now+=10;self.r.end_work(5);self.assertEqual(self.r.status()['until'],until)
  self.assertTrue(self.r.protected());self.now+=301;self.assertFalse(self.r.status()['active']);self.assertEqual(self.h.rewards.balances(),before)
  self.r.finish('rest');self.assertTrue(self.r.status()['active'])
 def test_mood_missing_records_cooldown_no_delayed_penalty(self):
  self.assertEqual(self.r.decision(known=False),'ignore');self.r.report('sad')
  self.assertEqual(self.r.decision(),'defer');self.assertEqual(self.r.decision(urgent=True),'allow')
  result=self.h.relations.report_setback('rui','实际没有完成');self.assertEqual(result['status'],'deferred')
  self.assertEqual(next(r for r in self.h.relations.list() if r['role_id']=='rui')['affinity'],50)
  self.r.report('calm');self.assertTrue(self.r.negative_allowed('one'));self.assertFalse(self.r.negative_allowed('two'))
 def test_shared_reminder_deferred_urgent_bypasses(self):
  past=(datetime.now().astimezone()-timedelta(seconds=1)).isoformat()
  normal=self.h.planner.add('普通',past,local=False,qq=True);urgent=self.h.planner.add('紧急',past,local=False,qq=True);self.h.planner.set_urgent(urgent,True)
  self.r.end_work()
  with patch.object(self.h.reminder_delivery,'test_send',return_value=True) as send:
   self.h.reminder_delivery.tick();deadline=time.monotonic()+2
   while self.h.reminder_delivery.active and time.monotonic()<deadline:APP.processEvents();time.sleep(.01)
   self.assertEqual(send.call_count,1);self.assertEqual(send.call_args.args[0],'紧急')
  states={r['schedule_id']:r['qq_status'] for r in self.h.planner.history()};self.assertEqual(states[normal],'pending');self.assertEqual(states[urgent],'sent')
 def test_proactive_gate_and_context(self):
  self.r.report('tired');self.assertFalse(self.h.social.can_interrupt());self.assertIn('暂停非紧急',self.r.context())
  self.assertIsNone(self.h.social.proactive_candidate())
 def test_extensions_survive_personality_swap(self):
  from sunday_blue.capabilities import TurnCapabilities
  skill=Path(self.tmp.name)/'extensions/skills/fixture';skill.mkdir(parents=True);(skill/'SKILL.md').write_text('Fixture workflow',encoding='utf-8')
  self.h.duties.set_extensions('organizer',[],['fixture']);self.h.duties.assign('organizer','mia')
  route=TurnCapabilities(self.cfg.root,self.cfg.snapshot(),'mia','你好');self.assertIn('skill:fixture',route.catalog);self.assertNotIn('skill:fixture',route.active)
  route.activate('skill:fixture');self.assertIn('fixture',route.snapshot()['roles']['mia']['skills'])
  self.assertNotIn('skill:fixture',TurnCapabilities(self.cfg.root,self.cfg.snapshot(),'mubu','你好').catalog)
  self.assertEqual(next(s for s in self.h.duties.slots() if s['id']=='organizer')['role_id'],'mia')
