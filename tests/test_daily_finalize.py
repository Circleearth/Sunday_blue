import tempfile,unittest
from pathlib import Path
from datetime import date,timedelta
from unittest.mock import patch
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtCore import QDate,QCoreApplication,QEvent
from sunday_blue.storage import Config,Store
from sunday_blue.modules.hub import ModuleHub
from sunday_blue.modules.sleep_quality import score_sleep
from sunday_blue.module_views.life import LifePage
APP=QApplication.instance() or QApplication([])
class FinalizeTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).parent);cfg=Config(self.temp.name);self.h=ModuleHub(cfg,Store(cfg.data),start_timer=False);self.widgets=[];self.day=(date.today()-timedelta(days=1)).isoformat()
 def tearDown(self):
  self.h.close()
  for w in self.widgets:w.close();w.deleteLater()
  self.h.deleteLater();APP.processEvents();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.temp.cleanup()
 def submit(self,day=None,private=(0,0,False,False)):
  return self.h.life.finalize_daily(day or self.day,private,sleep_start='23:00',sleep_end='07:00')
 def test_score_monotonic_and_midnight(self):
  self.assertEqual(score_sleep('23:00','07:00')['quality'],1)
  self.assertLess(score_sleep('02:00','10:00')['quality'],1)
  self.assertLess(score_sleep('23:00','04:00')['quality'],1)
  self.assertLess(score_sleep('23:00','13:00')['quality'],1)
 def test_atomic_lock_recovery_and_no_double_credit(self):
  with self.h.db.connect() as c:c.execute('UPDATE attention_state SET focus=10 WHERE id=1')
  with self.assertRaises(ValueError):self.submit(private=(0,20,False,False))
  self.assertFalse(self.h.life.daily(self.day));self.assertEqual(self.h.attention.status()['focus'],10)
  self.submit();value=self.h.attention.status()['focus'];self.assertGreater(value,10)
  with self.assertRaises(ValueError):self.submit()
  with self.assertRaises(ValueError):self.h.life.save_daily(self.day,meal='change')
  with self.assertRaises(ValueError):self.h.private_wellbeing.save(self.day,2,20)
  self.assertEqual(value,self.h.attention.status()['focus'])
  self.assertGreater(self.h.life.energy()['physical'],90)
 def test_backfill_does_not_restore_today(self):
  with self.h.db.connect() as c:c.execute('UPDATE attention_state SET focus=10 WHERE id=1')
  self.submit((date.today()-timedelta(days=5)).isoformat());self.assertEqual(self.h.attention.status()['focus'],10)
 def test_midnight_date_sync_and_cancel(self):
  p=LifePage(self.h);self.widgets.append(p);p.report_today=QDate.currentDate().addDays(-1);p.day.setDate(QDate.currentDate().addDays(-2));p.sync_report_date();self.assertEqual(p.day.date(),QDate.currentDate());self.assertEqual(p.selected_day(),self.day)
  p.bed.load('23:00');p.wake.load('07:00')
  with patch('PySide6.QtWidgets.QMessageBox.question',return_value=QMessageBox.StandardButton.No):p.save_daily()
  self.assertFalse(self.h.life.daily(self.day))
