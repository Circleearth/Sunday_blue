"""Isolated UI checks for the life cockpit, relationship entry and screen bounds."""
import tempfile,unittest
from pathlib import Path
from datetime import date,timedelta
from PySide6.QtCore import QRect,QPointF,QCoreApplication,QEvent,Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from sunday_blue.storage import Config,Store
from sunday_blue.modules.hub import ModuleHub
from sunday_blue.module_views.life_work import LifePage,clock_pair
from sunday_blue.module_views.life_widgets import recovery_rows,MuscleMap
from sunday_blue.window_geometry import initial_rect
from sunday_blue.art_assets import asset_spec
from sunday_blue.theme import style_for
APP=QApplication.instance() or QApplication([])
ROOT=Path(__file__).resolve().parents[1]
class LifeCockpitTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(dir=ROOT/'tests',prefix='sunday-ui-');self.cfg=Config(self.temp.name);self.hub=ModuleHub(self.cfg,Store(self.cfg.data),start_timer=False);self.pages=[]
 def tearDown(self):
  self.hub.close()
  for p in self.pages:p.close();p.deleteLater()
  self.hub.deleteLater();APP.processEvents();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.temp.cleanup()
 def test_visual_state_drilldown_and_no_data_changes(self):
  day=date.today().isoformat();self.hub.life.exercise('力量训练',40,'high',day=day,muscles=['胸','二头肌'])
  page=LifePage(self.hub);self.pages.append(page);page.setStyleSheet(style_for('light'));page.resize(1100,760);page.show();APP.processEvents()
  self.assertEqual(page.tabs.count(),6);self.assertEqual(page.trend.count(),7);self.assertFalse(page.cards['physical'].bar.isTextVisible())
  self.assertEqual(next(r for r in page.muscle_rows if r['part']=='胸')['level'],'red')
  self.assertEqual(next(r for r in page.muscle_rows if r['part']=='背')['level'],'unknown')
  page.part_buttons['二头肌'].click();self.assertIn('高强度',page.muscle_detail.text());self.assertIn('40 分钟',page.muscle_detail.text())
  before=self.hub.rewards.balances();page.refresh();self.assertEqual(before,self.hub.rewards.balances())
  for width in (700,1100):
   page.resize(width,760);APP.processEvents();self.assertLessEqual(page.minimumSizeHint().width(),width)
  page.open_daily();self.assertEqual(page.tabs.currentIndex(),1)
 def test_map_hit_regions_and_recovery_time(self):
  m=MuscleMap(self.cfg.root);self.pages.append(m);m.resize(440,330)
  self.assertEqual(m.part_at(QPointF(102,95)),'胸');self.assertEqual(m.part_at(QPointF(325,110)),'背')
  states=[{'part':'胸','level':'green','age':None}];old=(date.today()-timedelta(days=4)).isoformat()
  rows=recovery_rows(states,[dict(day=old,kind='力量训练',minutes=30,intensity='light',muscles='["胸"]')],date.today().isoformat())
  self.assertEqual(rows[0]['level'],'green');self.assertIn(old,rows[0]['detail'])
 def test_placeholder_keyboard_input_remains_direct(self):
  pair=clock_pair();self.pages.append(pair);pair.show();APP.processEvents();box=pair.hours
  QTest.mouseClick(box.lineEdit(),Qt.MouseButton.LeftButton);QTest.keyClicks(box.lineEdit(),'6');box.interpretText();self.assertEqual(pair.value(),'06:00')
 def test_art_manifest_and_work_areas(self):
  for key in ('recovery_body','recovery_scene'):
   spec=asset_spec(ROOT,key);self.assertTrue(spec['positive']);self.assertTrue(spec['negative']);self.assertTrue(spec['file'].is_relative_to(ROOT/'assets'))
  for bounds in (QRect(0,0,1366,728),QRect(-1920,40,1920,1040),QRect(0,0,1097,580)):
   self.assertTrue(bounds.contains(initial_rect(bounds)))
 def test_relationship_entry_and_real_window_work_area(self):
  from sunday_blue.ui import MainWindow
  from sunday_blue.modules.workspace import install_workspace
  w=MainWindow(self.cfg);h=install_workspace(w);h.timer.stop();h.focus_timer.stop()
  try:
   w.show();QTest.qWait(100);available=w.screen().availableGeometry()
   self.assertTrue(available.contains(w.frameGeometry()),str((available,w.frameGeometry())))
   self.assertFalse(any(b.text()=='关系' for b in w.module_navigation.buttons()))
   w.relationship_button.click();APP.processEvents();self.assertTrue(w.relations_dialog.isVisible());self.assertEqual(w.relations_panel.items.count(),len(h.relations.list()))
   w.relations_dialog.close();w.maximize();QTest.qWait(100);self.assertTrue(available.contains(w.frameGeometry()),str((available,w.frameGeometry())))
  finally:h.close();w.tray.exiting=True;w.close();w.tray.icon.hide();w.deleteLater();APP.processEvents()
