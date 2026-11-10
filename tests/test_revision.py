import json
import shutil
import threading
import time
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from pathlib import Path
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QDialog,QPushButton
from test_core import Fixture
from test_ui import UITests,APP
from sunday_blue.files import FileTools,FILE_SCHEMAS
from sunday_blue.plugin_runtime import discover,load,parameters,system_context
from sunday_blue.plugin_preferences import PluginPreferences
from sunday_blue.agent import Agent
from sunday_blue.settings import Settings

class RevisionCore(Fixture):
    def test_trusted_scope_and_backed_up_deletes(self):
        rules=[{'path':str(self.workspace),'write':True,'trusted':True}]
        with patch.object(self.files,'approve',return_value=False) as ask:
            self.files.rules=rules
            p=self.workspace/'doc';self.files.write(str(p),content='saved')
            result=self.files.delete_file(str(p));self.assertFalse(p.exists())
            self.assertEqual(Path(result['backup']).read_text(),'saved');ask.assert_not_called()
            with self.assertRaises(PermissionError):self.files.delete_directory(str(self.workspace))
            self.files.rules[0]['trusted']=False
            self.assertEqual(self.files.write(str(p),content='x')['status'],'denied')
            ask.assert_called_once()
        self.assertIn('delete_file',{s['name'] for s in FILE_SCHEMAS})

    def test_delete_revalidates_and_rejects_links(self):
        p=self.workspace/'folder';p.mkdir();f=p/'x';f.write_text('before')
        def change(*args):f.write_text('changed');return True
        self.files.approve=change
        with self.assertRaises(RuntimeError):self.files.delete_directory(str(p))
        self.assertTrue(f.exists())
        import os
        secret=self.base/'secret';secret.write_text('protected');os.link(secret,p/'linked')
        with self.assertRaises(PermissionError):self.files.delete_directory(str(p))

    def test_withdraw_preserves_audit_and_other_session(self):
        sid=self.store.create('rui');other=self.store.create('red')
        self.store.add(sid,'user','old');mid=self.store.add(sid,'user','withdraw me')
        self.store.add(sid,'assistant','partial');self.store.add(other,'user','keep')
        self.assertEqual(self.store.withdraw_turn(sid,mid),'withdraw me')
        self.assertEqual(len(self.store.messages(sid)),1);self.assertEqual(len(self.store.messages(other)),1)
        with self.store.connect() as db:self.assertIn('partial',db.execute("SELECT detail FROM audit WHERE action='withdraw_turn'").fetchone()[0])

    def test_external_plugins_schema_parameters_and_uninstall(self):
        c=self.config.snapshot();self.assertEqual(set(discover(self.root)),{'time-context','daypart-greetings','qq-reminders','livingmemory','focus-cheer'})
        c['roles']['rui']['plugin_settings']={'time-context':{'include_time':False}}
        c['roles']['rui']['native_plugins']={'qq-reminders':False}
        c['roles']['red']['native_plugins']={'qq-reminders':False}
        self.assertNotIn('本轮本地时间',system_context(self.root,c,'rui'))
        self.assertIn('本轮本地时间',system_context(self.root,c,'red'))
        shutil.rmtree(self.root/'extensions/plugins/time-context')
        self.assertEqual(system_context(self.root,c,'rui'),'')
        self.assertNotIn('time-context',discover(self.root))

    def test_idle_across_periods_failure_and_role_settings(self):
        g=load('daypart-greetings',self.root).Greetings(self.config.data);c=self.config.snapshot()
        at=datetime(2026,11,4,10,50,tzinfo=timezone(timedelta(hours=8)))
        self.assertIsNotNone(g.on_message(c,'rui','a',1,at))
        self.assertIsNone(g.on_message(c,'rui','b',2,at+timedelta(minutes=20)))
        self.assertIsNone(g.on_message(c,'rui','b',3,at+timedelta(minutes=80)))
        event=g.on_message(c,'rui','b',4,at+timedelta(minutes=141));self.assertIn('中午',event)
        g.discard('rui','b',4)
        self.assertIsNotNone(g.on_message(c,'rui','b',5,at+timedelta(minutes=142)))
        c['roles']['red']['plugin_settings']={'daypart-greetings':{'idle_minutes':5}}
        g.on_message(c,'red','c',1,at)
        self.assertIsNotNone(g.on_message(c,'red','c',2,at+timedelta(minutes=6)))

class RevisionUI(UITests):
    # Existing UI tests are inherited to exercise the same fixtures; only this class's
    # additional tests are loaded below to avoid duplicate execution.
    def test_stream_adoption_follow_and_user_scroll(self):
        w=self.window;self.config.value['chat_display']={'segmented':False}
        for i in range(25):w.store.add(w.sid,'assistant','历史。'*30)
        w.render();QTest.qWait(150)
        w.on_text(w.sid,'新回复。'*60);pending=w.pending;QTest.qWait(70)
        bar=w.chat_scroll.verticalScrollBar();self.assertEqual(bar.value(),bar.maximum())
        bar.setValue(100);w.on_text(w.sid,'追加。'*50);QTest.qWait(70);self.assertEqual(bar.value(),100)
        text=w.pending_text;w.store.add(w.sid,'assistant',text);w.render(preserve=True);QTest.qWait(70)
        self.assertIn(pending,w.chat_bubbles);self.assertIsNone(w.pending)
        self.assertEqual(sum(b.raw==text for b in w.chat_bubbles),1)

    def test_segments_advance_in_same_session_and_load_history(self):
        w=self.window;self.config.value['chat_display']={'segmented':True,'threshold':150}
        mid=w.store.add(w.sid,'assistant','第一句。第二句。第三句。')
        state={'count':1,'parts':['第一句。','第二句。','第三句。'],'next':0,'config':{'random_min':0,'random_max':0}}
        w.reveals[(w.sid,mid)]=state;w.render();self.assertEqual(len(w.chat_bubbles),1)
        w.advance_segments();w.advance_segments();self.assertEqual(len(w.chat_bubbles),3)
        for i in range(130):w.store.add(w.sid,'user',str(i))
        w._force_rebuild=True;w.render();QTest.qWait(120);w.more_history();QTest.qWait(120)
        self.assertTrue(any(b.raw=='第一句。' for b in w.chat_bubbles));self.assertEqual(len(w.chat_bubbles),133)

    def test_stop_waits_for_worker_then_restores_draft(self):
        w=self.window;w.config.value['api']['model']='mock'
        entered=threading.Event();release=threading.Event()
        def slow(*args,**kwargs):
            entered.set();release.wait(3);return ([{'type':'text','text':'late answer'}],{},'end_turn')
        with patch('sunday_blue.agent.Provider.complete',side_effect=slow):
            w.input.setPlainText('撤回的问题');w.send();self.wait_until(entered.is_set)
            w.input.setPlainText('新草稿');w.stop()
            self.assertTrue(w.workers);release.set();self.wait_until(lambda:not w.workers)
        self.assertEqual(w.input.toPlainText(),'撤回的问题\n新草稿')
        self.assertEqual(w.store.messages(w.sid),[])

    def test_schema_editor_roundtrip_role_and_close_option(self):
        dlg=Settings(self.config,'rui',self.window)
        dlg.tabs.setCurrentIndex(2);dlg.show();QTest.qWait(100)
        row=dlg.plugins.itemWidget(dlg.plugins.item(0));configure=row.findChild(QPushButton)
        self.assertTrue(configure.isVisible());self.assertGreater(configure.height(),15)
        def apply_visible():
            active=APP.activeModalWidget()
            if isinstance(active,PluginPreferences):active.fields['idle_minutes'][0].setValue(33);active.save()
        QTimer.singleShot(50,apply_visible);QTest.mouseClick(configure,Qt.MouseButton.LeftButton)
        self.assertEqual(dlg.value['roles']['rui']['plugin_settings']['daypart-greetings']['idle_minutes'],33)
        meta=discover(self.root)['daypart-greetings']
        form=PluginPreferences(meta,parameters(dlg.value,'rui','daypart-greetings',self.root))
        form.fields['idle_minutes'][0].setValue(25);form.save()
        self.assertEqual(form.result(),QDialog.DialogCode.Accepted)
        dlg.value['roles']['rui']['plugin_settings']={'daypart-greetings':form.values}
        dlg.close_to_tray.setChecked(True);dlg.save()
        self.assertEqual(parameters(self.config.snapshot(),'rui','daypart-greetings')['idle_minutes'],25)
        self.assertEqual(parameters(self.config.snapshot(),'red','daypart-greetings')['idle_minutes'],60)
        self.assertTrue(self.config.value['close_to_tray']);self.config.value['close_to_tray']=False
        self.assertTrue(dlg.plugins.findChildren(QPushButton));dlg.deleteLater();form.deleteLater()

    def test_repeated_bubble_fit_does_not_grow_and_tray_preserves_worker(self):
        from types import SimpleNamespace
        w=self.window;w.config.value['chat_display']={'segmented':False}
        w.store.add(w.sid,'assistant','测试长文字。'*30);w.render();QTest.qWait(100)
        bubble=w.chat_bubbles[0];height=bubble.height()
        for _ in range(10):bubble.fit()
        self.assertEqual(height,bubble.height())
        worker=SimpleNamespace(role='rui');w.workers[w.sid]=worker;w.config.value['close_to_tray']=True
        with patch('sunday_blue.tray.QSystemTrayIcon.isSystemTrayAvailable',return_value=True):
            self.assertFalse(w.close());self.assertFalse(w.isVisible());self.assertIs(w.workers[w.sid],worker)
        w.workers.clear();w.config.value['close_to_tray']=False;w.tray.show();self.assertTrue(w.isVisible());w.tray.icon.hide()

def load_tests(loader,tests,pattern):
    import unittest
    suite=loader.loadTestsFromTestCase(RevisionCore)
    for name in RevisionUI.__dict__:
        if name.startswith('test_'):suite.addTest(RevisionUI(name))
    return suite
