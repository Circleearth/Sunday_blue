"""One loopback memory service per role. Never imports the AstrBot application."""
import asyncio
from datetime import datetime
import json
import logging
from pathlib import Path
import secrets
import sqlite3
import sys
from types import SimpleNamespace

PLUGIN = Path(__file__).resolve().parent
ROOT = Path(sys.argv[1]).resolve()
ROLE = sys.argv[2]
sys.path.insert(0, str(ROOT))
from sunday_blue.storage import ROLE_IDS, atomic_json
if ROLE not in ROLE_IDS:
    raise ValueError('Unknown role')
DATA = ROOT / 'data/plugins/livingmemory' / ROLE
DATA.mkdir(parents=True, exist_ok=True)
logging.basicConfig(filename=str(DATA / 'service.log'), level=logging.WARNING,
                    encoding='utf-8', format='%(asctime)s %(levelname)s %(message)s')
from compat import install
install(PLUGIN / 'vendor')
from providers import ChatProvider, OllamaEmbedding
from livingmemory.core.base.config_manager import ConfigManager
from livingmemory.core.plugin_initializer import PluginInitializer
from livingmemory.core.models.conversation_models import Message
from livingmemory.core.page_api import PluginPageApi
from livingmemory.core.utils.formatting import format_memories_for_injection
from livingmemory.core.prompts.prompt_manager import init_prompt_manager
from livingmemory.core.i18n_backend import init as init_i18n
from quart import Quart, request, abort, send_from_directory, make_response
from hypercorn.asyncio import serve
from hypercorn.config import Config as ServerConfig

TOKEN = sys.stdin.readline().strip()
if len(TOKEN) < 32:
    raise ValueError('Missing process capability')
app = Quart(__name__, static_folder=None)
app.config['MAX_CONTENT_LENGTH'] = 4 * 1024 * 1024
guard = asyncio.Lock()
stop = asyncio.Event()
last_error = ''


class SavedConfig(dict):
    def save_config(self):
        atomic_json(DATA / 'engine-config.json', self)


class Context:
    def __init__(self, chat, embedding):
        self.chat, self.embedding = chat, embedding
        self.provider_manager = SimpleNamespace(inst_map={'sunday-chat': chat, 'sunday-ollama': embedding})
        self.platform_manager = SimpleNamespace(get_insts=lambda: [])
        self.persona_manager = self

    def get_config(self):
        return {'platform': [{'id': ROLE, 'type': 'sunday'}]}

    def get_provider_by_id(self, pid):
        return self.provider_manager.inst_map.get(pid)

    def get_all_embedding_providers(self):
        return [self.embedding]

    def get_all_providers(self):
        return [self.chat]

    async def get_using_provider_async(self, umo=None):
        return self.chat

    async def get_persona(self, persona_id):
        parts = []
        for name in ('identity.md', 'personality.md', 'voice.md', 'relationships.md'):
            path = ROOT / 'personas' / ROLE / name
            if path.exists():
                parts.append(path.read_text(encoding='utf-8'))
        return SimpleNamespace(system_prompt='\n'.join(parts))

    def register_web_api(self, path, callback, methods, description):
        suffix = path.split('/page/', 1)[1]
        async def handle():
            async with guard:
                return await callback()
        app.add_url_rule('/page/' + suffix, description, handle, methods=methods)


class Plugin:
    async def _ensure_plugin_ready(self):
        return (self.initializer.is_initialized, self.initializer.error_message or '')


plugin = Plugin()


@app.before_request
async def authenticate():
    if request.host.split(':')[0] != '127.0.0.1':
        abort(403)
    origin = request.headers.get('Origin')
    if origin and origin != 'http://' + request.host:
        abort(403)
    credential = request.headers.get('X-Sunday-Token') or request.cookies.get('sunday_memory')
    if request.path == '/dashboard/' and request.args.get('token') == TOKEN:
        return None
    if not credential or not secrets.compare_digest(credential, TOKEN):
        abort(403)


@app.after_request
async def headers(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    return response


@app.get('/dashboard/')
async def dashboard():
    html = (PLUGIN / 'vendor/livingmemory/pages/dashboard/index.html').read_text(encoding='utf-8')
    html = html.replace('<head>', '<head><script src="/bridge.js"></script>', 1)
    response = await make_response(html)
    response.set_cookie('sunday_memory', TOKEN, httponly=True, samesite='Strict')
    return response


@app.get('/dashboard/<path:filename>')
async def assets(filename):
    return await send_from_directory(PLUGIN / 'vendor/livingmemory/pages/dashboard', filename)


@app.get('/bridge.js')
async def bridge():
    # The temporary URL token becomes an HttpOnly cookie; remove it from history.
    content = (PLUGIN / 'bridge.js').read_text(encoding='utf-8').replace('__ROLE__', json.dumps(ROLE))
    return content, 200, {'Content-Type': 'application/javascript'}


@app.get('/status')
async def status():
    from sunday_blue.living_memory import pending_count
    return {'ready': plugin.initializer.is_initialized, 'role': ROLE,
            'pending': pending_count(ROOT, ROLE), 'error': last_error, 'upstream': '2.9.1'}


@app.post('/recall')
async def recall():
    body = await request.get_json()
    async with guard:
        found = await plugin.initializer.memory_engine.search_memories(
            str(body.get('query', ''))[:12000], k=max(1, min(15, int(body.get('count', 5)))), persona_id=ROLE)
        text = format_memories_for_injection(found, max_chars=max(500, min(20000, int(body.get('chars', 6000)))))
        return {'text': text, 'count': len(found)}


async def reflect(force=False):
    global last_error
    from sunday_blue.living_memory import queue_connect
    from sunday_blue.storage import Config
    from sunday_blue.plugin_runtime import parameters
    settings = parameters(Config(ROOT).snapshot(), ROLE, 'livingmemory', ROOT)
    threshold = max(1, min(50, int(settings.get('reflection_turns', 4))))
    with queue_connect(ROOT, ROLE) as db:
        rows = db.execute('SELECT * FROM turns WHERE done=0 ORDER BY id LIMIT 50').fetchall()
    if not rows or (not force and len(rows) < threshold):
        return {'processed': 0}
    rows = rows[:threshold]
    messages = []
    for row in rows:
        for item in json.loads(row['messages']):
            messages.append(Message(id=item['id'], session_id=row['session'], role=item['role'],
                                    content=item['content'], sender_id=ROLE if item['role']=='assistant' else 'owner',
                                    sender_name=ROLE if item['role']=='assistant' else '主人',
                                    timestamp=datetime.fromisoformat(item['created']).timestamp(), platform='sunday'))
    job = ','.join(str(r['id']) for r in rows)
    engine = plugin.initializer.memory_engine
    async with guard:
        # Recover the commit/cursor gap after a process interruption, without duplication.
        async with engine.db_connection.execute(
                "SELECT id, json_extract(metadata,'$.sunday_committed') AS committed "
                "FROM documents WHERE json_extract(metadata,'$.sunday_job')=?", (job,)) as cursor:
            existing = await cursor.fetchone()
        if existing and not existing['committed']:
            await engine.delete_memory(existing['id'])
            existing = None
        if not existing:
            processor = plugin.initializer.memory_processor
            content, metadata, importance = await processor.process_conversation(messages, persona_id=ROLE)
            metadata.update(sunday_job=job, adapter_id=ROLE, source='Sunday Blue automatic reflection',
                            verified_by_user=False)
            atoms = processor.classify_atoms_from_metadata(metadata, importance, persona_id=ROLE)
            memory_id = await engine.add_memory(content, persona_id=ROLE, importance=importance,
                                                metadata=metadata, atoms=atoms,
                                                source_messages=[m.to_dict() for m in messages])
            async with engine._db_write_lock:
                await engine.db_connection.execute(
                    "UPDATE documents SET metadata=json_set(metadata,'$.sunday_committed',1) WHERE id=?",
                    (memory_id,))
                await engine.db_connection.commit()
        with queue_connect(ROOT, ROLE) as db:
            db.executemany('UPDATE turns SET done=1 WHERE id=?', [(r['id'],) for r in rows])
    last_error = ''
    return {'processed': len(rows)}


@app.post('/reflect')
async def reflect_now():
    try:
        return await reflect(force=True)
    except Exception as exc:
        global last_error
        last_error = str(exc)
        return {'error': last_error}, 503


@app.post('/shutdown')
async def shutdown():
    stop.set()
    return {'ok': True}


async def background():
    global last_error
    while not stop.is_set():
        await asyncio.sleep(5)
        try:
            from sunday_blue.native_plugins import enabled
            from sunday_blue.storage import Config
            if enabled(Config(ROOT).snapshot(), ROLE, 'livingmemory'):
                await reflect()
        except Exception as exc:
            last_error = str(exc)
            # Do not hammer a failed provider repeatedly in a short interval.
            await asyncio.sleep(55)


async def watch_parent():
    # A crashed desktop must not leave nine invisible memory services behind.
    import ctypes
    import os
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x100000, False, os.getppid())
    if not handle:
        return
    try:
        while not stop.is_set():
            if kernel.WaitForSingleObject(handle, 0) == 0:
                stop.set()
                return
            await asyncio.sleep(2)
    finally:
        kernel.CloseHandle(handle)


async def main():
    from sunday_blue.living_memory import OLLAMA_URL, EMBEDDING_MODEL
    embedding = OllamaEmbedding(OLLAMA_URL, EMBEDDING_MODEL)
    await embedding.get_embedding('Sunday Blue 向量模型连接检测')
    contract_path = DATA / 'embedding.json'
    contract = {'model': EMBEDDING_MODEL, 'dimension': embedding.get_dim()}
    if contract_path.exists() and json.loads(contract_path.read_text()) != contract:
        raise RuntimeError('向量模型与原索引不一致，请先重建索引。')
    atomic_json(contract_path, contract)
    saved = DATA / 'engine-config.json'
    raw = SavedConfig(json.loads(saved.read_text(encoding='utf-8')) if saved.exists() else {})
    raw['provider_settings'] = {'embedding_provider_id': 'sunday-ollama', 'llm_provider_id': 'sunday-chat'}
    plugin.config_manager = ConfigManager(raw)
    plugin.context = Context(ChatProvider(ROOT), embedding)
    init_i18n('zh')
    init_prompt_manager(str(DATA))
    plugin.initializer = PluginInitializer(plugin.context, plugin.config_manager, str(DATA))
    plugin.initializer.embedding_provider = embedding
    plugin.initializer.llm_provider = plugin.context.chat
    await plugin.initializer._complete_initialization()
    PluginPageApi(plugin).register_routes()
    config = ServerConfig()
    config.bind = ['127.0.0.1:0']
    config.accesslog = None
    # Reserve the actual listening socket before publishing the address.
    sockets = config.create_sockets()
    port = sockets.insecure_sockets[0].getsockname()[1]
    from hypercorn.asyncio.run import worker_serve
    from hypercorn.utils import wrap_app
    task = asyncio.create_task(background())
    parent_task = asyncio.create_task(watch_parent())
    print(json.dumps({'port': port, 'role': ROLE}), flush=True)
    try:
        await worker_serve(wrap_app(app, config.wsgi_max_body_size, 'asgi'), config,
                           sockets=sockets, shutdown_trigger=stop.wait)
    finally:
        task.cancel()
        parent_task.cancel()
        await asyncio.gather(task, parent_task, return_exceptions=True)
        await plugin.initializer.stop_background_tasks()
        await plugin.initializer._teardown_partial_init()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=True), flush=True)
        sys.exit(1)
