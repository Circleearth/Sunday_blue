import shutil
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sunday_blue.storage import Config, Store, protect, plain
from sunday_blue.files import FileTools
from sunday_blue.provider import Provider, endpoint, openai_messages
from sunday_blue.agent import Agent, is_compact_command
from sunday_blue.extensions import MCPClient, validate_servers, extension_text

class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='sunday-test-',dir=Path(__file__).parent)
        self.base=Path(self.temp.name);self.root=self.base/'app';self.workspace=self.base/'work';self.workspace.mkdir()
        self.config=Config(self.root);self.store=Store(self.config.data)
        shutil.copytree(Path(__file__).resolve().parents[1]/'extensions/plugins',self.root/'extensions/plugins')
        self.audit=[]
        self.files=FileTools(self.root,'rui',[{'path':str(self.workspace),'write':True}],lambda *a:True,lambda *a:self.audit.append(a))
    def tearDown(self):self.temp.cleanup()

class FileTests(Fixture):
    def test_scoped_read_and_write_backup(self):
        path=self.workspace/'hello.txt';path.write_text('hello\n',encoding='utf-8')
        result=self.files.write(str(path),old_text='hello',new_text='world')
        self.assertEqual(path.read_text(),'world\n')
        self.assertEqual(Path(result['backup']).read_text(),'hello\n')
        self.assertEqual(self.files.read(str(path)),'world\n')
    def test_denied_outside_readonly_traversal_internal_ads(self):
        outside=self.base/'secret.txt';outside.write_text('secret')
        for path in [str(outside),str(self.workspace/'..'/'secret.txt'),str(self.config.path),str(self.workspace/'file.txt:secret')]:
            with self.assertRaises(PermissionError):self.files.read(path)
        self.files.rules[0]['write']=False
        with self.assertRaises(PermissionError):self.files.write(str(self.workspace/'x.txt'),content='x')
    def test_denial_does_not_write(self):
        self.files.approve=lambda *a:False
        p=self.workspace/'new.txt'
        self.assertEqual(self.files.write(str(p),content='x')['status'],'denied');self.assertFalse(p.exists())
    def test_conflict_after_review(self):
        p=self.workspace/'a.txt';p.write_text('original')
        def approval(*args):p.write_text('user edit');return True
        self.files.approve=approval
        with self.assertRaises(RuntimeError):self.files.write(str(p),content='AI edit')
        self.assertEqual(p.read_text(),'user edit')
    def test_hardlink_denied(self):
        p=self.base/'secret.txt';p.write_text('secret');os.link(p,self.workspace/'alias.txt')
        with self.assertRaises(PermissionError):self.files.read(str(self.workspace/'alias.txt'))
    def test_search_and_memory_isolation(self):
        (self.workspace/'a.txt').write_text('alpha\nbeta\nalpha')
        self.assertEqual(len(self.files.search(str(self.workspace),'alpha')['matches']),2)
        self.files.write('',content='confirmed preference',memory=True)
        self.assertIn('confirmed', (self.config.data/'memory'/'rui'/'long_term.md').read_text(encoding='utf-8'))
        self.assertNotIn('confirmed', (self.config.data/'memory'/'red'/'long_term.md').read_text(encoding='utf-8'))
    def test_exact_edit_ambiguous(self):
        p=self.workspace/'a.txt';p.write_text('x x')
        with self.assertRaises(ValueError):self.files.write(str(p),old_text='x',new_text='y')
    def test_directory_create_delete_move(self):
        ws=str(self.workspace)
        self.assertEqual(self.files.create_directory(ws+'/new folder')['status'],'created')
        (self.workspace/'new folder'/'doc.txt').write_text('data')
        out=self.files.delete_directory(ws+'/new folder')
        self.assertEqual(out['status'],'deleted');self.assertFalse((self.workspace/'new folder').exists())
        self.assertEqual(self.audit[-1][0],'rmdir')
        self.assertEqual(self.files.create_directory(ws+'/src')['status'],'created')
        (self.workspace/'src'/'doc.txt').write_text('data')
        moved=self.files.move(ws+'/src',ws+'/dest')
        self.assertEqual(moved['status'],'moved');self.assertEqual((self.workspace/'dest'/'doc.txt').read_text(),'data')
        with self.assertRaises(RuntimeError):self.files.move(ws+'/src',ws+'/dest2')
        (self.workspace/'doc.txt').write_text('f')
        self.assertEqual(self.files.move(ws+'/doc.txt',ws+'/moved.txt')['status'],'moved')
        self.files.approve=lambda *a:False
        self.assertEqual(self.files.create_directory(ws+'/nd')['status'],'denied')
        self.assertEqual(self.files.delete_directory(ws+'/dest')['status'],'denied')
        self.assertTrue((self.workspace/'dest').exists())

class StoreTests(Fixture):
    def test_interrupted_tool_is_not_replayed(self):
        sid=self.store.create('rui')
        self.store.add(sid,'assistant',[{'type':'tool_use','id':'orphan','name':'write_file','input':{}}])
        self.store.recover_interrupted_tools()
        rows=self.store.messages(sid)
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[-1]['content'][0]['tool_use_id'],'orphan')
        self.assertTrue(rows[-1]['content'][0]['is_error'])
        self.store.recover_interrupted_tools();self.assertEqual(len(self.store.messages(sid)),2)
    def test_fork_summary_and_role_isolation(self):
        sid=self.store.create('rui');self.store.add(sid,'user','one');mid=self.store.add(sid,'assistant','two')
        self.store.update(sid,summary='summary',summarized_through=mid)
        self.store.add(sid,'user','three');fork=self.store.fork(sid)
        self.assertEqual(len(self.store.messages(fork)),3)
        self.assertEqual([m['content'] for m in self.store.messages(fork,True)],['three'])
        self.assertEqual(self.store.session(fork)['parent'],sid)
        self.assertEqual(len(self.store.sessions('red')),0)
        self.store.add(fork,'assistant','branch');self.assertEqual(len(self.store.messages(sid)),3)
    def test_config_credentials(self):
        encrypted=protect('not-a-real-api-key')
        self.assertNotIn('not-a-real',encrypted);self.assertEqual(protect(encrypted,True),'not-a-real-api-key')
        self.config.value['api']['key_encrypted']=encrypted;self.config.save()
        self.assertEqual(Config(self.root).value['api']['key_encrypted'],encrypted)
    def test_extension_role_allowlist(self):
        p=self.root/'extensions'/'skills'/'test';p.mkdir(parents=True);(p/'SKILL.md').write_text('role skill')
        self.assertIn('role skill',extension_text(self.root,{'skills':['test']}))
        self.assertNotIn('role skill',extension_text(self.root,{'skills':[]}))
        with self.assertRaises(ValueError):extension_text(self.root,{'skills':['../../outside']})

class MockHandler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.seen.append((self.path,payload))
        self.send_response(200)
        self.send_header('Content-Type','text/event-stream' if payload.get('stream') else 'application/json')
        self.end_headers()
        anthropic=self.path.endswith('/messages')
        mode=self.server.mode
        if mode=='tool' and len(self.server.seen)==1:
            blocks=[{'type':'tool_use','id':'call_1','name':'write_file','input':{'path':self.server.target,'content':'made by mock'}}]
            finish='tool_use'
        elif mode=='compact':blocks=[{'type':'text','text':'摘要：保留任务与决策。'}];finish='end_turn'
        elif mode=='thinking':blocks=[{'type':'thinking','thinking':'先规划再回答。','signature':'sig123'},{'type':'text','text':'你好，测试回复。'}];finish='end_turn'
        else:blocks=[{'type':'text','text':'你好，测试回复。'}];finish='end_turn'
        if not payload.get('stream'):
            if anthropic:result={'content':blocks,'usage':{'input_tokens':20,'output_tokens':8},'stop_reason':finish}
            else:result={'choices':[{'message':{'content':'你好，测试回复。'},'finish_reason':'stop'}],'usage':{'prompt_tokens':20,'completion_tokens':8}}
            self.wfile.write(json.dumps(result,ensure_ascii=False).encode());return
        if anthropic:
            events=[{'type':'message_start','message':{'usage':{'input_tokens':20}}}]
            for i,b in enumerate(blocks):
                if b['type']=='text':
                    events.extend([{'type':'content_block_start','index':i,'content_block':{'type':'text','text':''}},
                      {'type':'content_block_delta','index':i,'delta':{'type':'text_delta','text':b['text']}}])
                elif b['type']=='thinking':
                    events.extend([{'type':'content_block_start','index':i,'content_block':{'type':'thinking','thinking':''}},
                      {'type':'content_block_delta','index':i,'delta':{'type':'thinking_delta','thinking':b['thinking']}},
                      {'type':'content_block_delta','index':i,'delta':{'type':'signature_delta','signature':b.get('signature','')}}])
                else:
                    events.extend([{'type':'content_block_start','index':i,'content_block':dict(b,input={})},
                        {'type':'content_block_delta','index':i,'delta':{'type':'input_json_delta','partial_json':json.dumps(b['input'])}}])
            events.extend([{'type':'message_delta','delta':{'stop_reason':finish},'usage':{'output_tokens':8}},{'type':'message_stop'}])
        else:
            events=[{'choices':[{'delta':{'content':'你好，测试回复。'},'finish_reason':None}]},
                    {'choices':[{'delta':{},'finish_reason':'stop'}],'usage':{'prompt_tokens':20,'completion_tokens':8}}]
        if mode=='truncated':events=events[:2]
        for event in events:self.wfile.write(('data: '+json.dumps(event,ensure_ascii=False)+'\n\n').encode())
        if not anthropic and mode!='truncated':self.wfile.write(b'data: [DONE]\n\n')

class ProviderTests(Fixture):
    def setUp(self):
        super().setUp();self.server=ThreadingHTTPServer(('127.0.0.1',0),MockHandler)
        self.server.mode='normal';self.server.seen=[]
        self.server_thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.server_thread.start()
        self.config.value['api'].update(base_url=f'http://127.0.0.1:{self.server.server_port}',model='mock-test')
    def tearDown(self):self.server.shutdown();self.server.server_close();super().tearDown()
    def test_both_protocols_stream_and_json(self):
        for protocol in ('anthropic','openai'):
            for stream in (True,False):
                api=dict(self.config.value['api'],protocol=protocol,stream=stream);deltas=[]
                blocks,usage,finish=Provider(api).complete('system',[{'role':'user','content':'hello'}],on_text=deltas.append)
                self.assertIn('你好',plain(blocks));self.assertEqual(''.join(deltas),plain(blocks));self.assertTrue(usage)
    def test_endpoint_normalization(self):
        self.assertEqual(endpoint('https://test/v1','anthropic'),'https://test/v1/messages')
        self.assertEqual(endpoint('https://test/api','openai'),'https://test/api/v1/chat/completions')
        self.assertEqual(endpoint('https://test/v1/messages','anthropic'),'https://test/v1/messages')
        with self.assertRaises(ValueError):endpoint('https://key@test','anthropic')
    def test_incomplete_stream_rejected(self):
        self.server.mode='truncated'
        with self.assertRaises(RuntimeError):Provider(self.config.value['api']).complete('s',[{'role':'user','content':'x'}])
    def test_thinking_blocks_are_captured_and_stored(self):
        self.server.mode='thinking'
        api=dict(self.config.value['api'],thinking_budget=1024)
        self.config.value['api'].update(api)
        sid=self.store.create('rui');self.store.add(sid,'user','think about it')
        Agent(self.root,self.config.snapshot(),self.store,sid)._run()
        rows=self.store.messages(sid)
        self.assertEqual(len(rows),2)
        last=rows[-1]['content']
        self.assertEqual([b['type'] for b in last],['thinking','text'])
        self.assertEqual(last[0]['thinking'],'先规划再回答。')
        self.assertEqual(last[0]['signature'],'sig123')
        # thinking block must be echoed in the next request as well
        Agent(self.root,self.config.snapshot(),self.store,sid)._run()
        self.assertIn('thinking',json.dumps(self.server.seen[-1][1],ensure_ascii=False))
    def test_agent_tool_loop_writes_with_review(self):
        self.server.mode='tool';p=self.workspace/'generated.txt';self.server.target=str(p)
        self.config.value['roles']['rui']['roots']=[{'path':str(self.workspace),'write':True}]
        sid=self.store.create('rui');self.store.add(sid,'user','create a file')
        agent=Agent(self.root,self.config.snapshot(),self.store,sid);reviews=[]
        agent.approve=lambda *args:reviews.append(args) or True
        agent._run()
        self.assertEqual(p.read_text(),'made by mock');self.assertEqual(len(reviews),1)
        self.assertEqual(len(self.server.seen),2)
        self.assertEqual(len(self.store.messages(sid)),4)
        sent=self.server.seen[1][1]['messages']
        self.assertEqual(sent[-1]['content'][0]['type'],'tool_result')
    def test_agent_denial_and_compaction_preserve_history(self):
        sid=self.store.create('rui');self.store.add(sid,'user','keep this history')
        self.server.mode='compact'
        Agent(self.root,self.config.snapshot(),self.store,sid,True)._run()
        self.assertEqual(len(self.store.messages(sid)),1)
        self.assertEqual(len(self.store.messages(sid,True)),0)
        self.assertIn('摘要',self.store.session(sid)['summary'])
    def test_slash_compact_command_intercepted(self):
        sid=self.store.create('rui');self.store.add(sid,'user','first exchange');self.store.add(sid,'assistant','first reply')
        last=self.store.add(sid,'user','/compact')
        self.server.mode='compact'
        Agent(self.root,self.config.snapshot(),self.store,sid)._run()
        s=self.store.session(sid)
        self.assertIn('摘要',s['summary'])
        self.assertEqual(s['summarized_through'],last)  # "/compact" itself is excluded from future context
        self.assertEqual(len(self.store.messages(sid)),3)
        self.assertEqual(self.store.messages(sid,True),[])
    def test_slash_compact_ignores_non_bare_command(self):
        self.assertTrue(is_compact_command('/compact'))
        self.assertTrue(is_compact_command('/ compact'))
        self.assertTrue(is_compact_command('/Compact：'))
        self.assertFalse(is_compact_command('/compact now please'))
        self.assertFalse(is_compact_command('please /compact'))
    def test_tool_conversion(self):
        m=[{'role':'assistant','content':[{'type':'tool_use','name':'read_file','id':'a','input':{'path':'p'}}]},
           {'role':'user','content':[{'type':'tool_result','tool_use_id':'a','content':'result'}]}]
        out=openai_messages('s',m)
        self.assertEqual(out[1]['tool_calls'][0]['id'],'a');self.assertEqual(out[2]['role'],'tool')

class MCPTests(Fixture):
    def test_stdio_handshake_list_call(self):
        script=self.base/'server.py'
        script.write_text('''import sys,json
for line in sys.stdin:
 o=json.loads(line)
 if 'id' not in o: continue
 m=o['method']
 if m=='initialize':r={'protocolVersion':'2024-11-05','capabilities':{'tools':{}},'serverInfo':{'name':'test','version':'1'}}
 elif m=='tools/list':r={'tools':[{'name':'echo','description':'test','inputSchema':{'type':'object'}}]}
 else:r={'content':[{'type':'text','text':o['params']['arguments']['text']}]}
 print(json.dumps({'jsonrpc':'2.0','id':o['id'],'result':r}),flush=True)
''',encoding='utf-8')
        spec={'name':'mock','command':sys.executable,'args':[str(script)],'roles':['rui'],'enabled':True}
        validate_servers([spec]);client=MCPClient(spec,threading.Event())
        try:
            self.assertEqual(client.tools()[0]['name'],'echo')
            self.assertEqual(client.call('tools/call',{'name':'echo','arguments':{'text':'works'}})['content'][0]['text'],'works')
        finally:client.close()
        self.assertIsNotNone(client.process.poll())
    def test_invalid_roles(self):
        with self.assertRaises(ValueError):validate_servers([{'name':'a','command':'x','roles':['unknown']}])

if __name__=='__main__':unittest.main()
