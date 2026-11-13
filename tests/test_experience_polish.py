import tempfile,unittest
from pathlib import Path
from datetime import datetime,timedelta
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication,QEvent,QSize,QDate,Qt,QPoint
from PySide6.QtTest import QTest
from PySide6.QtGui import QPixmap,QColor
from sunday_blue.storage import Config,Store
from sunday_blue.modules.hub import ModuleHub
from sunday_blue.modules.attention import Attention
from sunday_blue.modules.life_state import ZONE
from sunday_blue.image_layouts import save_selection,selection,framed,EditableImage,Preview
APP=QApplication.instance() or QApplication([])
ROOT=Path(__file__).resolve().parents[1]
class PolishTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'tests',prefix='sunday-polish-');self.cfg=Config(self.tmp.name);self.h=ModuleHub(self.cfg,Store(self.cfg.data),start_timer=False);self.h.focus.set_options({'llm_feedback':False});self.widgets=[]
 def tearDown(self):
  self.h.close()
  for w in self.widgets:w.close();w.deleteLater()
  self.h.deleteLater();APP.processEvents();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.tmp.cleanup()
 def test_work_summary_includes_created_and_today_completed_ancestors(self):
  p=self.h.work.create('项目');c=self.h.work.create('完成子项',p);self.h.work.update(c,status='done');r=self.h.end_work();self.assertIn('项目',r['created']);self.assertIn('完成子项',r['completed']);self.assertIn('项目',r['completed']);key=self.h.recovery.status()['settlement_key'];self.h.end_work();self.assertEqual(key,self.h.recovery.status()['settlement_key'])
 def test_rest_cycle_reaches_floor_daily_limits_reset(self):
  clock=[0];a=Attention(self.h.db,lambda:clock[0]);now=datetime.now(ZONE).replace(hour=12);a.daily_boundary(now)
  def advance(minutes,working):
   for _ in range(minutes*2):
    clock[0]+=30;a.tick({'state':'running','phase':'focus','category':'工作'} if working else {},active=working,now=now)
  for _ in range(4):
   a.configure({'mode':'screen'});advance(25,True);a.configure({'mode':'rest'});advance(5,False)
  advance(30,False);self.assertAlmostEqual(a.status()['eye_floor'],2);self.assertAlmostEqual(a.status()['eye'],2);self.assertLess(a.status()['focus_cap'],100)
  self.assertEqual(Attention(self.h.db).options()['rest_eye'],3.5)
  tomorrow=now+timedelta(days=1);a.daily_boundary(tomorrow);clock[0]+=30;a.tick(active=False,now=tomorrow);self.assertLess(a.status()['eye'],2)
  self.assertEqual(self.h.life.state.caps(tomorrow.date().isoformat())['focus_cap'],100)
 def test_external_image_transform_persistence_and_missing_fallback(self):
  path=self.cfg.root/'picture.png';pix=QPixmap(40,20);pix.fill(QColor('red'));pix.save(str(path));before=path.read_bytes()
  image=EditableImage(self.cfg.root,'test',self.cfg.root/'missing.png');self.widgets.append(image)
  save_selection(self.cfg.root,'test',{'path':str(path),'zoom':2,'x':.25,'y':0});self.assertFalse(image.pix.isNull());self.assertEqual(selection(self.cfg.root,'test')['zoom'],2)
  preview=Preview(pix,{},1);self.widgets.append(preview);preview.resize(300,300);preview.show();APP.processEvents();QTest.mousePress(preview,Qt.MouseButton.LeftButton,pos=QPoint(100,100));QTest.mouseMove(preview,QPoint(130,120));QTest.mouseRelease(preview,Qt.MouseButton.LeftButton,pos=QPoint(130,120));self.assertGreater(preview.cfg.get('x',0),0)
  out=framed(self.cfg.root,'test',self.cfg.root/'missing.png',QSize(60,60));self.assertEqual(out.size(),QSize(60,60));self.assertEqual(path.read_bytes(),before)
  save_selection(self.cfg.root,'other',{'zoom':1});self.assertEqual(selection(self.cfg.root,'test')['path'],str(path));path.unlink();image.reload();self.assertTrue(image.pix.isNull())
 def test_reported_form_locks_then_edit_or_nearest_missing(self):
  from sunday_blue.module_views.life import LifePage
  yesterday=QDate.currentDate().addDays(-1);prior=yesterday.addDays(-1)
  self.h.life.save_daily(yesterday.toString('yyyy-MM-dd'),sleep_start='23:00',sleep_end='07:00')
  page=LifePage(self.h);self.widgets.append(page);page.show();APP.processEvents();self.assertFalse(page.saved_panel.isHidden());self.assertTrue(page.submit_daily.isHidden())
  page.set_daily_saved(False);self.assertFalse(page.submit_daily.isHidden());page.open_missing_daily();self.assertEqual(page.selected_day(),prior.toString('yyyy-MM-dd'))
  page.bed.load('23:00');page.wake.load('07:00')
  with patch.object(self.h.reports,'daily',return_value=None) as report:page.save_daily();report.assert_called_once_with(prior.toString('yyyy-MM-dd'))
  self.assertFalse(page.saved_panel.isHidden())
 def test_report_page_does_not_generate_from_view_button(self):
  from sunday_blue.module_views.reports import ReportsPage
  page=ReportsPage(self.h);self.widgets.append(page)
  with patch.object(self.h.reports,'daily') as generate,patch('PySide6.QtWidgets.QMessageBox.information'):
   page.generate();generate.assert_not_called()
