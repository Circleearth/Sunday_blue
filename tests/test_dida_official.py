import json,tempfile,threading,unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from unittest.mock import patch
import requests
from PySide6.QtCore import QObject,Signal,Qt
from PySide6.QtWidgets import QApplication
from sunday_blue.modules.database import ModuleDB
from sunday_blue.modules.dida import Dida
from sunday_blue.modules.dida_mcp import DidaMCP
from sunday_blue.module_views.planner import CheckinsPage
from sunday_blue.modules.planner import Planner
ROOT=Path(__file__).resolve().parents[1]
APP=QApplication.instance() or QApplication([])

def task(**extra):return dict(id='t1',projectId='p1',title='Example',status=0,dueDate='2026-11-11',etag='v1',kind='TEXT',repeatFlag='')|extra

class Client:
    def __init__(self):self.calls=[];self.current=task();self.result=task(status=2);self.active=[self.current];self.fail=False
    def call(self,name,args):
        self.calls.append((name,args))
        if name=='list_projects':return [{'id':'p1','name':'Work'}]
        if name=='filter_tasks':return list(self.active)
        if name=='get_task_by_id':return self.current.copy()
        if self.fail:raise ValueError('unconfirmed')
        return self.result.copy()

class DidaTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'tests',prefix='sunday-test-');self.db=ModuleDB(self.tmp.name);self.s=Dida(self.db);self.c=Client();self.s.client=lambda:self.c
    def tearDown(self):self.tmp.cleanup()
    def writes(self):return [a for n,a in self.c.calls if n=='complete_task']
    def test_sync_preserves_ids_and_history(self):
        self.s.sync_official();self.s.sync_official();self.assertEqual(self.s.tasks()[0]['project_id'],'p1')
        self.assertEqual(self.s.tasks()[0]['project'],'Work')
        with self.db.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM dida_history').fetchone()[0],1)
        self.c.active=[];self.c.current=task(status=2);self.s.sync_official();self.assertEqual(self.s.tasks()[0]['status'],2)
    def test_complete_and_already_done(self):
        self.s.sync_official();self.s.complete('t1','2026-11-11','v1');self.assertEqual(self.writes(),[{'task_id':'t1','project_id':'p1'}]);self.assertEqual(self.s.tasks()[0]['status'],2)
        self.c.current=task(status=2);self.s.complete('t1','2026-11-11','v1');self.assertEqual(len(self.writes()),1)
    def test_stale_occurrence_never_written(self):
        self.c.current=task(dueDate='2026-11-12',etag='v2')
        with self.assertRaises(ValueError):self.s.complete('t1','2026-11-11','v1')
        self.assertEqual(self.writes(),[])
    def test_uncertain_write_not_retried(self):
        self.s.sync_official();self.c.fail=True
        for _ in range(2):
            with self.assertRaises(ValueError):self.s.complete('t1','2026-11-11','v1')
        self.assertEqual(len(self.writes()),1);self.assertEqual(self.s.tasks()[0]['status'],0)
    def test_recurrence_retains_completed_snapshot(self):
        self.c.current=task(repeatFlag='RRULE:FREQ=DAILY');self.c.result=task(repeatFlag='RRULE:FREQ=DAILY',dueDate='2026-11-12',etag='v2')
        self.s.complete('t1','2026-11-11','v1');self.assertEqual(self.s.tasks()[0]['status'],0)
        with self.db.connect() as db:history=[json.loads(r[0]) for r in db.execute('SELECT payload FROM dida_history')]
        self.assertTrue(any(r['status']==2 and r['due']=='2026-11-11' for r in history))
    def test_mismatched_identity_rejected(self):
        self.c.current=task(id='other')
        with self.assertRaises(ValueError):self.s.complete('t1','2026-11-11','v1')
        self.assertEqual(self.writes(),[])
        self.c.current=task();self.c.result=task(id='other',status=2)
        with self.assertRaises(ValueError):self.s.complete('t1','2026-11-11','v1')
        self.assertEqual(self.s.tasks(),[])
    def test_ui_render_filter_and_checkbox(self):
        class Hub(QObject):changed=Signal(str)
        h=Hub();h.dida=self.s;h.db=self.db;h.planner=Planner(self.db);h.jobs={}
        self.s.official_enabled=lambda:True;self.s.sync_official();page=CheckinsPage(h)
        with patch.object(page,'run_job') as run:
            page.refresh();self.assertFalse(run.called)
            page.query.setText('absent');self.assertEqual(page.remote.count(),0)
            page.query.clear();page.remote.item(0).setCheckState(Qt.CheckState.Checked)
            run.assert_called_once();self.assertEqual(page.remote.item(0).checkState(),Qt.CheckState.Unchecked)
        page.close();page.deleteLater();APP.processEvents()

class WireTests(unittest.TestCase):
    def test_official_json_sse_and_errors_over_local_http(self):
        seen=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                p=json.loads(self.rfile.read(int(self.headers['Content-Length'])));seen.append((p,dict(self.headers)))
                if 'id' not in p:self.send_response(202);self.end_headers();return
                if p['method']=='initialize':result={'protocolVersion':'2025-03-26'}
                else:
                    name=p['params']['name']
                    value={'error':'private server message'} if name=='get_task_by_id' else task(status=2) if name=='complete_task' else []
                    result={'content':[{'type':'text','text':json.dumps(value)}]}
                body=json.dumps({'jsonrpc':'2.0','id':p['id'],'result':result})
                sse=p['method']=='tools/call'
                if sse:body='event: message\ndata: '+body+'\n\n'
                raw=body.encode();self.send_response(200);self.send_header('Content-Type','text/event-stream' if sse else 'application/json');self.send_header('Mcp-Session-Id','fixture');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def post(url,**kwargs):return requests.post('http://127.0.0.1:'+str(server.server_port),**kwargs)
        try:
            c=DidaMCP('dp_fixture',post);self.assertEqual(c.call('list_projects',{}),[])
            self.assertEqual(c.call('complete_task',{'project_id':'p1','task_id':'t1'})['status'],2)
            with self.assertRaisesRegex(ValueError,'记录不可访问'):c.call('get_task_by_id',{'task_id':'t1'})
            with self.assertRaises(PermissionError):c.call('delete_project',{})
            self.assertEqual(seen[-1][1].get('Mcp-Session-Id'),'fixture')
            self.assertEqual(seen[-1][1].get('Authorization'),'Bearer dp_fixture')
        finally:server.shutdown();server.server_close();thread.join()
    def test_network_error_is_sanitized(self):
        def post(*args,**kwargs):raise requests.Timeout('secret header')
        with self.assertRaises(ValueError) as caught:DidaMCP('dp_fixture',post)
        self.assertNotIn('secret',str(caught.exception))
