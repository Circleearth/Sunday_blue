import os
import json
import shutil
import tempfile
import threading
import time
from pathlib import Path
import unittest
from http.server import ThreadingHTTPServer
from PySide6.QtWidgets import QApplication, QDialog
from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest
from sunday_blue.storage import Config
from sunday_blue.ui import MainWindow
from sunday_blue.settings import Settings
from test_core import MockHandler

APP=QApplication.instance() or QApplication([])

class UITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='ui-test-',dir=Path(__file__).parent)
        self.root=Path(self.temp.name)/'app';self.config=Config(self.root)
        project=Path(__file__).resolve().parents[1]
        shutil.copytree(project/'assets',self.root/'assets')
        shutil.copytree(project/'personas',self.root/'personas')
        (self.root/'extensions'/'skills').mkdir(parents=True)
        (self.root/'extensions'/'plugins').mkdir(parents=True)
        self.window=MainWindow(self.config);self.window.show();APP.processEvents()
    def tearDown(self):
        for worker in list(self.window.workers.values()):worker.stop();worker.wait(65000)
        APP.processEvents();self.window.close();self.window.deleteLater();APP.processEvents();self.temp.cleanup()
    def wait_until(self,predicate,seconds=8):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            APP.processEvents()
            if predicate():return
            QTest.qWait(20)
        self.fail('UI timeout')
    def test_role_drafts_history_and_fork(self):
        self.window.input.setPlainText('unsent draft')
        original=self.window.sid
        self.window.switch_role('red');self.window.input.setPlainText('red draft');self.window.switch_role('rui')
        self.assertEqual(self.window.sid,original);self.assertEqual(self.window.input.toPlainText(),'unsent draft')
        self.window.store.add(original,'user','测试用户消息');self.window.store.add(original,'assistant',[{'type':'text','text':'测试气泡回复。\n代码与段落均可复制。'}])
        self.window.render();QTest.qWait(300);APP.processEvents()
        self.window.grab().save(str(Path(__file__).resolve().parents[1]/'docs'/'chat-preview.png'))
        self.window.fork_session();self.assertNotEqual(self.window.sid,original)
        self.assertEqual(len(self.window.store.messages(self.window.sid)),2)
    def test_settings_tabs_save_and_role_scopes(self):
        dlg=Settings(self.config,'rui',self.window);dlg.show();APP.processEvents()
        self.assertEqual(dlg.tabs.count(),6)
        dlg.model.setText('mock-model');dlg.url.setText('http://localhost:1234/v1')
        dlg.permission_role.setCurrentIndex(1);APP.processEvents();self.assertEqual(dlg.permission_role.currentData(),'red')
        for index in range(dlg.tabs.count()):dlg.tabs.setCurrentIndex(index);APP.processEvents()
        dlg.tabs.setCurrentIndex(0);QTest.qWait(150);APP.processEvents()
        dlg.grab().save(str(Path(__file__).resolve().parents[1]/'docs'/'settings-preview.png'))
        dlg.save();self.assertEqual(dlg.result(),QDialog.DialogCode.Accepted)
        self.assertEqual(Config(self.root).value['api']['model'],'mock-model')
        dlg.deleteLater()
    def test_concurrent_streams_and_real_review_dialog(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),MockHandler);server.mode='normal';server.seen=[]
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            self.config.value['api'].update(model='mock-test',base_url=f'http://127.0.0.1:{server.server_port}')
            self.window.input.setPlainText('hello rui');self.window.send();rui=self.window.sid
            self.window.switch_role('red');self.window.input.setPlainText('hello red');self.window.send();red=self.window.sid
            self.wait_until(lambda:not self.window.workers)
            self.assertEqual(len(self.window.store.messages(rui)),2);self.assertEqual(len(self.window.store.messages(red)),2)
            # Drive the actual difference-review dialog with a local mock response.
            work=Path(self.temp.name)/'work';work.mkdir();server.target=str(work/'ui.txt');server.mode='tool';server.seen=[]
            self.config.value['roles']['red']['roots']=[{'path':str(work),'write':True}]
            def accept_review():
                modal=APP.activeModalWidget()
                if isinstance(modal,QDialog):modal.accept()
            timer=QTimer();timer.timeout.connect(accept_review);timer.start(40)
            self.window.input.setPlainText('write a file');self.window.send()
            self.wait_until(lambda:not self.window.workers)
            timer.stop()
            self.assertEqual((work/'ui.txt').read_text(),'made by mock')
            self.assertEqual(self.window.chat_status.text(),'就绪')
        finally:server.shutdown();server.server_close()

    def test_ime_preedit_and_empty_placeholder(self):
        from PySide6.QtGui import QInputMethodEvent
        from PySide6.QtTest import QSignalSpy
        composer=self.window.input
        self.assertEqual(composer.placeholderText(),'')
        composer.send.disconnect()
        spy=QSignalSpy(composer.send)
        APP.sendEvent(composer,QInputMethodEvent('nihao',[]))
        self.assertTrue(composer._composing)
        self.assertEqual(composer.toPlainText(),'')
        commit=QInputMethodEvent();commit.setCommitString('你好')
        APP.sendEvent(composer,commit)
        self.assertFalse(composer._composing)
        self.assertEqual(composer.toPlainText(),'你好')
        QTest.keyClick(composer,Qt.Key.Key_Return)
        self.assertEqual(spy.count(),1)

    def test_theme_preserves_position_and_widgets(self):
        self.config.value['chat_display']={'segmented':False}
        for i in range(35):self.window.store.add(self.window.sid,'assistant',f'消息 {i} '+('一段内容。'*25))
        self.window.render();QTest.qWait(150)
        bar=self.window.chat_scroll.verticalScrollBar();bar.setValue(bar.maximum()//2)
        position=bar.value();bubbles=list(self.window.chat_bubbles)
        self.window.toggle_theme();QTest.qWait(120)
        self.assertEqual(self.window.chat_bubbles,bubbles)
        self.assertLessEqual(abs(bar.value()-position),3)
        self.window.scroll_bottom();position=bar.value()
        self.window.toggle_theme();QTest.qWait(120)
        self.assertLessEqual(abs(bar.value()-position),3)

    def test_bubbles_expand_and_resize_without_inner_scroll(self):
        from PySide6.QtWidgets import QAbstractScrollArea
        self.config.value['chat_display']={'segmented':False}
        self.window.store.add(self.window.sid,'assistant','短句。')
        self.window.store.add(self.window.sid,'assistant',('这是一段很长的消息，应该始终完整显示。'*20+'\n')*40)
        self.window.render();QTest.qWait(150)
        short,long=self.window.chat_bubbles
        self.assertLess(short.width(),long.width())
        self.assertGreaterEqual(long.width(),self.window.chat_scroll.viewport().width()*.75)
        self.assertGreater(long.height(),self.window.chat_scroll.viewport().height()*3)
        self.assertFalse(isinstance(long,QAbstractScrollArea))
        self.assertGreaterEqual(long.height(),long.heightForWidth(long.width()))
        wide=long.width();self.window.resize(1150,800);QTest.qWait(200)
        self.assertLess(long.width(),wide)
        self.assertGreaterEqual(long.height(),long.heightForWidth(long.width()))

    def test_success_tools_and_blank_text_hidden(self):
        self.window.store.add(self.window.sid,'assistant',[{'type':'text','text':'\n\n'},{'type':'tool_use','id':'x','name':'list_files','input':{}}])
        self.window.store.add(self.window.sid,'user',[{'type':'tool_result','tool_use_id':'x','content':'{}','is_error':False}])
        self.window.render();QTest.qWait(60)
        self.assertEqual(self.window.chat_bubbles,[])
        self.window.on_text(self.window.sid,'\n\n');self.assertIsNone(self.window.pending)
        self.window.store.add(self.window.sid,'user',[{'type':'tool_result','tool_use_id':'x','content':'{"error":"permission denied"}','is_error':True}])
        self.window.render();self.assertEqual(len(self.window.chat_bubbles),1)
        self.assertIn('permission denied',self.window.chat_bubbles[0].raw)

    def test_timed_segments_survive_role_switch(self):
        from types import SimpleNamespace
        sid=self.window.sid
        self.config.value['chat_display']={'random_min':.1,'random_max':.1}
        fake=SimpleNamespace(live_text='',start_after=0,role='rui')
        self.window.workers[sid]=fake
        self.window.store.add(sid,'assistant','第一句。第二句！第三句？')
        self.window.on_changed(sid)
        self.assertEqual(len(self.window.chat_bubbles),1)
        self.window.workers.pop(sid)
        self.window.switch_role('red');QTest.qWait(400);self.window.switch_role('rui')
        self.assertEqual(len(self.window.chat_bubbles),3)

    def test_import_font_and_persist_settings(self):
        from unittest.mock import patch
        from sunday_blue.chat_presentation import chat_font
        source=Path('C:/Windows/Fonts/msyh.ttc')
        if not source.exists():self.skipTest('No local test font')
        dlg=Settings(self.config,'rui',self.window)
        prefs=dlg.chat_preferences
        with patch('sunday_blue.chat_preferences.QFileDialog.getOpenFileName',return_value=(str(source),'')):
            prefs.import_font()
        saved=prefs.value()
        self.assertTrue((self.root/saved['font_file']).is_file())
        prefs.size.setValue(16);dlg.save()
        loaded=Config(self.root).value['chat_display']
        self.assertEqual(loaded['font_size'],16)
        self.assertEqual(chat_font(self.root,loaded).pointSize(),16)
        dlg.deleteLater()

if __name__=='__main__':unittest.main()
