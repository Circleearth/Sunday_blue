"""LivingMemory process boundary, durable turn inbox and manual Ollama ownership."""
import atexit
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from contextlib import contextmanager
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import threading
import time
import requests
from .storage import ROLE_IDS, plain

OLLAMA_URL = 'http://127.0.0.1:11435'
EMBEDDING_MODEL = 'bge-m3:latest'
_lock = threading.RLock()
_brains = {}
_ollama = None
_readers = ThreadPoolExecutor(max_workers=9, thread_name_prefix='memory-start')


@contextmanager
def queue_connect(root, role):
    if role not in ROLE_IDS:
        raise ValueError('未知记忆角色')
    path = Path(root) / 'data/plugins/livingmemory' / role / 'inbox.sqlite3'
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    try:
        with db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('''CREATE TABLE IF NOT EXISTS turns (
                id INTEGER PRIMARY KEY, session TEXT NOT NULL, user_id INTEGER NOT NULL,
                messages TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0,
                UNIQUE(session,user_id))''')
            yield db
    finally:
        db.close()


def enqueue(root, role, sid, user_id, messages):
    # Only real user text and completed assistant prose enter reflection.
    selected = []
    for item in messages:
        if item['role'] == 'user' and not isinstance(item['content'], str):
            continue
        text = plain(item['content']).strip()
        if text:
            selected.append({k: item[k] for k in ('id', 'role', 'created')} | {'content': text})
    if not any(m['role']=='assistant' for m in selected):
        return
    with queue_connect(root, role) as db:
        db.execute('INSERT OR IGNORE INTO turns(session,user_id,messages) VALUES(?,?,?)',
                   (sid, user_id, json.dumps(selected, ensure_ascii=False)))


def pending_count(root, role):
    with queue_connect(root, role) as db:
        return db.execute('SELECT count(*) FROM turns WHERE done=0').fetchone()[0]


def ollama_status():
    try:
        response = requests.get(OLLAMA_URL + '/api/tags', timeout=(1, 2), allow_redirects=False)
        response.raise_for_status()
        names = [m['name'] for m in response.json()['models']]
        return {'online': True, 'model_ready': EMBEDDING_MODEL in names, 'models': names,
                'owned': _ollama is not None and _ollama.poll() is None}
    except (requests.RequestException, ValueError, KeyError):
        return {'online': False, 'model_ready': False, 'models': [], 'owned': False}


def start_ollama(root):
    """Called only by the explicit start button (or explicit integration tests)."""
    global _ollama
    with _lock:
        state = ollama_status()
        if state['online']:
            if not state['owned']:
                raise RuntimeError('独立端口 11435 已被其他服务占用；不会接管或停止它。')
            return state
        directory = Path(root) / 'runtime/ollama'
        executable = directory / 'ollama.exe'
        if not executable.is_file():
            raise RuntimeError('缺少 runtime/ollama/ollama.exe，请按安装说明放入独立 Ollama。')
        env = os.environ.copy()
        env.update(OLLAMA_HOST='127.0.0.1:11435', OLLAMA_MODELS=str(directory / 'models'))
        logfile = Path(root) / 'data/plugins/livingmemory/ollama.log'
        logfile.parent.mkdir(parents=True, exist_ok=True)
        with logfile.open('ab') as log:
            _ollama = subprocess.Popen([str(executable), 'serve'], cwd=directory, env=env,
                                      stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
    for _ in range(40):
        if _ollama.poll() is not None:
            raise RuntimeError('独立 Ollama 启动失败，请检查本软件的 ollama.log。')
        state = ollama_status()
        if state['online']:
            return state
        time.sleep(.25)
    raise RuntimeError('Ollama 启动超时；可点击检测状态。')


def stop_ollama():
    global _ollama
    with _lock:
        for brain in list(_brains.values()):
            brain.close()
        _brains.clear()
        if _ollama is not None:
            if _ollama.poll() is None:
                # Terminate only the process tree started by this application.
                subprocess.run(['taskkill', '/PID', str(_ollama.pid), '/T', '/F'],
                               capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                _ollama.wait(timeout=10)
            _ollama = None
    return ollama_status()


class Brain:
    def __init__(self, root, role):
        self.token = secrets.token_urlsafe(40)
        runtime = root / 'runtime/livingmemory/Scripts/python.exe'
        if not runtime.is_file():
            raise RuntimeError('记忆运行环境未安装，请运行 scripts/setup_livingmemory.ps1。')
        log_path = root / 'data/plugins/livingmemory' / role / 'worker-stderr.log'
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open('ab') as log:
            self.process = subprocess.Popen(
                [str(runtime), str(root / 'extensions/plugins/livingmemory/worker.py'), str(root), role],
                cwd=root, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log,
                text=True, encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW)
        self.process.stdin.write(self.token + '\n')
        self.process.stdin.flush()
        try:
            line = _readers.submit(self.process.stdout.readline).result(timeout=150)
            result = json.loads(line)
            if 'error' in result:
                raise RuntimeError(result['error'])
            self.url = 'http://127.0.0.1:' + str(int(result['port']))
        except Exception:
            self.process.kill()
            self.process.wait(timeout=10)
            raise

    def call(self, path, body=None, timeout=150):
        try:
            response = requests.request('GET' if body is None else 'POST', self.url + path,
                                        headers={'X-Sunday-Token': self.token}, json=body,
                                        timeout=(3, timeout), allow_redirects=False)
            if response.status_code >= 300:
                raise RuntimeError('记忆服务失败（HTTP %s），请查看记忆状态。' % response.status_code)
            return response.json()
        except requests.RequestException:
            raise RuntimeError('记忆服务连接中断或超时；聊天仍可继续。') from None

    def close(self):
        if self.process.poll() is None:
            try:
                self.call('/shutdown', {}, timeout=3)
                self.process.wait(timeout=15)
            except Exception:
                self.process.kill()
                self.process.wait(timeout=5)


def get_brain(root, role):
    if role not in ROLE_IDS:
        raise ValueError('未知记忆角色')
    root = Path(root).resolve()
    state = ollama_status()
    if not state['online'] or not state['model_ready']:
        raise RuntimeError('记忆暂未启用：请手动启动独立 Ollama，并确认 bge-m3 模型已安装。')
    key = (str(root), role)
    with _lock:
        brain = _brains.get(key)
        if brain is None or brain.process.poll() is not None:
            brain = _brains[key] = Brain(root, role)
        return brain


def close_all():
    try:
        stop_ollama()
    except Exception:
        pass


atexit.register(close_all)
