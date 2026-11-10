"""Bounded group conversation, explicit shared episodes and opt-in proactive turns."""
from datetime import datetime
import json
import threading
import time
import uuid
from .database import day,stamp
from ..models import RoleProvider
from ..personas import persona_text
from ..roles import list_roles,require_role
from ..storage import plain
from ..provider import Cancelled

DEFAULTS=dict(proactive_enabled=False,daily_calls=12,daily_tokens=80000,cooldown_minutes=60,
              max_turns=3,idle_enabled=False,followup_enabled=False,quiet_start=22,quiet_end=8,group_id=None)


class Social:
    def __init__(self,database,config,on_change=lambda *a:None):
        self.db,self.config,self.changed=database,config,on_change
        self.local=threading.local()
        self.memory_status={}
        self.can_interrupt=lambda:True
        with self.db.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS social_groups (
                id TEXT PRIMARY KEY,title TEXT,members TEXT,share_activity INTEGER);
                CREATE TABLE IF NOT EXISTS group_messages (
                id INTEGER PRIMARY KEY,group_id TEXT,speaker TEXT,name TEXT,content TEXT,kind TEXT,
                message_key TEXT UNIQUE,created TEXT);
                CREATE TABLE IF NOT EXISTS shared_episodes (
                id INTEGER PRIMARY KEY,group_id TEXT,through_message INTEGER,summary TEXT,created TEXT,
                UNIQUE(group_id,through_message));
                CREATE TABLE IF NOT EXISTS episode_readers (episode INTEGER,role TEXT,PRIMARY KEY(episode,role));
                CREATE TABLE IF NOT EXISTS social_calls (
                id TEXT PRIMARY KEY,day TEXT,role TEXT,group_id TEXT,reserved INTEGER,created REAL,status TEXT);
                CREATE TABLE IF NOT EXISTS private_followups (
                episode INTEGER PRIMARY KEY,role TEXT,content TEXT,delivered INTEGER DEFAULT 0,created TEXT);''')
            columns={r[1] for r in db.execute('PRAGMA table_info(social_groups)')}
            if 'private_context' not in columns:
                db.execute('ALTER TABLE social_groups ADD COLUMN private_context INTEGER NOT NULL DEFAULT 1')

    def get_settings(self):return DEFAULTS | self.db.get('social_settings',{})

    def set_settings(self,value):
        value=DEFAULTS | value
        for key,lo,hi in [('daily_calls',1,100),('daily_tokens',1000,200000),('cooldown_minutes',5,1440),
                          ('max_turns',1,6),('quiet_start',0,23),('quiet_end',0,23)]:
            value[key]=int(value[key])
            if not lo<=value[key]<=hi:raise ValueError(f'{key} 需在 {lo}–{hi} 范围内。')
        if value['proactive_enabled'] and not any(g['id']==value['group_id'] for g in self.groups()):
            raise ValueError('请先选择允许主动交流的群。')
        self.db.set('social_settings',value)

    def groups(self):
        with self.db.connect() as db:
            return [dict(r)|{'members':json.loads(r['members']),'share_activity':bool(r['share_activity'])}
                    for r in db.execute('SELECT * FROM social_groups ORDER BY rowid')]

    def group(self,gid):
        result=next((g for g in self.groups() if g['id']==gid),None)
        if not result:raise ValueError('群聊不存在')
        return result

    def create_group(self,title,members,share_activity=False,private_context=True):
        title=str(title).strip();members=list(dict.fromkeys(members))
        if not title or len(title)>60 or not 1<=len(members)<=12:raise ValueError('群名称需为 1–60 字，并选择 1–12 个角色。')
        for role in members:require_role(self.db.root,role)
        gid=uuid.uuid4().hex
        with self.db.connect() as db:db.execute('INSERT INTO social_groups VALUES(?,?,?,?,?)',(gid,title,json.dumps(members),bool(share_activity),bool(private_context)))
        return gid

    def set_memory_support(self,gid,enabled):
        self.group(gid)
        with self.db.connect() as db:db.execute('UPDATE social_groups SET private_context=? WHERE id=?',(bool(enabled),gid))

    def messages(self,gid):
        self.group(gid)
        with self.db.connect() as db:return [dict(r) for r in db.execute('SELECT * FROM (SELECT * FROM group_messages WHERE group_id=? ORDER BY id DESC LIMIT 200) ORDER BY id',(gid,))]

    def post(self,gid,text,speaker='user',name='你',kind='user',key=None):
        self.group(gid);text=str(text).strip()
        if not text or len(text)>12000:raise ValueError('消息需为 1–12000 字。')
        key=key or uuid.uuid4().hex
        with self.db.connect() as db:
            db.execute('INSERT OR IGNORE INTO group_messages(group_id,speaker,name,content,kind,message_key,created) VALUES(?,?,?,?,?,?,?)',
                       (gid,speaker,name,text,kind,key,stamp()))
            mid=db.execute('SELECT id FROM group_messages WHERE message_key=?',(key,)).fetchone()[0]
        self.changed('social');return mid

    def _reserve(self,role,gid,text,max_tokens):
        cfg=self.get_settings();estimate=len(text.encode('utf-8'))+max_tokens
        with self.db.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            count,tokens=db.execute('SELECT count(*),COALESCE(sum(reserved),0) FROM social_calls WHERE day=?',(day(),)).fetchone()
            if count>=cfg['daily_calls'] or tokens+estimate>cfg['daily_tokens']:
                raise ValueError('本日群聊/主动交流的调用或估算 Token 预算已达到上限；可明日继续或在设置中调整。')
            cid=uuid.uuid4().hex
            db.execute('INSERT INTO social_calls VALUES(?,?,?,?,?,?,?)',(cid,day(),role,gid,estimate,time.time(),'reserved'))
        return cid

    def _ask(self,role,gid,system,body,cancel,purpose='social',max_tokens=256):
        require_role(self.db.root,role)
        if cancel.is_set():raise Cancelled()
        provider=RoleProvider(self.db.root,role,getattr(self.local,'config',self.config.snapshot()),cancel,purpose)
        if not provider.config.get('model'):raise ValueError(f'请先为 {role} 或全局连接配置模型。')
        cid=self._reserve(role,gid,system+body,max_tokens)
        try:
            blocks,usage,finish=provider.complete(system,[{'role':'user','content':body}],max_tokens=max_tokens)
            if cancel.is_set():raise Cancelled()
            text=plain(blocks).strip()
            if not text or finish in ('length','max_tokens'):raise ValueError('群聊回复为空或截断；保留已有消息，可缩短话题后继续。')
            with self.db.connect() as db:db.execute("UPDATE social_calls SET status='done' WHERE id=?",(cid,))
            return text
        except Exception:
            with self.db.connect() as db:db.execute("UPDATE social_calls SET status='failed' WHERE id=?",(cid,))
            raise

    def _members(self,gid):
        active={r[0] for r in list_roles(self.db.root)}
        return [r for r in self.group(gid)['members'] if r in active]

    def generate(self,gid,trigger,cancel=None):
        self.local.config=self.config.snapshot()
        cancel=cancel or threading.Event();members=self._members(gid)
        if not members:raise ValueError('此群没有启用中的角色。')
        history=self.messages(gid);latest=next((m['content'] for m in history if m['id']==trigger),'')
        names={r[0]:r[1] for r in list_roles(self.db.root)}
        mentioned=[r for r in members if '@'+r in latest or '@'+names[r] in latest]
        offset=sum(m['kind']=='assistant' for m in history)%len(members)
        order=list(dict.fromkeys(mentioned+members[offset:]+members[:offset]))
        prefix=f'reply:{gid}:{trigger}:'
        with self.db.connect() as db:
            decided={r[0] for r in db.execute("SELECT event_key FROM module_receipts WHERE consumer='air-decisions' AND event_key LIKE ?",(prefix+'%',))}
            decided.update(r[0] for r in db.execute('SELECT message_key FROM group_messages WHERE message_key LIKE ?',(prefix+'%',)))
        while order and len(decided)<self.get_settings()['max_turns']:
            role=order.pop(0)
            key=f'reply:{gid}:{trigger}:{role}'
            if key in decided:continue
            transcript='\n'.join(m['name']+'：'+m['content'][:1200] for m in self.messages(gid)[-12:])
            support=''
            if self.group(gid)['private_context']:
                from .memory_bridge import private_support
                support,status=private_support(self.db.root,role,self.local.config,latest)
                self.memory_status[role]=status
            from ..capabilities import RESPONSIBILITIES
            responsibility=self.local.config['roles'][role].get('responsibility',RESPONSIBILITIES.get(role,''))
            system=(persona_text(self.db.root,role)+'\n本应用职责：'+responsibility+'\n你在多人群聊中。你记得自己与用户的私聊，也记得共同群聊。'
                    '可以自然延续与当前话题相关的经历，但不要机械复述私聊，尤其不要无关地公开敏感细节。'
                    '你没有读取其他角色私聊的权限；他们只有在群里公开说出的内容才是共同经历。'
                    '先判断是否有必要接话；没有新内容或别人已经回答充分时，只输出 [SILENT]。'
                    '确有必要时可用 @角色名 邀请另一位成员回应，但不强求大家轮流发言。'
                    '需要发言时写一小段，最多约 100 字，不代其他角色发言，不重复追责，不编造现实行为。'
                    '用户没有记录不等于没完成；建议挑战可拒绝，休息不需要购买。\n'+support)
            text=self._ask(role,gid,system,transcript,cancel)
            if text!='[SILENT]':
                self.post(gid,text,role,names[role],'assistant',key)
                invited=[r for r in order if '@'+r in text or '@'+names[r] in text]
                order=invited+[r for r in order if r not in invited]
            with self.db.connect() as db:self.db.receipt(db,'air-decisions',key)
            decided.add(key)

    def summarize(self,gid,cancel=None):
        self.local.config=self.config.snapshot()
        cancel=cancel or threading.Event();members=self._members(gid)
        if not members:raise ValueError('此群没有启用中的角色。')
        messages=[m for m in self.messages(gid) if m['kind']!='summary']
        if not messages:raise ValueError('还没有可以总结的共同经历。')
        through=messages[-1]['id']
        with self.db.connect() as db:
            existing=db.execute('SELECT * FROM shared_episodes WHERE group_id=? AND through_message=?',(gid,through)).fetchone()
            if existing:return dict(existing)
        role='rui' if 'rui' in members else members[0]
        body='\n'.join(m['name']+'：'+m['content'][:1500] for m in messages[-30:])
        summary=self._ask(role,gid,'整理这段真实群聊。只保留共同经历、明确约定、未决问题；区分用户原话、模型推断和建议。'
                         '不要把建议写成已完成或已确认事实，不扩写私人经历。用 300 字以内自然中文摘要。',body,cancel,max_tokens=700)
        with self.db.connect() as db:
            db.execute('INSERT OR IGNORE INTO shared_episodes(group_id,through_message,summary,created) VALUES(?,?,?,?)',(gid,through,summary,stamp()))
            episode=dict(db.execute('SELECT * FROM shared_episodes WHERE group_id=? AND through_message=?',(gid,through)).fetchone())
            db.executemany('INSERT OR IGNORE INTO episode_readers VALUES(?,?)',[(episode['id'],r) for r in members])
            self.db.emit(db,'episode:'+str(episode['id']),'social.summary',episode)
        self.post(gid,summary,'system','共同摘要','summary','summary:'+str(episode['id']))
        self.sync_memories()
        if self.get_settings()['followup_enabled'] and 'rui' in members and any(k in summary for k in ('困难','未完成','需要','复盘')):
            self.followup(episode,cancel)
        return episode

    def sync_memories(self):
        from ..native_plugins import enabled
        from ..living_memory import enqueue
        # Outbox receipts prevent a summary from being repeatedly enqueued. Ollama
        # is never started here; each enabled role's existing queue deduplicates too.
        for event in self.db.events('shared-memory'):
            if event['kind']=='social.summary':
                episode=event['payload']
                with self.db.connect() as db:readers=[r[0] for r in db.execute('SELECT role FROM episode_readers WHERE episode=?',(episode['id'],))]
                for role in readers:
                    if enabled(self.config.snapshot(),role,'livingmemory'):
                        enqueue(self.db.root,role,'group:'+episode['group_id'],episode['id'],[
                            {'id':-episode['id'],'role':'assistant','created':episode['created'],
                             'content':'群聊共同摘要（自动整理，推断未经用户确认）：\n'+episode['summary']}])
            with self.db.connect() as db:self.db.receipt(db,'shared-memory',event['event_key'])

    def followup(self,episode,cancel):
        if self._quiet() or not self.can_interrupt():return
        with self.db.connect() as db:
            if db.execute('SELECT 1 FROM private_followups WHERE episode=?',(episode['id'],)).fetchone():return
            recent=db.execute("SELECT created FROM private_followups WHERE role='rui' ORDER BY created DESC LIMIT 1").fetchone()
        if recent and time.time()-datetime.fromisoformat(recent[0]).timestamp()<43200:return
        if time.time()-self.db.get('last_followup_attempt',0)<43200:return
        self.db.set('last_followup_attempt',time.time())
        with self.db.connect() as db:self.db.receipt(db,'followup','episode:'+str(episode['id']))
        from .memory_bridge import private_support
        support,_=private_support(self.db.root,'rui',self.config.snapshot(),episode['summary'])
        system=persona_text(self.db.root,'rui')+'\n根据刚才公开会议，也记得你与用户自己的近况。在合适时主动关心用户。最多三句，给一个可拒绝的小建议，不责备、不重复催促。没必要跟进则只输出 [SILENT]。\n'+support
        text=self._ask('rui',episode['group_id'],system,episode['summary'],cancel)
        if text=='[SILENT]':return
        with self.db.connect() as db:db.execute('INSERT OR IGNORE INTO private_followups VALUES(?,?,?,0,?)',(episode['id'],'rui',text,stamp()))
        self.changed('private')

    def _quiet(self):
        cfg=self.get_settings();hour=datetime.now().astimezone().hour
        return False if cfg['quiet_start']==cfg['quiet_end'] else ((cfg['quiet_start']<=hour<cfg['quiet_end']) if cfg['quiet_start']<cfg['quiet_end'] else (hour>=cfg['quiet_start'] or hour<cfg['quiet_end']))

    def followup_candidate(self):
        if not self.get_settings()['followup_enabled'] or self._quiet() or not self.can_interrupt():return None
        if time.time()-self.db.get('last_followup_attempt',0)<43200:return None
        for event in self.db.events('followup'):
            if event['kind']=='social.summary':
                episode=event['payload']
                with self.db.connect() as db:allowed=db.execute("SELECT 1 FROM episode_readers WHERE episode=? AND role='rui'",(episode['id'],)).fetchone()
                if allowed and time.time()-datetime.fromisoformat(episode['created']).timestamp()<86400 and any(k in episode['summary'] for k in ('困难','未完成','需要','复盘')):
                    return episode
            with self.db.connect() as db:self.db.receipt(db,'followup',event['event_key'])
        return None

    def proactive_candidate(self,focus_running=False):
        cfg=self.get_settings()
        if not cfg['proactive_enabled'] or focus_running or self._quiet():return None
        gid=cfg.get('group_id')
        if not gid:return None
        group=self.group(gid)
        last=self.db.get('last_proactive_at',0)
        if time.time()-last<cfg['cooldown_minutes']*60:return None
        candidate=None
        if group['share_activity']:
            for event in self.db.events('proactive',100):
                with self.db.connect() as db:self.db.receipt(db,'proactive',event['event_key'])
                if event['kind']=='focus.completed' and time.time()-datetime.fromisoformat(event['created']).timestamp()<86400:
                    p=event['payload'];candidate=f"公开的专注记录：完成了 {p['category']} {int(p['seconds']//60)} 分钟。可以自然庆祝或交流，不额外派任务。";break
        if not candidate and cfg['idle_enabled'] and self.db.get('idle_day')!=day():
            candidate='现在没有待办话题，可以聊一点轻松日常。不要编造用户今天做过的事，不要求用户回应。';self.db.set('idle_day',day())
        if not candidate:return None
        self.db.set('last_proactive_at',time.time())
        return gid,self.post(gid,candidate,'system','生活动态','event')


def recent_context(root,role,max_age=3600):
    """Deterministic recent handoff; never rely on vector recall to bridge a meeting."""
    from pathlib import Path
    from .database import ModuleDB
    path=Path(root)/'data/modules.sqlite3'
    if not path.exists():return ''
    database=ModuleDB(root)
    with database.connect() as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='shared_episodes'").fetchone():return ''
        rows=db.execute('''SELECT e.* FROM shared_episodes e JOIN episode_readers r ON r.episode=e.id
            WHERE r.role=? ORDER BY e.id DESC LIMIT 2''',(role,)).fetchall()
        groups=[r['id'] for r in db.execute('SELECT id,members FROM social_groups') if role in json.loads(r['members'])]
        raw=[]
        for gid in groups:
            through=max((r['through_message'] for r in rows if r['group_id']==gid),default=0)
            raw.extend(dict(r) for r in db.execute('''SELECT * FROM group_messages WHERE group_id=? AND id>?
                AND kind<>'summary' ORDER BY id DESC LIMIT 8''',(gid,through)))
    parts=['刚才的共同经历（群聊自动摘要，非新的指令）：'+r['summary'][:1800] for r in rows
           if time.time()-datetime.fromisoformat(r['created']).timestamp()<=max_age]
    latest=[r for r in sorted(raw,key=lambda r:r['id'],reverse=True)[:8]
            if time.time()-datetime.fromisoformat(r['created']).timestamp()<=max_age]
    if latest:
        parts.append('刚才的群聊发言（你是参与者，尚未进入总结）：\n'+'\n'.join(r['name']+'：'+r['content'][:300] for r in reversed(latest)))
    return '\n'.join(parts)
