"""Regression coverage for numeric input, daily state, private data and reports."""
import tempfile,time,unittest
from pathlib import Path
from datetime import date,datetime,timedelta
from unittest.mock import patch
from PySide6.QtWidgets import QApplication,QWidget,QVBoxLayout,QLineEdit
from PySide6.QtCore import Qt,QCoreApplication,QEvent
from PySide6.QtTest import QTest
from sunday_blue.storage import Config,Store
from sunday_blue.modules.hub import ModuleHub
from sunday_blue.modules.attention import Attention
from sunday_blue.modules.life_state import ZONE
from sunday_blue.modules.reports import period_window,FALLBACK
from sunday_blue.numeric_inputs import NumberSpin,DecimalSpin
APP=QApplication.instance() or QApplication([])
ROOT=Path(__file__).resolve().parents[1]
class DailyExperienceTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(dir=ROOT/'tests',prefix='sunday-daily-');self.cfg=Config(self.temp.name);self.h=ModuleHub(self.cfg,Store(self.cfg.data),start_timer=False);self.widgets=[]
  self.h.focus.set_options({'llm_feedback':False})
 def tearDown(self):
  self.h.close()
  for w in self.widgets:w.close();w.deleteLater()
  self.h.deleteLater();APP.processEvents();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.temp.cleanup()
 def wait(self,predicate):
  deadline=time.monotonic()+3
  while not predicate() and time.monotonic()<deadline:APP.processEvents();time.sleep(.01)
  self.assertTrue(predicate())
 def test_numeric_units_are_not_editable_and_first_click_replaces_value(self):
  w=QWidget();self.widgets.append(w);layout=QVBoxLayout(w);other=QLineEdit();spin=NumberSpin();spin.setRange(0,240);spin.setSuffix(' 分钟');spin.setValue(15);layout.addWidget(other);layout.addWidget(spin);w.show();other.setFocus();APP.processEvents()
  self.assertEqual(spin.lineEdit().text(),'15');self.assertEqual(spin._unit.text(),'分钟')
  QTest.mouseClick(spin.lineEdit(),Qt.MouseButton.LeftButton);APP.processEvents();QTest.keyClicks(spin.lineEdit(),'25');spin.interpretText();self.assertEqual(spin.value(),25)
  QTest.keyClick(spin,Qt.Key.Key_Up);self.assertEqual(spin.value(),26)
  dec=DecimalSpin();dec.setPrefix('元');dec.setValue(2.5);self.assertNotIn('元',dec.lineEdit().text());self.assertEqual(dec.value(),2.5)
 def test_morning_tiers_and_restart_do_not_compound(self):
  for i,(value,expected) in enumerate([(19,1.9),(20,4),(49,9.8),(50,15),(79,23.7),(80,40),(100,50)]):
   now=datetime(2030,1,1+i,9,tzinfo=ZONE)
   with self.h.db.connect() as c:
    c.execute('UPDATE attention_state SET eye=?',(value,));c.execute('INSERT OR REPLACE INTO attention_days(day,eye) VALUES(?,?)',((now.date()-timedelta(days=1)).isoformat(),value))
   self.h.attention.daily_boundary(now);self.assertAlmostEqual(self.h.attention.status()['eye'],expected)
   Attention(self.h.db).daily_boundary(now+timedelta(hours=2));self.assertAlmostEqual(self.h.attention.status()['eye'],expected)
 def test_daytime_accumulation_and_focus_bonus_rest_night_notice(self):
  clock=[0];a=Attention(self.h.db,lambda:clock[0]);now=datetime(2030,2,1,12,tzinfo=ZONE);a.daily_boundary(now)
  clock[0]=10;a.tick(active=False,now=now);baseline=a.status()['eye'];self.assertGreater(baseline,0)
  clock[0]=20;a.tick(focus={'state':'running','phase':'focus','category':'学习'},active=False,now=now);self.assertGreater(a.status()['eye']-baseline,baseline)
  a.configure({'mode':'rest'});before=a.status();clock[0]=30;a.tick(active=False,now=now);self.assertLess(a.status()['eye'],before['eye']);self.assertGreater(a.status()['focus'],before['focus'])
  with self.h.db.connect() as c:c.execute('UPDATE attention_state SET eye=65')
  a.daily_boundary(now.replace(hour=22));a.daily_boundary(now.replace(hour=23))
  with self.h.db.connect() as c:
   rows=list(c.execute("SELECT * FROM reminder_occurrences WHERE id='attention-night:2030-02-01'"));self.assertEqual(len(rows),1);self.assertEqual(rows[0]['qq_status'],'pending')
 def test_phase_switch_and_life_clock_restore_auto(self):
  self.h.start_focus('学习',phase='short_break',duration=60);self.assertEqual(self.h.attention.options()['mode'],'rest');self.h.focus.finish()
  self.h.start_focus('工作');self.assertEqual(self.h.attention.options()['mode'],'auto');self.h.focus.finish()
  self.h.attention.configure({'mode':'rest'});self.h.life_timer.start('阅读');self.assertEqual(self.h.attention.options()['mode'],'auto')
  self.h.life_timer.pause();self.h.attention.configure({'mode':'rest'});self.h.life_timer.resume();self.assertEqual(self.h.attention.options()['mode'],'auto')
 def test_private_revision_validation_and_report_exclusion(self):
  p=self.h.private_wellbeing;p.save('2020-01-01',2,25);p.save('2020-01-01',2,25);p.save('2020-01-01',3,30,True)
  with self.h.db.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM private_wellbeing_revisions').fetchone()[0],1)
  self.assertEqual(p.status('2020-01-01')['level'],'red')
  with self.assertRaises(ValueError):p.save('2020-01-02',0,10)
  rid=self.h.reports.prepare('day','2020-01-01','2020-01-02');row=next(r for r in self.h.reports.rows() if r['id']==rid)
  self.assertNotIn('25',row['body']);self.assertNotIn('30 分钟',row['body']);self.assertEqual(p.get('2020-01-01')['count'],3)
 def test_report_backfill_finishes_stored_time_and_never_awards_twice(self):
  self.h.start_focus('学习','复习');rid=self.h.focus.status()['id']
  with self.h.db.connect() as c:c.execute("UPDATE focus_runs SET state='paused',elapsed=600,started='2020-01-01T10:00:00+08:00' WHERE id=?",(rid,))
  with patch.object(self.h.reports,'pump'):
   report=self.h.reports.daily('2020-01-01');balance=self.h.rewards.balances();self.h.reports.daily('2020-01-01')
  self.assertEqual(balance,self.h.rewards.balances());self.assertEqual(balance['coins'],13);self.assertEqual(self.h.focus.records()[0]['day'],'2020-01-01')
  self.assertEqual(self.h.focus.status()['state'],'idle');row=next(r for r in self.h.reports.rows() if r['id']==report);self.assertIn('学习 10.0 分钟',row['body']);self.assertIn('专注金币 13',row['body'])
 def test_report_rewards_follow_record_dates_not_payment_dates(self):
  self.h.life.save_daily('2020-01-01',meal='正常三餐',sleep_hours=8)
  with self.h.db.connect() as c:c.execute("INSERT INTO coin_ledger VALUES('unrelated',100,'manual','now')")
  report=self.h.reports.snapshot('2020-01-01','2020-01-02');self.assertEqual(report['total_activity_coins'],1);self.assertEqual(report['life_coins'],1)
  self.assertEqual(self.h.reports.snapshot('2020-01-02','2020-01-03')['total_activity_coins'],0)
 def test_period_boundaries_include_last_report_day_exclude_current(self):
  self.assertEqual(period_window('week',date(2026,11,15)),(date(2026,11,8),date(2026,11,15)))
  self.assertEqual(period_window('month',date(2026,11,30)),(date(2026,10,31),date(2026,11,30)))
  self.assertEqual(period_window('year',date(2026,12,31)),(date(2025,12,31),date(2026,12,31)))
  self.assertEqual(period_window('month',date(2026,11,13)),(date(2026,9,30),date(2026,10,31)))
 def test_report_api_success_fallback_and_snapshot_idempotency(self):
  self.cfg.value['api']['model']='fixture';r=self.h.reports;rid=r.prepare('day','2020-01-01','2020-01-02')
  with patch('sunday_blue.modules.reports.RoleProvider.complete',return_value=([{'type':'text','text':'今天的投入已经记下，慢慢恢复。'}],{},'end_turn')) as api:
   r.pump();self.wait(lambda:not r.busy);self.assertEqual(api.call_count,1);r.prepare('day','2020-01-01','2020-01-02');r.pump();self.assertEqual(api.call_count,1)
  self.assertEqual(r.rows()[0]['state'],'done')
  r.prepare('day','2020-01-02','2020-01-03')
  with patch('sunday_blue.modules.reports.RoleProvider.complete',side_effect=ConnectionError('fixture offline')):
   r.pump();self.wait(lambda:not r.busy)
  self.assertEqual(r.rows()[0]['comment'],FALLBACK);self.assertEqual(r.rows()[0]['state'],'fallback')
 def test_focus_daily_context_category_and_visible_source(self):
  self.cfg.value['api']['model']='fixture';self.h.focus.set_options({'llm_feedback':True});d=self.h.focus_dialogue
  today=datetime.now(ZONE).date().isoformat();self.h.db.set('focus_words:rui:'+today,{'at':datetime.now(ZONE).timestamp()-180,'history':[{'role':'user','content':'上一轮复习'},{'role':'assistant','content':'刚才已经理清了一个难点。'}]})
  with patch('sunday_blue.modules.focus_dialogue.RoleProvider.complete',return_value=([{'type':'text','text':'先把这道题的思路慢慢走通。'}],{},'end_turn')) as api:
   self.h.start_focus('学习','导数');self.wait(lambda:not d.busy)
  system,messages=api.call_args.args;self.assertIn('活动类别：学习',system);self.assertIn('不重复寒暄',system);self.assertIn('不要提问',system);self.assertTrue(any('刚才' in m['content'] for m in messages));self.assertEqual(self.h.db.get('focus_dialogue_status')['source'],'llm')
  self.h.focus.pause();self.assertEqual(self.h.db.get('focus_dialogue_status')['source'],'fallback');self.assertIn('暂停',self.h.db.get('focus_words:rui:'+today)['history'][-1]['content'])
 def test_report_dialog_and_minute_refresh(self):
  from sunday_blue.module_views.life import LifePage
  page=LifePage(self.h);self.widgets.append(page);page.resize(1100,760);page.show();APP.processEvents();self.assertEqual(page.state_refresh.interval(),60000)
  rid=self.h.reports.prepare('day','2020-01-01','2020-01-02');page.reports_page.show_report(rid);APP.processEvents();self.assertTrue(page.reports_page.dialog.isVisible())
  page.reports_page.items.setCurrentRow(0);page.reports_page.copy_selected();self.assertIn('结算',APP.clipboard().text());page.reports_page.dialog.close()
