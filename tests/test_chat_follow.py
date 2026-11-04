import shutil
import tempfile
import time
import unittest
from pathlib import Path
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from sunday_blue.storage import Config
from sunday_blue.ui import MainWindow

APP=QApplication.instance() or QApplication([])

class ChatFollowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='chat-follow-',dir=Path(__file__).parent)
        self.root=Path(self.temp.name)/'app';self.config=Config(self.root)
        project=Path(__file__).resolve().parents[1]
        shutil.copytree(project/'assets',self.root/'assets')
        shutil.copytree(project/'personas',self.root/'personas')
        (self.root/'extensions'/'skills').mkdir(parents=True)
        shutil.copytree(project/'extensions/plugins',self.root/'extensions/plugins')
        self.config.value['chat_display']={'segmented':False}
        self.window=MainWindow(self.config);self.window.show();APP.processEvents()
    def tearDown(self):
        APP.processEvents();self.window.close();self.window.deleteLater();APP.processEvents();self.temp.cleanup()
    def _fill(self,count=240):
        for i in range(count):self.window.store.add(self.window.sid,'assistant',f'历史消息 {i} '+(f'内容{i}。'*8))
        self.window.render();QTest.qWait(80)
    def test_reading_history_is_not_pulled_down_by_new_message(self):
        self._fill()
        bar=self.window.chat_scroll.verticalScrollBar()
        bar.setValue(800)
        self.assertNotIn(self.window._is_at_bottom(),(True,),)
        self.window.store.add(self.window.sid,'assistant','新的一条。')
        self.window.render(preserve=True);QTest.qWait(60)
        self.assertLessEqual(bar.value(),900)  # not dragged to the bottom
        self.assertTrue(self.window.follow_button.isVisible())
    def test_at_bottom_new_message_follows(self):
        self._fill()
        bar=self.window.chat_scroll.verticalScrollBar()
        bar.setValue(bar.maximum())
        self.window.store.add(self.window.sid,'assistant','最新回复。')
        self.window.render(preserve=True);QTest.qWait(60)
        self.assertEqual(bar.value(),bar.maximum())
        self.assertFalse(self.window.follow_button.isVisible())
    def test_append_does_not_destroy_existing_bubbles(self):
        self._fill(40)
        before=list(self.window.chat_bubbles)
        first_widgets=[item.widget() for i in range(self.window.chat_layout.count()) if (item:=self.window.chat_layout.itemAt(i)).widget()]
        self.window.store.add(self.window.sid,'assistant','再来一条。')
        self.window.render(preserve=True);QTest.qWait(60)
        self.assertEqual(before,self.window.chat_bubbles[:len(before)])  # same Bubble objects, not recreated
        self.assertTrue(all(w in first_widgets or w.parent() for w in first_widgets))
    def test_follow_button_returns_to_bottom_and_resumes_follow(self):
        self._fill()
        bar=self.window.chat_scroll.verticalScrollBar()
        bar.setValue(0);QTest.qWait(30)
        self.window.store.add(self.window.sid,'assistant','新消息。')
        self.window.render(preserve=True);QTest.qWait(60)
        self.assertTrue(self.window.follow_button.isVisible())
        self.window._follow_clicked();QTest.qWait(60)
        self.assertEqual(bar.value(),bar.maximum())
        self.assertFalse(self.window.follow_button.isVisible())
        self.window.store.add(self.window.sid,'assistant','又一条。')
        self.window.render(preserve=True);QTest.qWait(60)
        self.assertEqual(bar.value(),bar.maximum())  # follow resumed after clicking the hint

if __name__=='__main__':unittest.main()
