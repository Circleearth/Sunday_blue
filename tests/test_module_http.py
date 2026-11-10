import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from PySide6.QtWidgets import QApplication
from sunday_blue.storage import Config,Store
from sunday_blue.modules.hub import ModuleHub
from sunday_blue.modules.social import recent_context
from sunday_blue.models import RoleProvider

ROOT=Path(__file__).resolve().parents[1]
APP=QApplication.instance() or QApplication([])


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*a):pass
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));self.server.seen.append(body)
        text=self.server.answers.pop(0) if self.server.answers else '收到'
        if self.path.endswith('/messages'):
            result={'content':[{'type':'text','text':text}],'usage':{'input_tokens':12,'output_tokens':8},'stop_reason':'end_turn'}
        else:result={'choices':[{'message':{'content':text},'finish_reason':'stop'}],'usage':{'prompt_tokens':12,'completion_tokens':8}}
        self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(json.dumps(result,ensure_ascii=False).encode())


class ModuleHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'tests',prefix='sunday-test-')
        self.config=Config(self.temp.name);self.store=Store(self.config.data)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.server.answers=[];self.server.seen=[]
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.config.value['api'].update(base_url=f'http://127.0.0.1:{self.server.server_port}',model='local-fixture',stream=False)
        self.hub=ModuleHub(self.config,self.store,start_timer=False)
    def tearDown(self):
        for job in list(self.hub.jobs.values()):job.cancel.set();job.wait(5000)
        APP.processEvents();self.hub.close();self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()
    def wait(self):
        until=time.monotonic()+6
        while self.hub.jobs and time.monotonic()<until:APP.processEvents();time.sleep(.01)
        APP.processEvents();self.assertFalse(self.hub.jobs)
    def test_focus_to_group_summary_memory_private_followup_and_diagnostics(self):
        self.hub.focus.set_options({'llm_feedback':False})  # isolate social request ordering; dialogue has separate tests
        sid=self.store.create('rui');self.store.add(sid,'user','RUI_PRIVATE_SOURCE')
        other=self.store.create('red');self.store.add(other,'user','RED_PRIVATE_SOURCE')
        gid=self.hub.social.create_group('合成家庭会议',['rui','mia'],True)
        self.hub.social.set_settings(self.hub.social.get_settings()|dict(proactive_enabled=True,followup_enabled=True,
            group_id=gid,quiet_start=0,quiet_end=0,max_turns=1,daily_tokens=200000))
        clock=[0];self.hub.focus.clock=lambda:clock[0];self.hub.focus.start('学习',role_id='rui')
        for _ in range(25):clock[0]+=5;self.hub.focus.checkpoint()
        self.hub.focus.finish();self.server.answers=['今天这段学习很踏实。','我们需要复盘学习安排，但尚未作决定。','主动私聊_ONLY：刚才提到的安排，我们可以慢慢调整。']
        self.hub.tick();self.wait()
        self.hub.summarize_group(gid);self.wait()
        self.assertEqual(len(self.server.seen),3)
        self.assertIn('RUI_PRIVATE_SOURCE',self.server.seen[0]['system']);self.assertNotIn('RED_PRIVATE_SOURCE',self.server.seen[0]['system'])
        self.assertIn('RUI_PRIVATE_SOURCE',self.server.seen[2]['system'])
        group=json.dumps(self.hub.social.messages(gid),ensure_ascii=False)
        self.assertNotIn('主动私聊_ONLY',group)
        self.assertIn('尚未作决定',recent_context(self.config.root,'mia'))
        self.assertEqual(recent_context(self.config.root,'red'),'')
        private=self.store.messages(sid);self.assertEqual(sum('主动私聊_ONLY' in str(m['content']) for m in private),1)
        with self.hub.db.connect() as db:db.execute('UPDATE private_followups SET delivered=0')
        self.hub._deliver_private()
        self.assertEqual(len(self.store.messages(sid)),len(private))
        self.assertEqual(len(self.hub.diagnostics()),3);self.assertEqual(len(self.hub.focus.records()),1)
    def test_role_model_protocol_reasoning_and_request_metadata(self):
        self.config.value['roles']['rui']['model_profile']=dict(enabled=True,protocol='openai',model='reasoning-fixture',
            reasoning='openai_effort',reasoning_effort='high')
        RoleProvider(self.config.root,'rui',self.config.snapshot()).complete('system',[{'role':'user','content':'fixture'}])
        self.assertEqual(self.server.seen[-1]['model'],'reasoning-fixture');self.assertEqual(self.server.seen[-1]['reasoning_effort'],'high')
        diagnostics=self.hub.diagnostics()[0]
        self.assertEqual(diagnostics['model'],'reasoning-fixture');self.assertEqual(diagnostics['reasoning'],'high')
        self.assertNotIn('fixture',diagnostics['usage']);self.assertEqual(diagnostics['error'],'')
    def test_role_model_dialog_test_button_sends_real_request_and_cancel_writes_nothing(self):
        from sunday_blue.model_preferences import RoleModelDialog
        # open + cancel must not write any formal config value
        before=self.config.snapshot()
        dialog=RoleModelDialog(self.config.root,before,'red',None)
        dialog.model.setText('changed-but-cancelled')
        dialog.reject()
        self.assertEqual(self.config.value['roles']['red'],before['roles']['red'])
        # the test button makes a real request through the local fixture server
        self.server.answers=['OK']
        self.assertEqual(len(self.server.seen),0)
        dialog.test()
        deadline=time.monotonic()+6
        while dialog.worker and dialog.worker.isRunning() and time.monotonic()<deadline:APP.processEvents();time.sleep(.01)
        APP.processEvents()
        self.assertEqual(len(self.server.seen),1)
        self.assertIn('连接成功',dialog.result_label.text())
        dialog.deleteLater();APP.processEvents()

    def test_focus_dynamic_reply_uses_wire_context_without_chat_storage(self):
        self.server.answers=['先从眼前的小目标开始。'];feedback=[]
        self.hub.feedback.connect(lambda role,text:feedback.append(text))
        self.hub.start_focus('学习',duration=180)
        deadline=time.monotonic()+5
        while self.hub.focus_dialogue.busy and time.monotonic()<deadline:APP.processEvents();time.sleep(.01)
        self.assertIn('先从眼前的小目标开始。',feedback)
        self.assertEqual(len(self.server.seen),1)
        self.assertIn('长期熟悉度',self.server.seen[0]['system'])
        self.assertEqual(self.server.seen[0]['max_tokens'],120)
        self.assertEqual(self.hub.focus_dialogue.history[-1]['content'],'先从眼前的小目标开始。')
        self.hub.focus.finish();self.assertEqual(self.hub.focus_dialogue.history,[])
