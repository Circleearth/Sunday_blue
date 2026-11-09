import json
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from sunday_blue.agent import Agent
from sunday_blue.storage import Config, Store
from sunday_blue.role_lifecycle import RoleLifecycle
from sunday_blue.capabilities import TurnCapabilities
from sunday_blue.personas import read_persona, save_persona

ROOT = Path(__file__).resolve().parents[1]


class WireHandler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.seen.append(body)
        anthropic = self.path.endswith('/messages')
        activate = self.server.activate and len(self.server.seen) == 1
        call = {'type':'tool_use', 'id':'load1', 'name':'activate_capability', 'input':{'capability':'skill:review'}}
        if anthropic:
            result = {'content':[call] if activate else [{'type':'text','text':'收到'}],
                      'usage':{'input_tokens':10,'output_tokens':5}, 'stop_reason':'tool_use' if activate else 'end_turn'}
        else:
            msg = {'content':'收到'}
            if activate:
                msg = {'content':None, 'tool_calls':[{'id':'load1','type':'function','function':{
                    'name':'activate_capability','arguments':'{"capability":"skill:review"}'}}]}
            result = {'choices':[{'message':msg,'finish_reason':'tool_calls' if activate else 'stop'}], 'usage':{}}
        self.send_response(200); self.send_header('Content-Type','application/json'); self.end_headers()
        self.wfile.write(json.dumps(result).encode())


class CapabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'tests', prefix='sunday-test-')
        self.root = Path(self.temp.name); self.config = Config(self.root); self.store = Store(self.config.data)
        self.service = RoleLifecycle(self.config, self.store)
        self.role = self.service.create('合成人格测试')
        before = read_persona(self.root, self.role)
        save_persona(self.root, self.role, before, {k:'MARKER_' + k for k in before})
        skill = self.root/'extensions/skills/review'; skill.mkdir(parents=True)
        (skill/'SKILL.md').write_text('LAZY_SKILL_BODY', encoding='utf-8')
        cfg = self.config.value['roles'][self.role]
        cfg['skills'] = ['review', 'review']
        cfg['capability_loading'] = {'skill:review':{'mode':'on_demand','keywords':'复盘'}}
        self.server = ThreadingHTTPServer(('127.0.0.1',0), WireHandler)
        self.server.seen = []; self.server.activate = False
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.config.value['api'].update(base_url=f'http://127.0.0.1:{self.server.server_port}', model='fixture', stream=False)

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.temp.cleanup()

    def run_turn(self, text='你好'):
        sid = self.store.create(self.role); self.store.add(sid,'user',text)
        agent = Agent(self.root,self.config.snapshot(),self.store,sid)
        agent._run()
        return sid

    def test_real_wire_persona_four_sections_once_and_updates(self):
        for protocol in ('anthropic','openai'):
            self.config.value['api']['protocol'] = protocol
            self.run_turn()
            payload = self.server.seen[-1]
            system = payload['system'] if protocol=='anthropic' else payload['messages'][0]['content']
            for key in read_persona(self.root,self.role): self.assertEqual(system.count('MARKER_'+key), 1)
            self.assertNotIn('LAZY_SKILL_BODY', system)
            self.assertIn('合成人格测试', system)
        before = read_persona(self.root,self.role)
        save_persona(self.root,self.role,before,before | {'voice.md':'NEW_VOICE_ONLY'})
        self.service.rename(self.role,'显示名已修改')
        self.run_turn()
        wire = json.dumps(self.server.seen[-1],ensure_ascii=False)
        self.assertIn('NEW_VOICE_ONLY',wire); self.assertNotIn('MARKER_voice.md',wire)
        self.assertIn('显示名已修改',wire)
        other = self.service.create('另一个角色')
        sid = self.store.create(other); self.store.add(sid,'user','你好')
        Agent(self.root,self.config.snapshot(),self.store,sid)._run()
        self.assertNotIn('NEW_VOICE_ONLY',json.dumps(self.server.seen[-1]))

    def test_semantic_activation_delivers_skill_on_next_wire_request(self):
        for protocol in ('anthropic', 'openai'):
            self.server.seen.clear(); self.server.activate = True
            self.config.value['api']['protocol'] = protocol
            sid = self.run_turn()
            self.assertEqual(len(self.server.seen), 2)
            self.assertNotIn('LAZY_SKILL_BODY', json.dumps(self.server.seen[0]))
            self.assertEqual(json.dumps(self.server.seen[1]).count('LAZY_SKILL_BODY'), 1)
            self.assertNotIn('LAZY_SKILL_BODY', json.dumps(self.store.messages(sid)))

    def test_deterministic_activation_and_no_permission_expansion(self):
        base = self.config.snapshot()
        for text in ('请复盘今天', '@skill:review 整理'):
            plan = TurnCapabilities(self.root,base,self.role,text)
            self.assertIn('skill:review',plan.active)
        plan = TurnCapabilities(self.root,base,self.role,'闲聊')
        self.assertNotIn('skill:review',plan.active)
        with self.assertRaises(PermissionError): plan.activate('files')
        with self.assertRaises(PermissionError): plan.activate('skill:ungranted')
        self.assertFalse(plan.snapshot()['features']['files'])

    def test_unloaded_plugin_code_and_context_are_not_run(self):
        folder = self.root/'extensions/plugins/custom'; folder.mkdir(parents=True)
        (folder/'plugin.json').write_text(json.dumps({'id':'custom','api_version':1,'entry':'main.py',
            'name':'Custom','version':'1','description':'test','default_enabled':True}))
        (folder/'main.py').write_text("def system_context(config): return 'PLUGIN_SENTINEL'\n")
        role = self.config.value['roles'][self.role]
        # Newly created roles do not inherit even default-enabled plugins.
        self.assertNotIn('plugin:custom',TurnCapabilities(self.root,self.config.snapshot(),self.role).catalog)
        role['native_plugins'] = {'custom':True}
        role['capability_loading']['plugin:custom'] = {'mode':'on_demand'}
        self.run_turn()
        self.assertNotIn('PLUGIN_SENTINEL',json.dumps(self.server.seen[-1]))
        self.run_turn('@plugin:custom')
        self.assertIn('PLUGIN_SENTINEL',json.dumps(self.server.seen[-1]))

    def test_capability_settings_roundtrip_and_role_scope(self):
        from PySide6.QtWidgets import QApplication
        from sunday_blue.capability_preferences import CapabilityDialog
        app = QApplication.instance() or QApplication([])
        dialog = CapabilityDialog(self.root,self.config.snapshot(),self.role)
        dialog.grants['files'].setChecked(True)
        mode, keys = dialog.rows['files']; mode.setCurrentIndex(1); keys.setText('文件,目录')
        dialog.responsibility.setPlainText('只记录，不自动规划')
        dialog.save()
        self.config.value['roles'][self.role] = dialog.value; self.config.save()
        saved = Config(self.root).value
        self.assertEqual(saved['roles'][self.role]['capability_loading']['files']['mode'],'on_demand')
        self.assertEqual(saved['roles'][self.role]['responsibility'],'只记录，不自动规划')
        self.assertNotIn('capability_loading',saved['roles']['rui'])
        dialog.deleteLater(); app.processEvents()
