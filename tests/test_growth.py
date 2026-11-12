"""Isolated end-to-end evidence, challenge economy, state and navigation invariants."""
import tempfile,unittest
from pathlib import Path
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from PySide6.QtCore import QCoreApplication,QEvent
from PySide6.QtWidgets import QApplication
from sunday_blue.storage import Config,Store
from sunday_blue.modules.hub import ModuleHub
from sunday_blue.modules.attention import Attention
from sunday_blue.modules.life_state import ZONE
APP=QApplication.instance() or QApplication([])
ROOT=Path(__file__).resolve().parents[1]
class GrowthTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(dir=ROOT/'tests',prefix='sunday-growth-');self.cfg=Config(self.temp.name);self.h=ModuleHub(self.cfg,Store(self.cfg.data),start_timer=False);self.l=self.h.learning;self.c=self.h.contracts
  self.course=self.l.add('subject','数学');self.chapter=self.l.add('chapter','函数',self.course);self.unit=self.l.add('unit','导数',self.chapter)
 def tearDown(self):
  self.h.close();self.h.deleteLater();APP.processEvents();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.temp.cleanup()
 def deadline(self):return (datetime.now(timezone.utc)+timedelta(days=2)).isoformat()
 def test_evidence_requires_practice_review_and_resolved_errors(self):
  self.l.assess(self.unit,100);self.assertFalse(self.l.evidence(self.unit)['mastered']);self.assertEqual(self.l.evidence(self.unit)['score'],0)
  self.l.practice(self.unit,10,8,'链式法则易错',request_id='batch1');self.l.review(self.unit,True);self.assertFalse(self.l.evidence(self.unit)['mastered'])
  self.l.practice(self.unit,2,2,'已能解释',request_id='retry',error_id='batch1');self.assertTrue(self.l.evidence(self.unit)['mastered'])
  self.l.practice(self.unit,2,2,'已能解释',request_id='retry',error_id='batch1');self.assertEqual(self.l.evidence(self.unit)['total'],12)
  with self.assertRaises(ValueError):self.l.practice(self.unit,2,1,'更换内容',request_id='retry')
  with self.assertRaises(ValueError):self.l.review(self.unit,True)
  self.assertGreater(self.l.evidence(self.unit)['due'],datetime.now(ZONE).date().isoformat())
  with self.assertRaises(ValueError):self.l.add('unit','错误层级',self.course)
 def test_focus_link_and_existing_reward_once(self):
  clock=[0];self.h.focus.clock=lambda:clock[0];self.h.start_focus('学习','导数','loluns');run=self.h.focus.status()['id'];self.l.bind(run,self.unit)
  other=self.l.add('unit','积分',self.chapter)
  with self.assertRaises(ValueError):self.l.bind(run,other)
  for _ in range(25):clock[0]+=5;self.h.focus.checkpoint()
  result=self.h.focus.finish();balance=self.h.rewards.balances();self.assertAlmostEqual(self.l.evidence(self.unit)['minutes'],125/60)
  self.l.summary();self.l.evidence(self.unit);self.assertEqual(balance,self.h.rewards.balances())
 def test_contract_evidence_baseline_and_idempotent_settlement(self):
  self.l.practice(self.unit,10,10,request_id='before')
  rid=self.c.sign('练习挑战','correct',3,self.deadline());self.c.tick();self.assertEqual(self.c.rows()[0]['progress'],0)
  self.l.practice(self.unit,3,3,request_id='after');before=self.h.rewards.balances();self.c.tick();points=self.c.balance();self.c.tick();self.assertEqual(points,110);self.assertEqual(points,self.c.balance());self.assertEqual(before,self.h.rewards.balances());self.assertEqual(self.c.rows()[0]['status'],'success')
 def test_contract_expiry_requires_review_caps_and_no_real_money(self):
  self.c.configure(50,60,30);ids=[self.c.sign('测试'+str(i),'manual',10,self.deadline(),1,3) for i in range(3)];before=self.h.rewards.balances()
  self.c.tick(datetime.now(timezone.utc)+timedelta(days=3));self.assertTrue(all(r['status']=='review' for r in self.c.rows()));self.assertEqual(self.c.balance(),100)
  for rid in ids:self.c.resolve(rid,True);self.c.resolve(rid,True)
  self.assertEqual(self.c.balance(),40);self.assertEqual(before,self.h.rewards.balances())
 def test_manual_contract_duplicate_and_immutable_rules(self):
  rid=self.c.sign('读书','manual',1,self.deadline(),2,1);self.c.configure(0,0,0);self.c.log(rid,1,'实际完成第一章',request_id='one');self.c.log(rid,1,'实际完成第一章',request_id='one');self.assertEqual(self.c.balance(),120)
  with self.assertRaises(ValueError):self.c.log(rid,1,'更换内容',request_id='one')
 def test_reminder_outbox_is_stable_and_channels(self):
  rid=self.c.sign('学习','correct',10,self.deadline());now=datetime.now(ZONE).replace(hour=19);self.c.tick(now);self.c.tick(now)
  with self.h.db.connect() as db:
   notices=list(db.execute("SELECT * FROM reminder_occurrences WHERE id LIKE 'contract-%'"));self.assertEqual(len(notices),2);self.assertTrue(all(r['qq_status']=='pending' and r['local_status']=='pending' for r in notices))
 def test_night_use_rest_and_offline_do_not_confuse_physical(self):
  clock=[0];a=Attention(self.h.db,clock=lambda:clock[0]);night=datetime.now(ZONE).replace(hour=23)
  with self.h.db.connect() as db:db.execute('UPDATE attention_state SET eye=40,focus=60')
  physical=self.h.life.energy()['physical'];clock[0]=10;a.tick(active=True,now=night);self.assertGreater(a.status()['eye'],40)
  previous=a.status();clock[0]=20;a.tick(active=False,now=night+timedelta(seconds=10));self.assertLess(a.status()['eye'],previous['eye']);self.assertGreater(a.status()['focus'],previous['focus']);self.assertEqual(self.h.life.energy()['physical'],physical)
  previous=a.status();clock[0]=1000;a.tick(active=True,now=night+timedelta(minutes=20));self.assertEqual(a.status()['eye'],previous['eye'])
  reopened=Attention(self.h.db,clock=lambda:2000);reopened.tick(active=False,now=night);self.assertEqual(reopened.status()['eye'],previous['eye'])
 def test_thresholds_escalate_once_and_rest_ignores_keyboard(self):
  clock=[0];a=Attention(self.h.db,clock=lambda:clock[0]);a.configure({'mode':'screen','eye_rate':2});now=datetime.now(ZONE)
  with self.h.db.connect() as db:db.execute('UPDATE attention_state SET eye=59.9,focus=50')
  clock[0]=10;a.tick(active=True,now=now);self.assertEqual(a.new_alert,1)
  with self.h.db.connect() as db:db.execute('UPDATE attention_state SET eye=79.9')
  clock[0]=20;a.tick(active=True,now=now+timedelta(seconds=10));self.assertEqual(a.new_alert,2)
  clock[0]=30;a.tick(active=True,now=now+timedelta(seconds=20));self.assertEqual(a.new_alert,0)
  with self.h.db.connect() as db:
   rows=list(db.execute("SELECT * FROM reminder_occurrences WHERE id LIKE 'attention:%'"));self.assertEqual(len(rows),2);self.assertEqual([r['qq_status'] for r in rows],['off','pending'])
  a.configure({'mode':'rest'});before=a.status()['eye'];clock[0]=40;a.tick(active=True,now=now+timedelta(seconds=30));self.assertGreater(a.status()['eye'],before)
 def test_sleep_report_applies_once_and_does_not_change_physical_directly(self):
  a=self.h.attention;day=(datetime.now(ZONE)-timedelta(days=1)).date().isoformat()
  with self.h.db.connect() as db:db.execute('UPDATE attention_state SET eye=80,focus=20')
  before=self.h.life.energy()['physical'];a.sleep(day,8);first=a.status();a.sleep(day,10);self.assertEqual(a.status()['eye'],first['eye']);self.assertEqual(self.h.life.energy()['physical'],before)
  self.assertLess(first['eye'],80);self.assertGreater(first['focus'],20)
 def test_parameters_and_navigation_aliases(self):
  with self.assertRaises(ValueError):self.h.attention.configure({'high_threshold':50,'light_threshold':60})
  with self.assertRaises(ValueError):self.c.configure(51,60,10)
  self.h.attention.configure({'night_end':'8:30'});self.assertEqual(self.h.attention.options()['night_end'],'08:30')
  from sunday_blue.ui import MainWindow
  from sunday_blue.modules.workspace import install_workspace
  self.cfg.value['main_page']='reminders';w=MainWindow(self.cfg);hub=install_workspace(w);hub.timer.stop();hub.focus_timer.stop()
  try:
   self.assertEqual(w.page_stack.count(),9);self.assertEqual(w.page_stack.currentWidget().tabs.currentWidget().__class__.__name__,'RemindersPage')
   hub.navigate.emit('checkins');self.assertEqual(w.page_stack.currentWidget().tabs.currentWidget().__class__.__name__,'CheckinsPage')
  finally:hub.close();w.tray.exiting=True;w.close();w.tray.icon.hide();w.deleteLater();APP.processEvents()

 def test_sleep_from_report_and_rest_overlap_are_not_double_counted(self):
  day=(datetime.now(ZONE)-timedelta(days=1)).date().isoformat()
  with self.h.db.connect() as db:
   db.execute('UPDATE attention_state SET eye=90,focus=10')
   db.execute('INSERT INTO attention_days(day,rest_seconds) VALUES(?,?)',(day,3600*4))
  self.h.life.save_daily(day,sleep_start='23:00',sleep_end='07:00')
  a=self.h.attention.status();self.assertEqual(a['eye'],62);self.assertEqual(a['focus'],34)
  self.h.life.save_daily(day,sleep_start='22:00',sleep_end='07:00');self.assertEqual(self.h.attention.status()['eye'],62)
 def test_paper_mode_and_sleep_gap_do_not_recover_eyes(self):
  clock=[0];a=Attention(self.h.db,clock=lambda:clock[0]);a.configure({'mode':'paper'})
  clock[0]=10;a.tick(active=False,now=datetime.now(ZONE));self.assertGreater(a.status()['eye'],0);self.assertLess(a.status()['focus'],100)
 def test_learning_loop_preserves_binding(self):
  clock=[0];self.h.focus.clock=lambda:clock[0];self.h.start_focus('学习','导数','loluns',duration=125);self.l.bind(self.h.focus.status()['id'],self.unit)
  self.h.db.set('focus_loop',self.h.db.get('focus_loop')|{'learning_unit':self.unit,'enabled':True,'remaining':2})
  for _ in range(25):clock[0]+=5;self.h.focus.checkpoint()
  self.assertNotEqual(self.h.focus.status()['phase'],'focus')
  duration=self.h.focus.status()['duration']
  for _ in range(int(duration/5)):clock[0]+=5;self.h.focus.checkpoint()
  self.assertEqual(self.h.focus.status()['phase'],'focus')
  with self.h.db.connect() as db:self.assertEqual(db.execute('SELECT unit FROM learning_focus_links WHERE run_id=?',(self.h.focus.status()['id'],)).fetchone()[0],self.unit)
