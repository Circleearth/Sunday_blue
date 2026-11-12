"""UI service wiring for work, life records and fixed duty slots."""
from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
from PySide6.QtCore import Qt,QCoreApplication,QEvent,QTime
from PySide6.QtWidgets import QApplication
from sunday_blue.storage import Config,Store
from sunday_blue.modules.hub import ModuleHub
from sunday_blue.module_views.life_work import WorkPage,LifePage,DutiesPage
from sunday_blue.module_views.focus import FocusPage
APP=QApplication.instance() or QApplication([])
ROOT=Path(__file__).resolve().parents[1]

class LifeWorkViewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'tests',prefix='sunday-test-');self.config=Config(self.temp.name)
        self.hub=ModuleHub(self.config,Store(self.config.data),start_timer=False);self.pages=[]
    def tearDown(self):
        self.hub.close()
        for page in self.pages:page.close();page.deleteLater()
        self.hub.deleteLater();APP.processEvents();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.temp.cleanup()
    def page(self,cls):
        page=cls(self.hub);self.pages.append(page);return page
    def test_work_tree_and_focus_binding_follow_external_start(self):
        parent=self.hub.work.create('Project',estimate_minutes=120);child=self.hub.work.create('Write draft',parent_id=parent,estimate_minutes=30)
        self.hub.work.update(child,progress=40)
        work=self.page(WorkPage);focus=self.page(FocusPage)
        self.assertEqual(work.tree.topLevelItemCount(),1);self.assertEqual(work.tree.topLevelItem(0).childCount(),1)
        work.tree.setCurrentItem(work.tree.topLevelItem(0).child(0));work.start_selected()
        self.assertEqual(self.hub.focus.status()['task_id'],child);focus.refresh(True)
        self.assertEqual(focus.task.currentData(),child);self.assertFalse(focus.task.isEnabled())
        self.hub.focus.pause();self.assertEqual(self.hub.focus.status()['task_id'],child)
    def test_life_form_saves_and_reloads_without_duplicate_reward(self):
        page=self.page(LifePage);page.meal.setPlainText('米饭、蔬菜');page.has_sleep.setChecked(True);page.bed.setTime(QTime(23,0));page.wake.setTime(QTime(6,30));page.phone_total.setValue(80);page.phone_fun.setValue(30);page.save_daily()
        saved=self.hub.life.daily(page.selected_day());self.assertEqual(saved['phone_fun'],30)
        page.load_daily();self.assertEqual(page.meal.toPlainText(),'米饭、蔬菜');self.assertEqual(saved['sleep_hours'],7.5)
        self.hub.life.exercise('快走',20,'moderate');self.hub.changed.emit('life');self.assertEqual(page.exercises.count(),1)
        self.assertEqual(page.trend.count(),7)
        with patch('sunday_blue.module_views.life_work.QMessageBox.warning') as warning:
            page.phone_fun.setValue(100);page.save_daily();self.assertTrue(warning.called)
        self.assertEqual(self.hub.life.daily(page.selected_day())['phone_fun'],30)
    def test_duty_handoff_pending_failed_and_completed_views(self):
        page=self.page(DutiesPage);self.assertEqual(page.slots.topLevelItemCount(),7)
        row=self.hub.duties.capture('原始记录','需要后续归档','请整理到生活备忘');self.hub.changed.emit('duties')
        self.assertEqual(page.handoffs.count(),1);hid=page.handoffs.item(0).data(Qt.ItemDataRole.UserRole)['id']
        self.hub.duties.fail_handoff(hid,'需要确认分类');self.hub.changed.emit('duties');self.assertIn('失败',page.handoffs.item(0).text())
        self.hub.duties.complete_handoff(hid,'生活备忘',note='分类完成');self.hub.changed.emit('duties');self.assertEqual(page.handoffs.count(),0)
        page.done.setChecked(True);self.assertEqual(page.handoffs.count(),1)
        self.assertEqual(len(self.hub.organizer.search('原始记录')),1)
