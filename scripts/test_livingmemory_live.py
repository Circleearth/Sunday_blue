"""Explicit integration check: real local embeddings + upstream engine, isolated data.

Default uses a local deterministic chat fixture. --live-chat makes one or more
paid summary calls through the configured Sunday Blue API, using synthetic text.
No user conversations, existing memories, or AstrBot credentials are read.
"""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sunday_blue.storage import Config, Store
from sunday_blue.living_memory import start_ollama, stop_ollama, ollama_status, enqueue, Brain, _brains, get_brain


class Fixture(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass
    def do_POST(self):
        self.rfile.read(int(self.headers['Content-Length']))
        memory = {'summary': '主人喜欢晴栀牌桂花乌龙茶，不加糖。', 'topics': ['饮品偏好'],
                  'key_facts': ['主人喜欢晴栀牌桂花乌龙茶', '主人喝茶不加糖'],
                  'sentiment': 'positive', 'importance': .85}
        body = json.dumps({'choices': [{'message': {'content': json.dumps(memory, ensure_ascii=False)},
                                       'finish_reason': 'stop'}]}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def launch(root, role):
    brain = object.__new__(Brain)
    import secrets
    brain.token = secrets.token_urlsafe(40)
    brain.process = subprocess.Popen(
        [str(ROOT / 'runtime/livingmemory/Scripts/python.exe'),
         str(ROOT / 'extensions/plugins/livingmemory/worker.py'), str(root), role],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW)
    brain.process.stdin.write(brain.token + '\n')
    brain.process.stdin.flush()
    from sunday_blue.living_memory import _readers
    line = _readers.submit(brain.process.stdout.readline).result(timeout=150)
    result = json.loads(line)
    if 'error' in result:
        brain.process.kill()
        brain.process.wait()
        raise RuntimeError(result['error'])
    brain.url = 'http://127.0.0.1:' + str(result['port'])
    _brains[(str(root.resolve()), role)] = brain
    return brain


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live-chat', action='store_true')
    parser.add_argument('--preview', action='store_true')
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', 0), Fixture)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    # Reuse an existing endpoint for embeddings without adopting or stopping it.
    owned=not ollama_status()['online']
    if owned:start_ollama(ROOT)
    try:
        with tempfile.TemporaryDirectory(prefix='sunday-test-lmem-', dir=ROOT/'tests') as temp:
            root = Path(temp)
            shutil.copytree(ROOT/'sunday_blue', root/'sunday_blue', ignore=shutil.ignore_patterns('__pycache__'))
            plugin_dir=root/'extensions/plugins/livingmemory';plugin_dir.mkdir(parents=True)
            for name in ('plugin.json','main.py','_conf_schema.json'):shutil.copyfile(ROOT/'extensions/plugins/livingmemory'/name,plugin_dir/name)
            config = Config(root)
            config.value['roles']['rui'].setdefault('native_plugins',{})['livingmemory']=True
            if args.live_chat:
                config.value['api'] = Config(ROOT).value['api'].copy()
            else:
                config.value['api'].update(protocol='openai', stream=False,
                                           base_url='http://127.0.0.1:'+str(server.server_port), model='fixture')
            config.save()
            store = Store(config.data)
            sid = store.create('rui')
            uid = store.add(sid, 'user', '请记住：我最喜欢晴栀牌桂花乌龙茶，喝茶不加糖。')
            store.add(sid, 'assistant', [{'type': 'text', 'text': '好，我记住这个饮茶偏好了。'}])
            enqueue(root, 'rui', sid, uid, store.messages(sid))
            enqueue(root, 'rui', sid, uid, store.messages(sid))
            target=root/'data/plugins/livingmemory/rui/engine-config.json'
            target.parent.mkdir(parents=True,exist_ok=True)
            if not target.exists():target.write_text(json.dumps({'filtering_settings':{'memory_scope_mode':'user'}}),encoding='utf-8')
            rui = launch(root, 'rui')
            red = launch(root, 'red')
            try:
                state=rui.call('/status');assert state['pending'] == 1, 'duplicate inbox'
                assert state['scope']=='livingmemory:user:sunday:owner',state
                assert rui.call('/page/stats')['data']['total_memories']==0,'below-threshold data was written early'
                for n in range(3):
                    new_id=store.add(sid,'user','补充确认：喝茶不加糖，喜欢桂花乌龙。'+str(n))
                    store.add(sid,'assistant','记下了，保留这一真实偏好。')
                    enqueue(root,'rui',sid,new_id,store.messages(sid)[-2:])
                deadline=time.monotonic()+120
                while rui.call('/status')['pending'] and time.monotonic()<deadline:time.sleep(1)
                assert rui.call('/status')['pending']==0,rui.call('/status')
                assert rui.call('/reflect',{},timeout=30)['processed']==0,'automatic batch was not consumed'
                recalled = rui.call('/recall', {'query': '我喜欢喝什么茶？加糖吗？'})
                assert '乌龙' in recalled['text'] and '糖' in recalled['text'], recalled
                assert red.call('/recall', {'query':'桂花乌龙茶'})['count'] == 0, 'cross-role leakage'
                stats = rui.call('/page/stats')['data']
                assert stats['total_memories'] == 1, stats
                assert stats['atom_count'] >= 1 and stats['graph_nodes'] >= 1, stats
                import requests
                assert requests.get(rui.url+'/page/stats', timeout=3).status_code == 403
                assert requests.get(rui.url+'/page/stats', headers={'X-Sunday-Token': rui.token,
                                    'Origin':'https://example.com'}, timeout=3).status_code == 403
                assert rui.call('/reflect', {})['processed'] == 0
                assert rui.call('/page/config')['status'] == 'ok'
                assert rui.call('/page/graph/overview')['status'] == 'ok'
                if args.preview:
                    preview(rui, root)
                rui.close()
                rui = launch(root, 'rui')
                assert '乌龙' in rui.call('/recall', {'query':'喜欢什么茶'})['text']
                print(json.dumps({'ok':True,'chat':'real API' if args.live_chat else 'local fixture',
                      'embedding':'real Ollama bge-m3', 'memory_count':stats['total_memories'],
                      'atoms':stats['atom_count'],'graph_nodes':stats['graph_nodes'],
                      'checks':['automatic threshold=4','user scope','reflection','recall','role isolation','idempotency','restart persistence',
                                'dashboard APIs','unauthenticated rejection','cross-origin rejection']}, ensure_ascii=True))
            finally:
                rui.close()
                red.close()
                _brains.clear()
    finally:
        if owned:stop_ollama()
        server.shutdown()


def preview(brain, root):
    from PySide6.QtWidgets import QApplication
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from sunday_blue.memory_preferences import MemoryPanel, _windows
    from sunday_blue.theme import style_for
    app = QApplication.instance() or QApplication([])
    panel = MemoryPanel(root, config=Config(root))
    panel.setStyleSheet(style_for('dark'))
    panel.show()
    panel.open_dashboard()
    until = time.monotonic()+12
    while time.monotonic()<until:
        app.processEvents()
        time.sleep(.02)
    assert _windows, 'Dashboard window did not open'
    dialog = _windows[-1]
    view = dialog.findChild(QWebEngineView)
    assert view and '/dashboard/' in view.url().toString()
    dialog.grab().save(str(ROOT/'docs/livingmemory-preview.png'))
    dialog.close()
    panel.close()
    panel.deleteLater()
    app.processEvents()


if __name__ == '__main__':
    main()
