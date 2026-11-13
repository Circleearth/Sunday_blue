"""Regression tests for personal control, daily exercise challenges and nested work."""
import tempfile,unittest
from pathlib import Path
from datetime import datetime,timedelta
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication,QEvent
from sunday_blue.storage import Config,Store
from sunday_blue.modules.hub import ModuleHub
from sunday_blue.modules.attention import Attention
from sunday_blue.modules.life_state import ZONE
APP=QApplication.instance() or QApplication([])
ROOT=Path(__file__).resolve().parents[1]
class FollowupTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'tests',prefix='sunday-followup-');cfg=Config(self.tmp.name);self.h=ModuleHub(cfg,Store(cfg.data),start_timer=False);self.h.focus.set_options({'llm_feedback':False});self.widgets=[]
 def tearDown(self):
  self.h.close()
  for w in self.widgets:w.close();w.deleteLater()
  self.h.deleteLater();APP.processEvents();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.tmp.cleanup()
 def test_private_thresholds_and_yesterday_form_no_toggle(self):
  p=self.h.private_wellbeing;day=(datetime.now(ZONE)-timedelta(days=1)).date().isoformat()
  for count,level in [(0,'green'),(2,'green'),(3,'yellow'),(5,'orange'),(7,'orange'),(8,'red'),(12,'red')]:
   p.save(day,count,count*5);state=p.status();self.assertEqual(state['level'],level);self.assertEqual(state['ratio'],count/5)
  from sunday_blue.module_views.life import LifePage
  page=LifePage(self.h);self.widgets.append(page);self.assertFalse(hasattr(page,'private_enabled'));self.assertFalse(hasattr(page,'private_limit'));self.assertEqual(page.selected_day(),day);self.assertIn('240%',page.private_recovery.text())
  page.bed.load('23:00');page.wake.load('07:00');page.private_count.setValue(1);page.private_minutes.setValue(10)
  with patch.object(self.h.reports,'daily',return_value=None):page.save_daily()
  self.assertEqual(p.get(day)['count'],1)
 def test_nested_aggregation_due_notes_archive_and_guards(self):
  w=self.h.work;r=w.create('project',due='2026-12-31',notes='保留资料链接');a=w.create('chapter',r);b=w.create('other',r);x=w.create('nested',a);y=w.create('second',a)
  self.assertEqual(w.task(x)['due'],'2026-12-31');w.update(r,due='2027-01-01');self.assertEqual(w.task(x)['due'],'2027-01-01')
  w.update(x,status='done');self.assertEqual(w.task(a)['progress'],50);self.assertEqual(w.task(r)['progress'],25);self.assertEqual(w.task(r)['notes'],'保留资料链接')
  w.update(x,notes='不同备注');self.assertEqual(w.task(x)['notes'],'不同备注')
  with self.h.db.connect() as c:
   c.execute('INSERT INTO focus_task_links VALUES(?,?,?,?)',('historic',y,'nested',0));c.execute('INSERT INTO activity_records VALUES(?,?,?,?,?,?,?,?)',('historic','工作','nested','rui',600,'2020-01-01','then','then'))
  self.assertEqual(w.task(r)['actual_seconds'],600);self.assertEqual(w.task(a)['actual_seconds'],600)
  w.update(r,status='paused')
  with self.h.db.connect() as c:
   with self.assertRaises(ValueError):w.validate_binding(c,y)
  self.assertFalse(w.suggest());w.archive(r);self.assertEqual(w.tasks(),[]);w.archive(r,False);self.assertEqual(len(w.tasks()),5)
 def test_done_child_sort_and_ancestor_reopening(self):
  w=self.h.work;r=w.create('root');c=w.create('child',r);a=w.create('a',c);b=w.create('b',c);w.update(b,status='done')
  children=[x for x in w.tasks() if x['parent_id']==c];self.assertEqual(children[0]['id'],b)
  w.update(a,status='done');w.update(c,status='done');w.update(r,status='done');w.update(a,progress=40)
  self.assertEqual(w.task(r)['progress'],70);self.assertEqual(w.task(r)['status'],'doing')
  with self.h.db.connect() as db:self.assertEqual(db.execute('SELECT status FROM work_tasks WHERE id=?',(r,)).fetchone()[0],'doing')
 def test_work_tree_completed_nested_widgets_and_missing_estimate_weights(self):
  from sunday_blue.module_views.life_work import WorkPage
  w=self.h.work;r=w.create('project');a=w.create('done',r,estimate_minutes=30);b=w.create('unknown',r);w.update(a,status='done');self.assertEqual(w.task(r)['progress'],50)
  page=WorkPage(self.h);self.widgets.append(page);page.show();APP.processEvents();root=page.tree.topLevelItem(0);self.assertEqual(root.child(0).text(0),'done');self.assertIsNotNone(page.tree.itemWidget(root.child(0),2))
 def test_capacity_loss_rest_half_and_restart(self):
  clock=[0];a=Attention(self.h.db,lambda:clock[0]);now=datetime.now(ZONE);a.daily_boundary(now);a.configure({'mode':'screen','focus_rate':1})
  with self.h.db.connect() as c:c.execute('UPDATE attention_state SET focus=100')
  for _ in range(4):clock[0]+=30;a.tick(active=True,now=now)
  self.assertAlmostEqual(a.status()['focus'],98);self.assertAlmostEqual(a.status()['focus_cap'],99)
  a.configure({'mode':'rest'})
  for _ in range(4):clock[0]+=30;a.tick(active=False,now=now)
  self.assertAlmostEqual(a.status()['focus'],98.5);self.assertAlmostEqual(self.h.life.energy()['focus_value'],98.5);self.assertAlmostEqual(self.h.life.energy()['focus_cap'],99)
  reopened=Attention(self.h.db);self.assertEqual(reopened.options()['rest_focus'],.25);self.assertEqual(reopened.status()['focus_cap'],99)
  for _ in range(20):clock[0]+=30;a.tick(active=False,now=now)
  self.assertAlmostEqual(a.status()['focus'],99)
  tomorrow=(now+timedelta(days=1)).date().isoformat();self.assertEqual(self.h.life.state.caps(tomorrow)['focus_cap'],100)
 def test_exercise_daily_not_total_and_separate_ledger_report(self):
  c=self.h.contracts;now=datetime.now(ZONE);yesterday=(now-timedelta(days=1)).date().isoformat();today=now.date().isoformat()
  rid=c.sign('每天运动','exercise_daily',30,(now+timedelta(days=1)).isoformat())
  with self.h.db.connect() as db:db.execute('UPDATE challenge_contracts SET signed=?,deadline=? WHERE id=?',((now-timedelta(days=1)).replace(hour=0).isoformat(),now.replace(hour=23,minute=59,second=59).isoformat(),rid))
  self.h.life.exercise('快走',90,'light',day=yesterday);c.tick();row=next(r for r in c.rows() if r['id']==rid);self.assertEqual(row['status'],'active');self.assertEqual(row['progress'],0)
  self.h.life.exercise('散步',30,'light',day=today);c.tick();self.assertEqual(c.balance('exercise'),110);self.assertEqual(c.balance('study'),100)
  c.tick();self.assertEqual(c.balance('exercise'),110)
  snapshot=self.h.reports.snapshot(today,(now+timedelta(days=1)).date().isoformat());self.assertEqual(snapshot['contracts'][0]['amount'],10);self.assertEqual(snapshot['contracts'][0]['metric'],'exercise_daily')
  with self.h.db.connect() as db:
   self.assertIsNotNone(db.execute('SELECT * FROM challenge_settlement_evidence WHERE contract_id=?',(rid,)).fetchone());db.execute('UPDATE exercise_records SET minutes=1')
  frozen=next(r for r in c.rows() if r['id']==rid);self.assertEqual(frozen['progress'],30);self.assertEqual([r['minutes'] for r in frozen['exercise_days']],[90,30])
 def test_exercise_penalty_cannot_spend_study_points(self):
  c=self.h.contracts;rid=c.sign('运动','exercise_daily',30,(datetime.now(ZONE)+timedelta(days=2)).isoformat());c.resolve(rid,True)
  self.assertEqual(c.balance('exercise'),90);self.assertEqual(c.balance(),100);c.resolve(rid,True);self.assertEqual(c.balance('exercise'),90)
 def test_trace_reports_fallback_reason_without_prompts(self):
  self.h.start_focus('学习');self.h.focus.pause()
  with self.h.db.connect() as c:
   trace=list(c.execute('SELECT * FROM focus_feedback_trace'));self.assertTrue(trace);self.assertEqual(trace[-1]['reason'],'disabled');self.assertNotIn('content',trace[-1].keys())
