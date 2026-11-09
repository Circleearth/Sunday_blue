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
        shutil.copytree(project/'extensions/plugins',self.root/'extensions/plugins')
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
    def test_archive_delete_and_restore_flow(self):
        from unittest.mock import patch
        import PySide6.QtWidgets as W
        sid=self.window.sid
        self.window.store.add(sid,'user','归档测试消息')
        count_before=len(self.window.store.sessions(self.window.role))
        # archiving the only session must NOT create a new one (no side effect);
        # it should leave the user in an empty welcome state (sid=None).
        with patch.object(W.QMessageBox,'question',return_value=W.QMessageBox.StandardButton.Yes):
            self.window._menu_target=sid;self.window._menu_archive()
        self.assertEqual(self.window.store.session(sid)['archived'],1)
        self.assertNotIn(sid,[s['id'] for s in self.window.store.sessions(self.window.role)])
        self.assertIsNone(self.window.sid)
        self.assertEqual(len(self.window.store.messages(sid)),1)  # data preserved under archive
        # restoring (what the "已归档" dialog does) must NOT create a session either
        self.window.store.archive(sid,False)
        self.assertEqual(self.window.store.session(sid)['archived'],0)
        self.assertIn(sid,[s['id'] for s in self.window.store.sessions(self.window.role)])
        # the welcome screen's send() creates a fresh session on demand; stub out
        # the worker so no real Agent thread / Settings dialog is involved.
        self.config.value['api']['model']='mock'
        self.window.input.setPlainText('归档后新消息')
        with patch.object(self.window,'start_worker',lambda:None):
            self.window.send()
        new_sid=self.window.sid
        self.assertIsNotNone(new_sid); self.assertNotEqual(new_sid,sid)
        self.assertEqual(len(self.window.store.sessions(self.window.role)),count_before+1)
        # delete flow: a separate session is permanently removed; opening it must
        # fall back to an existing remaining session, never a fresh blank "新对话".
        other=self.window.store.create(self.window.role)
        self.window.store.add(other,'user','将被删除')
        third=self.window.store.create(self.window.role)
        self.window.store.add(third,'user','留下的会话')
        self.window.current_by_role[self.window.role]=other; self.window.sid=other  # open it, so we leave it
        with patch.object(W.QMessageBox,'question',return_value=W.QMessageBox.StandardButton.Yes):
            self.window._menu_target=other;self.window._menu_delete()
        self.assertIsNone(self.window.store.session(other))
        self.assertEqual(len(self.window.store.messages(other)),0)
        self.assertEqual(len(self.window.store.sessions(self.window.role)),count_before+2)  # only the 3 that existed survive
        self.assertIn(self.window.sid,{sid,new_sid,third})  # fell back to a real session, none created
    def test_settings_tabs_save_and_role_scopes(self):
        dlg=Settings(self.config,'rui',self.window);dlg.show();APP.processEvents()
        self.assertEqual(dlg.tabs.count(),7)
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

    def test_ui_font_is_fixed_size_and_chat_fonts_are_role_scoped(self):
        from sunday_blue.chat_presentation import chat_font
        dlg=Settings(self.config,'rui',self.window);prefs=dlg.chat_preferences
        self.assertFalse(hasattr(prefs,'ui_size'))
        prefs.ui_family.setCurrentIndex(max(0,prefs.ui_family.findData('YouYuan')))
        prefs.family.setCurrentIndex(max(0,prefs.family.findData('Noto Sans SC')))
        prefs.role.setCurrentIndex(prefs.role.findData('red'))
        prefs.family.setCurrentIndex(max(0,prefs.family.findData('STXinwei')))
        dlg.nav.setCurrentRow(5);dlg.show();QTest.qWait(120);APP.processEvents()
        dlg.grab().save(str(Path(__file__).resolve().parents[1]/'docs'/'appearance-redesign-preview.png'))
        dlg.save();loaded=Config(self.root).value
        self.assertEqual(loaded['ui_display']['font_family'],'YouYuan')
        self.assertEqual(chat_font(self.root,loaded['chat_display'],'rui').family(),'Noto Sans SC')
        self.assertEqual(chat_font(self.root,loaded['chat_display'],'red').family(),'STXinwei')
        dlg.deleteLater()

    def test_saving_appearance_keeps_pending_segment_schedule(self):
        from unittest.mock import patch
        sid=self.window.sid
        self.window.reveals[(sid,123)]={'parts':['一。','二。'],'count':1,'next':time.monotonic()+20,'config':{}}
        with patch('sunday_blue.ui.Settings') as dialog:
            dialog.return_value.exec.return_value=QDialog.DialogCode.Accepted
            self.window.settings()
        self.assertIn((sid,123),self.window.reveals)

    def test_native_plugin_checkboxes_are_role_scoped_and_persist(self):
        dlg=Settings(self.config,'rui',self.window)
        items={dlg.plugins.item(i).data(Qt.ItemDataRole.UserRole)[1]:dlg.plugins.item(i) for i in range(dlg.plugins.count())}
        self.assertIn('time-context',items);self.assertIn('daypart-greetings',items)
        items['time-context'].setCheckState(Qt.CheckState.Unchecked)
        dlg.plugin_role.setCurrentIndex(1)
        self.assertEqual(dlg.plugins.item(0).checkState(),Qt.CheckState.Checked)
        dlg.value['roles']['rui'].setdefault('plugin_settings',{})['daypart-greetings']={'night_interval_minutes':20};dlg.save()
        from sunday_blue.native_plugins import enabled
        saved=Config(self.root).value
        self.assertFalse(enabled(saved,'rui','time-context'));self.assertTrue(enabled(saved,'red','time-context'))
        self.assertEqual(saved['roles']['rui']['plugin_settings']['daypart-greetings']['night_interval_minutes'],20)
        dlg.deleteLater()

    def test_new_trigger_not_rendered_and_legacy_greeting_retained(self):
        from datetime import datetime,timezone
        mid=self.window.store.add(self.window.sid,'user','hello')
        from sunday_blue.daypart_greetings import Greetings
        plugin=Greetings(self.config.data)
        plugin.on_message(self.config.value,'rui',self.window.sid,mid,datetime(2026,11,3,8,tzinfo=timezone.utc))
        self.window.render();QTest.qWait(80)
        self.assertEqual(len(self.window.chat_bubbles),1)
        with plugin.connection() as db:
            db.execute('INSERT INTO events VALUES(?,?,?,?)',(self.window.sid,mid,'早上好，旧版寒暄','2026-11-03'))
        self.window.render();self.assertEqual(len(self.window.chat_bubbles),2)
        self.assertIn('早上',self.window.chat_bubbles[-1].raw)
        self.assertEqual(len(self.window.store.messages(self.window.sid,True)),1)

if __name__=='__main__':unittest.main()
