"""Controlled shared records. Suggestions never silently become confirmed facts.

This is a ledger and a small state machine, not an automatic planner/scheduler.
Only the user-facing editor may grant readers. Tools cannot grant themselves access.
"""
import hashlib
import json
import uuid
from .roles import require_role
from .storage import now

KINDS = {'original':'用户原始记录', 'inference':'AI 推断（未确认）',
         'decision':'已确认决定', 'task':'已创建待办'}
SCHEMAS = [
    {'name':'event_list', 'description':'读取本角色的记录和用户明确共享的记录。区分原始记录、推断、决定和任务；不要重复规划已有任务。',
     'input_schema':{'type':'object','properties':{}}},
    {'name':'event_record', 'description':'保存本轮用户原文，或关联这条原文的一条未确认推断。原文由程序取本轮实际消息，不能伪造。',
     'input_schema':{'type':'object','properties':{'kind':{'type':'string','enum':['original','inference']},'body':{'type':'string'}},'required':['kind']}},
    {'name':'event_derive', 'description':'依据可读事件提出决定或待办。程序必须向用户确认后才保存；同一来源事件只能创建一个决定和一个待办。',
     'input_schema':{'type':'object','properties':{'event_id':{'type':'string'},'kind':{'type':'string','enum':['decision','task']},'body':{'type':'string'}},'required':['event_id','kind','body']}},
    {'name':'event_complete', 'description':'请求用户确认某个待办已经完成；未经确认不得将其标记为完成。',
     'input_schema':{'type':'object','properties':{'event_id':{'type':'string'}},'required':['event_id']}},
]


class EventLedger:
    def __init__(self, store):
        self.store = store
        self.root = store.path.parent.parent
        with store.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS role_events (
                id TEXT PRIMARY KEY, owner TEXT, created_by TEXT NOT NULL,
                root_id TEXT NOT NULL, parent TEXT, source_session TEXT, source_message INTEGER,
                source_key TEXT UNIQUE NOT NULL, kind TEXT NOT NULL, body TEXT NOT NULL,
                state TEXT NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS role_event_readers (
                event TEXT NOT NULL, role TEXT NOT NULL, PRIMARY KEY(event,role));
                CREATE UNIQUE INDEX IF NOT EXISTS event_derivation
                ON role_events(root_id,kind) WHERE kind IN ('decision','task');''')

    def list(self, actor):
        require_role(self.root, actor)
        with self.store.connect() as db:
            return [dict(r) for r in db.execute('''SELECT e.* FROM role_events e WHERE owner=?
                OR EXISTS(SELECT 1 FROM role_event_readers r WHERE r.event=e.id AND r.role=?)
                ORDER BY updated DESC LIMIT 200''', (actor, actor))]

    def get(self, actor, event_id):
        require_role(self.root, actor)
        with self.store.connect() as db:
            row = db.execute('''SELECT e.* FROM role_events e WHERE e.id=? AND (owner=?
                OR EXISTS(SELECT 1 FROM role_event_readers r WHERE r.event=e.id AND r.role=?))''',
                (event_id, actor, actor)).fetchone()
        if row is None:
            raise PermissionError('此记录不存在或尚未共享给本角色。')
        return dict(row)

    @staticmethod
    def text(body):
        body = str(body).strip()
        if not body or len(body) > 12000:
            raise ValueError('记录正文需为 1–12000 字。')
        return body

    def _source(self, actor, body, key, sid=None, mid=None):
        body = self.text(body)
        eid = uuid.uuid4().hex
        with self.store.connect() as db:
            db.execute('''INSERT OR IGNORE INTO role_events VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (eid, actor, actor, eid, None, sid, mid, key, 'original', body, 'recorded', now(), now()))
            return dict(db.execute('SELECT * FROM role_events WHERE source_key=?', (key,)).fetchone())

    def user_note(self, actor, body):
        require_role(self.root, actor)
        return self._source(actor, body, 'user-ui:' + uuid.uuid4().hex)

    def record(self, actor, sid, mid, kind, body=''):
        require_role(self.root, actor)
        session = self.store.session(sid)
        if not session or session['role'] != actor:
            raise PermissionError('不能读取其他角色的原始会话。')
        with self.store.connect() as db:
            message = db.execute('SELECT role,content FROM messages WHERE session=? AND id=?', (sid,mid)).fetchone()
        if message is None or message['role'] != 'user' or not isinstance(json.loads(message['content']), str):
            raise ValueError('来源必须是实际用户文本消息。')
        if kind not in ('original', 'inference'):
            raise ValueError('直接记录只能是原文或未确认推断。')
        origin = self._source(actor, json.loads(message['content']), f'message:{sid}:{mid}', sid, mid)
        if kind == 'original': return origin
        body = self.text(body)
        key = origin['id'] + ':inference:' + hashlib.sha256(body.encode()).hexdigest()
        with self.store.connect() as db:
            db.execute('INSERT OR IGNORE INTO role_events VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (uuid.uuid4().hex, actor, actor, origin['id'], origin['id'], sid, mid, key,
                 'inference', body, 'unconfirmed', now(), now()))
            return dict(db.execute('SELECT * FROM role_events WHERE source_key=?', (key,)).fetchone())

    def derive(self, actor, event_id, kind, body, approve):
        origin = self.get(actor, event_id)
        if kind not in ('decision','task'): raise ValueError('无效的确认类型')
        body = self.text(body)
        with self.store.connect() as db:
            existing = db.execute('SELECT id FROM role_events WHERE root_id=? AND kind=?', (origin['root_id'],kind)).fetchone()
        if existing:
            # Do not disclose another role's private derivation through dedup feedback.
            return {'status':'already_exists','note':'此来源已有同类确认记录；请在协作记录中核对，未重复创建。'}
        if not approve('确认' + KINDS[kind], origin['id'],
                       '来源类型：' + KINDS[origin['kind']] + '\n来源：\n' + origin['body'] + '\n\n拟保存：\n' + body):
            return {'status':'denied'}
        self.get(actor,event_id)  # Revalidate grant after asynchronous user review.
        eid = uuid.uuid4().hex
        with self.store.connect() as db:
            db.execute('INSERT OR IGNORE INTO role_events VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (eid,actor,actor,origin['root_id'],event_id,origin['source_session'],origin['source_message'],
                 origin['root_id']+':'+kind,kind,body,'pending' if kind=='task' else 'confirmed',now(),now()))
            inserted = db.execute('SELECT * FROM role_events WHERE id=?', (eid,)).fetchone()
        if not inserted: return {'status':'already_exists'}
        self.store.audit(actor,origin['source_session'],'event_confirmed',eid)
        return dict(inserted)

    def complete(self, actor, event_id, approve):
        event = self.get(actor,event_id)
        if event['kind'] != 'task': raise ValueError('只有待办可以标记完成。')
        if event['state'] == 'completed': return event
        if not approve('确认待办已完成', event_id, event['body']): return {'status':'denied'}
        self.get(actor,event_id)
        with self.store.connect() as db:
            db.execute("UPDATE role_events SET state='completed',updated=? WHERE id=? AND state='pending'", (now(),event_id))
        self.store.audit(actor,event['source_session'],'event_completed',event_id)
        return self.get(actor,event_id)

    def readers(self, event_id):
        with self.store.connect() as db:
            return {r[0] for r in db.execute('SELECT role FROM role_event_readers WHERE event=?',(event_id,))}

    def share_by_user(self, event_id, roles):
        """User settings only. No Agent/tool dispatch exposes this method.
        Share the provenance chain too, so source records cannot be orphaned.
        Revocation applies to the selected record only; its source can be revoked separately.
        """
        for role in roles: require_role(self.root,role,active=False)
        with self.store.connect() as db:
            event = db.execute('SELECT * FROM role_events WHERE id=?',(event_id,)).fetchone()
            if event is None: raise ValueError('记录不存在')
            db.execute('DELETE FROM role_event_readers WHERE event=?',(event_id,))
            current = event_id
            while current:
                row = db.execute('SELECT parent FROM role_events WHERE id=?',(current,)).fetchone()
                if not row: break
                db.executemany('INSERT OR IGNORE INTO role_event_readers VALUES(?,?)',[(current,r) for r in roles])
                current = row[0]

    def export_role(self, role):
        with self.store.connect() as db:
            return {'records':[dict(r) for r in db.execute('SELECT * FROM role_events WHERE owner=?',(role,))],
                    'readers':[dict(r) for r in db.execute('''SELECT * FROM role_event_readers WHERE role=?
                        OR event IN (SELECT id FROM role_events WHERE owner=?)''',(role,role))]}

    @staticmethod
    def retire_role(db, role):
        """Inside the lifecycle's core DB transaction. Preserve user-shared provenance."""
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='role_events'").fetchone(): return
        records = {r['id']:dict(r) for r in db.execute('SELECT id,owner,parent FROM role_events')}
        protected = {r['id'] for r in records.values() if r['owner'] != role}
        protected.update(r[0] for r in db.execute('SELECT event FROM role_event_readers WHERE role<>?',(role,)))
        pending = list(protected)
        while pending:
            parent = records.get(pending.pop(),{}).get('parent')
            if parent and parent not in protected:
                protected.add(parent); pending.append(parent)
        db.executemany('UPDATE role_events SET owner=NULL WHERE id=? AND owner=?',[(eid,role) for eid in protected])
        db.execute('''UPDATE role_events SET source_session=NULL,source_message=NULL
            WHERE source_session IN (SELECT id FROM sessions WHERE role=?)''',(role,))
        db.execute('DELETE FROM role_event_readers WHERE role=? OR event IN (SELECT id FROM role_events WHERE owner=?)', (role,role))
        db.execute('DELETE FROM role_events WHERE owner=?',(role,))
