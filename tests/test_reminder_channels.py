"""QQ delivery regression: UI remains responsive and scheduled sends use the tested wire path."""
import json,tempfile,time,threading,unittest,urllib.request
from pathlib import Path
from datetime import datetime,timedelta
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from unittest.mock import patch
from PySide6.QtCore import QTimer,QCoreApplication,QEvent
from PySide6.QtWidgets import QApplication
from sunday_blue.storage import Config,Store
from sunday_blue.modules.hub import ModuleHub
from sunday_blue.module_views.planner import RemindersPage
from sunday_blue.module_views.reminder_settings import ReminderSettings
APP=QApplication.instance() or QApplication([])
ROOT=Path(__file__).resolve().parents[1]

class ReminderTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'tests',prefix='sunday-test-');self.cfg=Config(self.temp.name)
        self.hub=ModuleHub(self.cfg,Store(self.cfg.data),start_timer=False);self.delivery=self.hub.reminder_delivery
        self.channel={'profile':'qqbot','openid':'test_owner','proxy':''};self.hub.db.set('shared_qq',self.channel)
    def tearDown(self):
        self.hub.close();self.hub.deleteLater();APP.processEvents();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.temp.cleanup()
    def until(self,predicate,seconds=3):
        end=time.monotonic()+seconds
        while time.monotonic()<end and not predicate():APP.processEvents();time.sleep(.005)
        self.assertTrue(predicate())
    def test_dialog_async_uses_draft_and_no_auto_network(self):
        started=threading.Event();release=threading.Event();seen=[]
        def send(text='test',cfg=None):seen.append(cfg.copy());started.set();release.wait(3);return True
        with patch.object(self.delivery,'test_send',side_effect=send) as mocked:
            page=RemindersPage(self.hub);page.qq();dialog=page.settings_dialog;self.assertFalse(mocked.called)
            dialog.openid.setText('draft_owner');beats=[];timer=QTimer();timer.setInterval(5);timer.timeout.connect(lambda:beats.append(1));timer.start()
            try:
                begin=time.monotonic();dialog.start(True);self.assertLess(time.monotonic()-begin,.5);self.assertTrue(started.wait(1))
                self.until(lambda:len(beats)>3);self.assertFalse(dialog.send.isEnabled())
                self.assertEqual(seen[0]['openid'],'draft_owner');self.assertEqual(self.hub.db.get('shared_qq')['openid'],'test_owner')
                with self.assertRaises(ValueError):self.delivery.start_check(self.channel)
                release.set();self.until(lambda:dialog.request is None);self.assertTrue(dialog.send.isEnabled());self.assertIn('已接受',dialog.status.text())
            finally:release.set();timer.stop();dialog.close();page.close();page.deleteLater();APP.processEvents()
    def test_close_dialog_during_check_is_safe(self):
        release=threading.Event();started=threading.Event()
        def diagnose(cfg):started.set();release.wait(2);return {'token_ok':True}
        with patch.object(self.delivery,'diagnose',side_effect=diagnose):
            dialog=ReminderSettings(self.hub);dialog.start(False);self.assertTrue(started.wait(1));dialog.close()
            QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);release.set();self.until(lambda:not self.delivery._check_busy);APP.processEvents()
    def test_actual_transport_http_receipt_and_no_duplicate(self):
        received=[];release=threading.Event()
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])));received.append((self.path,payload))
                if self.path=='/token':data={'access_token':'fixture'}
                else:release.wait(2);data={'id':'receipt'}
                raw=json.dumps(data).encode();self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        real=self.delivery._transport()
        class Opener:
            def open(self,request,timeout):
                target='/token' if 'getAppAccessToken' in request.full_url else '/message'
                return urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{server.server_port}'+target,data=request.data,headers=dict(request.headers)),timeout=timeout)
        try:
            with patch.object(real,'_creds',return_value={'appId':'fixture','appSecret':'fixture'}),patch.object(real,'_opener',return_value=Opener()):
                rid=self.hub.planner.add('定时渠道测试',(datetime.now().astimezone()-timedelta(seconds=1)).isoformat(),local=False,qq=True)
                begin=time.monotonic();self.delivery.tick();self.assertLess(time.monotonic()-begin,.5)
                self.until(lambda:len(received)==2);self.delivery.tick();self.assertEqual(len(received),2)
                release.set();self.until(lambda:not self.delivery.active)
                row=self.hub.planner.history()[0];self.assertEqual(row['qq_status'],'sent');self.assertEqual(row['schedule_id'],rid)
                self.assertEqual(received[1][1]['markdown']['content'],'定时渠道测试')
                self.assertEqual(self.delivery.details()[row['id']]['attempts'],1)
                self.delivery.tick();self.assertEqual(len(received),2)
        finally:release.set();server.shutdown();server.server_close();thread.join()
    def test_failure_durable_manual_retry_and_error_visible(self):
        rid=self.hub.planner.add('失败记录',(datetime.now().astimezone()-timedelta(seconds=1)).isoformat(),local=False,qq=True)
        with patch.object(self.delivery,'test_send',side_effect=TimeoutError('private detail')) as send:
            self.delivery.tick();self.until(lambda:not self.delivery.active);self.delivery.tick();self.assertEqual(send.call_count,1)
        row=self.hub.planner.history()[0];self.assertEqual(row['qq_status'],'failed');detail=self.delivery.details()[row['id']]
        self.assertNotIn('private',detail['error']);page=RemindersPage(self.hub);self.assertIn('超时',page.history.item(0).text())
        self.hub.planner.mark(row['id'],'qq','pending')
        with patch.object(self.delivery,'test_send',return_value=True):self.delivery.tick();self.until(lambda:not self.delivery.active)
        self.assertEqual(self.hub.planner.history()[0]['qq_status'],'sent');self.assertEqual(self.delivery.details()[row['id']]['attempts'],2)
        page.close();page.deleteLater()
    def test_validate_empty_token_and_profiles(self):
        with self.assertRaises(ValueError):self.delivery.validate(self.channel|{'profile':'../other'})
        with self.assertRaises(ValueError):self.delivery.validate(self.channel|{'proxy':'socks5://localhost:9000'})
        transport=type('Transport',(),{'_creds':staticmethod(lambda p:{'a':'b'}),'_token':staticmethod(lambda c,cfg:None)})
        with patch.object(self.delivery,'_transport',return_value=transport):
            result=self.delivery.diagnose();self.assertFalse(result['token_ok']);self.assertTrue(result['creds_ok'])
            with self.assertRaises(ValueError):self.delivery.test_send()
    def test_edit_keeps_history_and_page_selection(self):
        past=datetime.now().astimezone()-timedelta(seconds=2);rid=self.hub.planner.add('Old',past.isoformat(),local=False,qq=True);self.hub.planner.due()
        future=datetime.now().astimezone()+timedelta(hours=2);self.hub.planner.update(rid,'New',future.isoformat(),qq=True)
        self.assertEqual(self.hub.planner.history()[0]['title'],'Old');self.assertEqual(self.hub.planner.schedules()[0]['title'],'New')
        self.hub.planner.enable(rid,True);page=RemindersPage(self.hub);page.items.setCurrentRow(0);page.history.setCurrentRow(0);page.refresh()
        self.assertIsNotNone(page.items.currentItem());self.assertIsNotNone(page.history.currentItem());self.assertTrue(page.edit_button.isEnabled())
        page.search.setText('missing');self.assertEqual(page.items.count(),0);page.close();page.deleteLater()
