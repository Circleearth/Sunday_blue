"""Notebook persistence, progress, navigation and next-day work notes."""
import tempfile,unittest
from pathlib import Path
from datetime import date,timedelta
from unittest.mock import patch
from PySide6.QtWidgets import QApplication,QPushButton,QPlainTextEdit,QMessageBox
from PySide6.QtCore import QCoreApplication,QEvent,Qt
from sunday_blue.storage import Config,Store
from sunday_blue.modules.hub import ModuleHub
from sunday_blue.module_views.learning_notebook import LearningPage,NotebookDialog
from sunday_blue.module_views.life_work import WorkPage
APP=QApplication.instance() or QApplication([])
ROOT=Path(__file__).resolve().parents[1]
class NotebookTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'tests',prefix='sunday-notebook-');cfg=Config(self.tmp.name);self.h=ModuleHub(cfg,Store(cfg.data),start_timer=False);self.h.focus.set_options({'llm_feedback':False});self.widgets=[];self.l=self.h.learning
  self.course=self.l.add('subject','数学');self.chapter=self.l.add('chapter','函数',self.course);self.a=self.l.add('unit','导数',self.chapter);self.b=self.l.add('unit','积分',self.chapter)
 def tearDown(self):
  self.h.close()
  for w in self.widgets:w.close();w.deleteLater()
  self.h.deleteLater();APP.processEvents();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.tmp.cleanup()
 def test_notes_states_and_read_flag_are_separate_from_contract_mastery(self):
  self.l.save_notebook(self.a,'知识备注','为什么能求导','关联物理速度','familiar');self.l.save_notebook(self.b,'积分入门',state='learning');self.l.chapter_done(self.chapter,True)
  chapter=self.l.notebook(self.chapter);self.assertEqual(chapter['progress'],75);self.assertEqual(chapter['familiar_count'],1);self.assertTrue(chapter['done']);self.assertFalse(self.l.evidence(self.a)['mastered'])
  self.assertEqual(self.l.notebook(self.a)['questions'],'为什么能求导')
  from sunday_blue.modules.learning import Learning
  self.assertEqual(Learning(self.h.db).notebook(self.a)['extensions'],'关联物理速度')
  self.l.rename(self.a,'导数与变化');self.assertEqual(self.l.notebook(self.a)['note'],'知识备注')
 def test_revisions_noop_and_stale_save_guard(self):
  self.l.save_notebook(self.a,'v1');old=self.l.notebook(self.a);self.l.save_notebook(self.a,'v1')
  with self.h.db.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM learning_note_history').fetchone()[0],1)
  self.l.save_notebook(self.a,'v2')
  with self.assertRaises(ValueError):self.l.save_notebook(self.a,'stale',expected=old)
  self.assertEqual(self.l.notebook(self.a)['note'],'v2')
  with self.assertRaises(ValueError):self.l.save_notebook(self.chapter,'note',state='familiar')
 def test_page_notes_search_next_and_no_assessment_controls(self):
  self.l.save_notebook(self.a,'导数小结','困惑待问','应用到速度');page=LearningPage(self.h);self.widgets.append(page);page.resize(1100,760);page.show();APP.processEvents();page.tree.setCurrentItem(page.items[self.a]);self.assertIn('困惑待问',page.readers['questions'].toPlainText())
  page.next_unit();self.assertEqual(page.selected()['id'],self.b);page.search.setText('困惑待问');self.assertFalse(page.items[self.a].isHidden());self.assertTrue(page.items[self.b].isHidden());self.assertFalse(page.items[self.course].isHidden())
  titles=[b.text() for b in page.findChildren(QPushButton)];self.assertNotIn('更新自评',titles);self.assertNotIn('复习检验',titles)
  page.search.clear();page.tree.setCurrentItem(page.items[self.chapter]);page.read_done.click();self.assertTrue(self.l.notebook(self.chapter)['done']);page.next_unit();self.assertEqual(page.selected()['id'],self.a)
 def test_next_note_does_not_rebind_running_focus(self):
  page=LearningPage(self.h);self.widgets.append(page);page.tree.setCurrentItem(page.items[self.a]);page.start();run=self.h.focus.status()['id'];page.next_unit()
  with self.h.db.connect() as c:self.assertEqual(c.execute('SELECT unit FROM learning_focus_links WHERE run_id=?',(run,)).fetchone()[0],self.a)
 def test_unsaved_dialog_does_not_discard_without_confirmation(self):
  dlg=NotebookDialog();self.widgets.append(dlg);editor=QPlainTextEdit(dlg);editor.setPlainText('initial');editor.insertPlainText('changed');dlg.editors={'note':editor};dlg.show();APP.processEvents()
  with patch('sunday_blue.module_views.learning_notebook.QMessageBox.question',return_value=QMessageBox.StandardButton.No):dlg.reject();self.assertTrue(dlg.isVisible())
  with patch('sunday_blue.module_views.learning_notebook.QMessageBox.question',return_value=QMessageBox.StandardButton.Yes):dlg.reject();self.assertFalse(dlg.isVisible())
 def test_work_note_tomorrow_persists_revisions_and_refresh_keeps_draft(self):
  today=date.today();tomorrow=(today+timedelta(days=1)).isoformat();w=self.h.work;target=w.leave_for_tomorrow('明天继续报告',today=today);self.assertEqual(target,tomorrow);self.assertEqual(w.day_note(tomorrow),'明天继续报告');self.assertEqual(w.day_note(today.isoformat()),'')
  w.leave_for_tomorrow('明天继续报告',today=today)
  with self.h.db.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM work_day_note_history').fetchone()[0],0)
  w.leave_for_tomorrow('先核对数据',today=today)
  with self.h.db.connect() as c:self.assertEqual(c.execute('SELECT body FROM work_day_note_history').fetchone()[0],'明天继续报告')
  w.leave_for_tomorrow('今天的接续',today=today-timedelta(days=1));page=WorkPage(self.h);self.widgets.append(page);self.assertIn('今天的接续',page.today_note.toPlainText())
  page.tomorrow_note.insertPlainText('尚未保存');draft=page.tomorrow_note.toPlainText();page.refresh();self.assertEqual(page.tomorrow_note.toPlainText(),draft)
  titles=[b.text() for b in page.findChildren(QPushButton)];self.assertFalse(any('恢复安排' in t or '下班结算' in t for t in titles));page.save_tomorrow();self.assertEqual(w.day_note(tomorrow),draft)
