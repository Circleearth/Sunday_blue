"""Portable configuration, Windows-protected credentials and durable conversations."""
from __future__ import annotations
import base64
import copy
import ctypes
import json
import os
from pathlib import Path
import sqlite3
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from .roles import RoleRegistry, list_roles, require_role, LegacyRoles, DEFAULT_ROLES, default_settings
# Compatibility exports only; runtime validation must use the installation root.
ROLES = LegacyRoles()
ROLE_IDS = {r[0] for r in DEFAULT_ROLES}

def root_path():
    return Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent.parent

def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)

def protect(value: str, decrypt=False):
    """DPAPI current-user protection. Never silently fall back to plaintext."""
    if not value:
        return ''
    if os.name != 'nt':
        raise RuntimeError('凭据加密目前仅支持 Windows DPAPI。')
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    raw = base64.b64decode(value) if decrypt else value.encode('utf-8')
    buf = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
    src, dst = Blob(len(raw), buf), Blob()
    api = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    if not api(ctypes.byref(src), None, None, None, None, 1, ctypes.byref(dst)):
        raise OSError('Windows 无法解密凭据，请在当前 Windows 账户下重新填写 API Key。')
    try:
        result = ctypes.string_at(dst.data, dst.size)
        return result.decode('utf-8') if decrypt else base64.b64encode(result).decode('ascii')
    finally:
        ctypes.windll.kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        ctypes.windll.kernel32.LocalFree(ctypes.cast(dst.data, ctypes.c_void_p))

class Config:
    def __init__(self, root=None):
        self.root = Path(root or root_path()).resolve()
        self.data = self.root / 'data'
        self.data.mkdir(parents=True, exist_ok=True)
        self.path = self.data / 'settings.json'
        self.registry = RoleRegistry(self.root)
        self.registry.initialize()
        role_ids = {r[0] for r in list_roles(self.root, include_archived=True)}
        self.value = {
            'api': {'protocol': 'anthropic', 'base_url': 'https://api.anthropic.com',
                    'model': '', 'key_encrypted': '', 'auth': 'x-api-key',
                    'max_tokens': 4096, 'context_limit': 200000, 'stream': True,
                    'thinking_budget': 0},
            'roles': {r: default_settings(r) for r in role_ids},
            'features': {'files': True, 'memory': True, 'mcp': False},
            'mcp_servers': [],
            'ui_theme': 'dark',
            'ui_display': {'font_family': 'Noto Sans SC'},
            'greetings': {'night_repeat': True, 'night_interval_minutes': 0},
            'chat_display': {},
        }
        if self.path.exists():
            loaded = json.loads(self.path.read_text(encoding='utf-8'))
            for k in ('api', 'features'):
                self.value[k].update(loaded.get(k, {}))
            for r in role_ids:
                self.value['roles'][r].update(loaded.get('roles', {}).get(r, {}))
            self.value['mcp_servers'] = loaded.get('mcp_servers', [])
            self.value['last_role'] = loaded.get('last_role', 'rui')
            self.value['active_sessions'] = loaded.get('active_sessions', {})
            self.value['ui_theme'] = loaded.get('ui_theme', 'dark')
            self.value['main_page'] = loaded.get('main_page', 'focus')
            self.value['ui_display'].update(loaded.get('ui_display', {}))
            self.value['close_to_tray'] = loaded.get('close_to_tray', False)
            self.value['chat_display'] = loaded.get('chat_display', {})
            self.value['greetings'].update(loaded.get('greetings', {}))
        for role in role_ids:
            p = self.data / 'memory' / role / 'long_term.md'
            p.parent.mkdir(parents=True, exist_ok=True)
            if not p.exists():
                p.write_text(f'# {role} · 持久记忆\n\n暂无已确认的用户事实。\n', encoding='utf-8')

    def save(self, value=None):
        if value is not None:value={k:v for k,v in value.items() if k!='_plugin_root'}
        target = value if value is not None else self.value
        valid = {r[0] for r in list_roles(self.root, include_archived=True)}
        target['roles'] = {r: target.get('roles', {}).get(r, default_settings(r)) for r in valid}
        target['active_sessions'] = {r:s for r,s in target.get('active_sessions', {}).items() if r in valid}
        for spec in target.get('mcp_servers', []):
            spec['roles'] = [r for r in spec.get('roles', []) if r in valid]
        fonts = target.get('chat_display', {}).get('role_fonts', {})
        for r in list(fonts):
            if r not in valid: del fonts[r]
        atomic_json(self.path, value if value is not None else self.value)
        if value is not None:
            self.value = copy.deepcopy(value)

    def snapshot(self):
        return copy.deepcopy(self.value) | {'_plugin_root':str(self.root)}


class Store:
    def __init__(self, data):
        self.path = Path(data) / 'conversations.sqlite3'
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY, role TEXT NOT NULL, title TEXT NOT NULL,
                    created TEXT, updated TEXT, parent TEXT,
                    summary TEXT DEFAULT '', summarized_through INTEGER DEFAULT 0,
                    usage TEXT DEFAULT '{}');
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, session TEXT NOT NULL,
                    role TEXT NOT NULL, content TEXT NOT NULL, created TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS session_messages ON messages(session,id);
                CREATE TABLE IF NOT EXISTS audit (
                    id INTEGER PRIMARY KEY, at TEXT, role TEXT, session TEXT, action TEXT, detail TEXT);
            ''')
            try:
                db.execute('ALTER TABLE sessions ADD COLUMN archived INTEGER NOT NULL DEFAULT 0')
            except sqlite3.OperationalError:
                pass  # column already present in newer databases

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self, role, title='新对话', parent=None):
        require_role(self.path.parent.parent, role)
        sid = str(uuid.uuid4())
        with self.connect() as db:
            db.execute('INSERT INTO sessions(id,role,title,created,updated,parent) VALUES(?,?,?,?,?,?)',
                       (sid, role, title, now(), now(), parent))
        return sid

    def session(self, sid):
        with self.connect() as db:
            row = db.execute('SELECT * FROM sessions WHERE id=?', (sid,)).fetchone()
        return dict(row) if row else None

    def sessions(self, role, include_archived=False):
        sql = 'SELECT * FROM sessions WHERE role=?'
        if not include_archived:
            sql += ' AND COALESCE(archived,0)=0'
        with self.connect() as db:
            return [dict(r) for r in db.execute(sql + ' ORDER BY updated DESC', (role,))]

    def add(self, sid, role, content):
        with self.connect() as db:
            cur = db.execute('INSERT INTO messages(session,role,content,created) VALUES(?,?,?,?)',
                             (sid, role, json.dumps(content, ensure_ascii=False), now()))
            db.execute('UPDATE sessions SET updated=? WHERE id=?', (now(), sid))
            return cur.lastrowid

    def messages(self, sid, context=False):
        session = self.session(sid)
        after = session['summarized_through'] if context else 0
        with self.connect() as db:
            rows = db.execute('SELECT * FROM messages WHERE session=? AND id>? ORDER BY id', (sid, after)).fetchall()
        return [dict(r) | {'content': json.loads(r['content'])} for r in rows]

    def message_page(self,sid,limit=20,day=None,before=None):
        """Display-only bounded query. Agent context still uses messages(context=True)."""
        limit=max(1,min(int(limit),100));where='session=?';args=[sid]
        if day is not None:
            from datetime import date
            date.fromisoformat(day);where+=" AND substr(created,1,10)=?";args.append(day)
        if before is not None:where+=' AND id<?';args.append(int(before))
        with self.connect() as db:rows=db.execute('SELECT * FROM messages WHERE '+where+' ORDER BY id DESC LIMIT ?',(*args,limit+1)).fetchall()
        more=len(rows)>limit
        return [dict(r)|{'content':json.loads(r['content'])} for r in reversed(rows[:limit])],more

    def message_days(self,sid):
        with self.connect() as db:return [(r[0],r[1]) for r in db.execute('SELECT substr(created,1,10),count(*) FROM messages WHERE session=? GROUP BY substr(created,1,10) ORDER BY 1 DESC',(sid,))]

    def context_characters(self,sid,after=0):
        with self.connect() as db:
            marker=tuple(db.execute('SELECT max(id),count(*) FROM messages WHERE session=? AND id>?',(sid,after)).fetchone())
            key=(sid,after,marker)
            cached=getattr(self,'_display_length_cache',{})
            if key not in cached:
                value=db.execute('SELECT COALESCE(sum(length(content)),0) FROM messages WHERE session=? AND id>?',(sid,after)).fetchone()[0]
                self._display_length_cache={key:value};return value
            return cached[key]

    def update(self, sid, **values):
        allowed = {'title', 'summary', 'summarized_through', 'usage'}
        if not values or not set(values) <= allowed:
            raise ValueError('无效会话字段')
        with self.connect() as db:
            db.execute('UPDATE sessions SET ' + ','.join(k+'=?' for k in values) + ' WHERE id=?', (*values.values(), sid))

    def fork(self, sid):
        old = self.session(sid)
        new = self.create(old['role'], old['title'] + ' · 分支', sid)
        cursor = 0
        for msg in self.messages(sid):
            copied = self.add(new, msg['role'], msg['content'])
            if msg['id'] <= old['summarized_through']:
                cursor = copied
        self.update(new, summary=old['summary'], summarized_through=cursor, usage=old['usage'])
        return new

    def archive(self, sid, archived=True):
        with self.connect() as db:
            db.execute('UPDATE sessions SET archived=? WHERE id=?', (1 if archived else 0, sid))

    def delete(self, sid):
        """Remove transcript and source queue; already extracted role memories stay.
        Cleanup errors propagate before deleting the transcript, allowing retry.
        Whole-role removal is owned by RoleLifecycle, never this method.
        """
        session = self.session(sid)
        from .living_memory import close_role
        if session: close_role(self.path.parent.parent, session['role'])
        self._purge_plugin_session_data(session['role'] if session else None, sid)
        with self.connect() as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='role_events'").fetchone():
                db.execute('UPDATE role_events SET source_session=NULL,source_message=NULL WHERE source_session=?',(sid,))
            db.execute('DELETE FROM messages WHERE session=?', (sid,))
            db.execute('DELETE FROM audit WHERE session=?', (sid,))
            db.execute('DELETE FROM sessions WHERE id=?', (sid,))
        if session:
            self.audit(session['role'], sid, 'delete_session', 'Session permanently deleted from all stores.')

    def _purge_plugin_session_data(self, role, sid):
        """Only known source tables; do not guess upstream memory table layouts."""
        def purge(db_path, specs):
            if not db_path.exists():
                return
            db = sqlite3.connect(str(db_path), timeout=15)
            try:
                for table, column in specs:
                    cols = [r[1] for r in db.execute('PRAGMA table_info("%s")' % table).fetchall()] if \
                        db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() else []
                    if column in cols:
                        db.execute('DELETE FROM "%s" WHERE "%s"=?' % (table, column), (sid,))
                db.commit()
            finally:
                db.close()
        plugins_dir = Path(self.path).parent / 'plugins'
        purge(plugins_dir / 'daypart-greetings' / 'state.sqlite3', (('events', 'session'), ('triggers', 'session')))
        if role:
            brain_dir = plugins_dir / 'livingmemory' / role
            purge(brain_dir / 'inbox.sqlite3', (('turns', 'session'),))

    def withdraw_turn(self,sid,message_id):
        """Called only once the worker has finished. Preserve withdrawn text in audit."""
        with self.connect() as db:
            row=db.execute('SELECT * FROM messages WHERE session=? AND id=?',(sid,message_id)).fetchone()
            if not row or row['role']!='user' or not isinstance(json.loads(row['content']),str):return ''
            rows=[dict(r) for r in db.execute('SELECT * FROM messages WHERE session=? AND id>=?',(sid,message_id))]
            role=self.session(sid)['role']
            db.execute('INSERT INTO audit(at,role,session,action,detail) VALUES(?,?,?,?,?)',
                (now(),role,sid,'withdraw_turn',json.dumps(rows,ensure_ascii=False)))
            db.execute('DELETE FROM messages WHERE session=? AND id>=?',(sid,message_id))
            db.execute("UPDATE sessions SET summary='',summarized_through=0 WHERE id=? AND summarized_through>=?",(sid,message_id))
            db.execute("UPDATE sessions SET usage='{}',updated=? WHERE id=?",(now(),sid))
            return json.loads(row['content'])

    def recover_interrupted_tools(self):
        """On application startup, do not replay operations with uncertain results."""
        with self.connect() as db:
            sessions = [r['id'] for r in db.execute('SELECT id FROM sessions')]
        for sid in sessions:
            messages = self.messages(sid)
            if not messages or messages[-1]['role'] != 'assistant':
                continue
            last = messages[-1]['content']
            if not isinstance(last, list):
                continue
            calls = [b for b in last if b.get('type') == 'tool_use']
            if calls:
                self.add(sid, 'user', [{'type': 'tool_result', 'tool_use_id': b['id'], 'is_error': True,
                    'content': '软件在工具回执保存前中断，执行结果未知。必须先检查实际状态，禁止盲目重复写入或外部操作。'} for b in calls])
                self.audit(self.session(sid)['role'], sid, 'interrupted_tools', 'Unknown outcome; no automatic replay.')

    def audit(self, role, sid, action, detail):
        with self.connect() as db:
            db.execute('INSERT INTO audit(at,role,session,action,detail) VALUES(?,?,?,?,?)',
                       (now(), role, sid, action, detail))

def plain(content):
    if isinstance(content, str):
        return content
    return '\n'.join(b.get('text', '') for b in content if b.get('type') == 'text')
