import tempfile,unittest,threading,time
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QObject,Signal,QTimer,QCoreApplication,QEvent
from PySide6.QtWidgets import QApplication,QMessageBox
from sunday_blue.storage import Config
from sunday_blue.modules.database import ModuleDB
from sunday_blue.modules.markdown_library import MarkdownLibrary
from sunday_blue.modules.document_changes import DocumentChanges
from sunday_blue.modules.duties import Duties,context
from sunday_blue.modules.duty_tools import dispatch
from sunday_blue.files import FileTools
from sunday_blue.module_views.markdown_reader import MarkdownPage
ROOT=Path(__file__).resolve().parents[1];APP=QApplication.instance() or QApplication([])
class Hub(QObject):changed=Signal(str);closed=Signal()
class RevisionTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'tests',prefix='sunday-test-');self.root=Path(self.tmp.name)/'app';self.root.mkdir();self.cfg=Config(self.root);self.db=ModuleDB(self.root)
  self.docs=Path(self.tmp.name)/'library';self.docs.mkdir();self.file=self.docs/'record.md';self.original=b'\xef\xbb\xbf# Topic\r\n\r\nOriginal\r\n';self.file.write_bytes(self.original)
  self.library=MarkdownLibrary(self.db);self.library.set_root(self.docs);self.duties=Duties(self.db);self.changes=DocumentChanges(self.db)
 def tearDown(self):APP.processEvents();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.tmp.cleanup()
 def test_manual_save_snapshots_diff_handoff_and_noop(self):
  result=self.library.save(self.file,'# Topic\n\nNew content\n',self.original)
  self.assertTrue(self.file.read_bytes().startswith(b'\xef\xbb\xbf'));self.assertIn(b'\r\n',self.file.read_bytes())
  row=self.changes.get(result['revision_id']);self.assertIn('Original',row['before_text']);self.assertIn('New content',row['after_text']);self.assertEqual(len(self.duties.handoffs()),1)
  self.assertIn('-Original',self.changes.difference(row['before_text'],row['after_text']))
  self.assertEqual(self.library.save(self.file,'# Topic\n\nNew content\n',result['data'])['status'],'unchanged');self.assertEqual(len(self.changes.history(self.file)),1)
  self.assertIn('待核对交接',context(self.root,'kia'));self.assertTrue(dispatch(self.root,'kia','handoffs',{})['items'])
  self.assertIn('New content',dispatch(self.root,'mubu','file_revision',{'id':row['id']})['after'])
 def test_agent_file_write_and_denied_do_not_fake_handoff(self):
  ft=FileTools(self.root,'kia',[{'path':str(self.docs),'read':True,'write':True,'trusted':True}],lambda *args:True,lambda *args:None)
  result=ft.write(str(self.file),content='# Agent edit\n');self.assertTrue(result['handoff_id']);self.assertEqual(self.changes.get(result['revision_id'])['actor'],'kia')
  ft.rules[0]['trusted']=False;ft.approve=lambda *args:False
  self.assertEqual(ft.write(str(self.file),content='Rejected')['status'],'denied');self.assertEqual(len(self.duties.handoffs()),1)
 def test_conflict_and_recover_saved_without_handoff(self):
  self.file.write_text('External',encoding='utf-8')
  with self.assertRaises(ValueError):self.library.save(self.file,'Draft',self.original)
  self.assertEqual(self.file.read_text(),'External');self.assertEqual(self.changes.history(self.file),[])
  with patch.object(DocumentChanges,'finish',side_effect=RuntimeError('db unavailable')):r=self.library.save(self.file,'Saved',b'External')
  self.assertTrue(r['warning']);self.assertEqual(self.file.read_text(),'Saved');self.assertEqual(self.duties.handoffs(),[])
  self.changes.recover(self.file);self.changes.recover(self.file);self.assertEqual(len(self.duties.handoffs()),1)
 def test_ui_prompt_async_save_and_cancel(self):
  h=Hub();h.db=self.db;h.config=self.cfg;page=MarkdownPage(h);page.open_file(self.file);page.source.appendPlainText('My addition');self.assertTrue(page.source.document().isModified())
  with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Cancel):self.assertFalse(page.can_leave())
  started=threading.Event();release=threading.Event();real=page.library.save;done=[];beats=[];timer=QTimer();timer.timeout.connect(lambda:beats.append(1));timer.start(5)
  def slow(*args):started.set();release.wait(2);return real(*args)
  try:
   with patch.object(page.library,'save',side_effect=slow),patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Save):
    self.assertFalse(page.can_leave(lambda:done.append(1)));self.assertTrue(started.wait(1));end=time.monotonic()+1
    while len(beats)<3 and time.monotonic()<end:APP.processEvents();time.sleep(.01)
    self.assertGreaterEqual(len(beats),3);self.assertFalse(page.save_button.isEnabled());release.set();end=time.monotonic()+3
    while page.saving and time.monotonic()<end:APP.processEvents();time.sleep(.01)
    self.assertFalse(page.saving);self.assertEqual(done,[1]);self.assertFalse(page.source.document().isModified())
  finally:release.set();timer.stop();h.closed.emit();page.deleteLater();h.deleteLater()

 def test_navigation_cancel_discard_and_saved_continuation(self):
  from PySide6.QtWidgets import QWidget,QStackedWidget,QHBoxLayout
  from sunday_blue.modules.workspace import install_workspace
  h=Hub();h.db=self.db;h.config=self.cfg;h.failed=type('Event',(),{'connect':lambda *args:None})()
  page=MarkdownPage(h);page.open_file(self.file)
  window=QWidget();window.config=self.cfg;window.store=None;window.chat_page=QWidget();window.page_stack=QStackedWidget(window);window.page_stack.addWidget(window.chat_page);window.module_nav=QHBoxLayout();window.show_notice=lambda *a:None;window.refresh_sessions=lambda:None;window.sid=None
  self.cfg.value['main_page']='documents'
  with patch('sunday_blue.modules.workspace.ModuleHub',return_value=h),patch('sunday_blue.modules.workspace.create_pages',return_value=[('documents','资料',page)]):install_workspace(window)
  try:
   page.source.appendPlainText('Draft')
   with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Cancel):window.module_navigation.button(0).click()
   self.assertIs(window.page_stack.currentWidget(),page);self.assertTrue(window.module_navigation.button(1).isChecked())
   with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Save):window.module_navigation.button(0).click()
   end=time.monotonic()+3
   while page.saving and time.monotonic()<end:APP.processEvents();time.sleep(.01)
   self.assertIs(window.page_stack.currentWidget(),window.chat_page);self.assertIn('Draft',self.file.read_text(encoding='utf-8-sig'))
   window.module_navigation.button(1).click();page.source.appendPlainText('Discard this')
   with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Discard):window.module_navigation.button(0).click()
   self.assertIs(window.page_stack.currentWidget(),window.chat_page);self.assertNotIn('Discard this',page.source.toPlainText());self.assertNotIn('Discard this',self.file.read_text(encoding='utf-8-sig'))
  finally:h.closed.emit();window.deleteLater();h.deleteLater()
