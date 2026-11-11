import tempfile,unittest
from pathlib import Path
from PySide6.QtWidgets import QApplication
from sunday_blue.storage import Config,Store
from sunday_blue.ui import MainWindow
from sunday_blue.chat_history import ChatHistory
APP=QApplication.instance() or QApplication([])
ROOT=Path(__file__).resolve().parents[1]
class HistoryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'tests',prefix='sunday-test-');self.cfg=Config(self.tmp.name);self.store=Store(self.cfg.data);self.sid=self.store.create('rui')
  for i in range(65):self.store.add(self.sid,'user' if i%2==0 else 'assistant',f'消息 {i}')
  with self.store.connect() as db:db.execute("UPDATE messages SET created='2026-11-10T12:00:00' WHERE session=? AND id IN (SELECT id FROM messages WHERE session=? ORDER BY id LIMIT 25)",(self.sid,self.sid))
 def tearDown(self):self.tmp.cleanup()
 def test_bounded_day_pages_and_context_unchanged(self):
  rows,more=self.store.message_page(self.sid);self.assertEqual(len(rows),20);self.assertTrue(more);self.assertEqual(rows[-1]['content'],'消息 64')
  rows,more=self.store.message_page(self.sid,day='2026-11-10');self.assertEqual(len(rows),20);self.assertTrue(more)
  older,more=self.store.message_page(self.sid,day='2026-11-10',before=rows[0]['id']);self.assertEqual(len(older),5);self.assertFalse(more)
  self.assertEqual(len(self.store.messages(self.sid,context=True)),65)
 def test_main_window_prunes_and_history_is_separate(self):
  window=MainWindow(self.cfg);window.sid=self.sid;window.render();APP.processEvents()
  self.assertEqual(len(window._message_rows),20)
  self.store.add(self.sid,'user','新消息');window.render();APP.processEvents();self.assertEqual(len(window._message_rows),20)
  history=ChatHistory(self.store,self.sid,window);history.days.setCurrentIndex(history.days.findData('2026-11-10'));self.assertEqual(len(history.rows),20)
  history.next();self.assertEqual(len(history.rows),5);history.previous();self.assertEqual(len(history.rows),20)
  self.assertEqual(window.sid,self.sid);history.close();history.deleteLater();window.close();window.deleteLater();APP.processEvents()
