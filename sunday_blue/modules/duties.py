"""Stable responsibility slots and a transactional recorder -> organizer queue."""
import hashlib,json,uuid
from .database import stamp,day
from .organizer import Organizer
from ..roles import list_roles,require_role

SLOTS=(('director','总负责人','rui'),('exercise','运动负责人','red'),('diet','饮食负责人','ewa'),('recovery','精力与作息负责人','luna'),('study','学习负责人','loluns'),('recorder','记录员','kia'),('organizer','整理员','mubu'))
RULES={'director':'汇总真实模块数据，负责统筹、规划和复盘；建议不是已确认决定。','exercise':'管理用户上报的运动事实与计划，不以高强度或缺少记录推断表现。','diet':'管理饮食记录与分析，不把建议写成真实食用记录。','recovery':'管理睡眠、屏幕使用和主观精力；估计不冒充医学测量。','study':'读取学习专注和进度，提供适量计划与复盘。','recorder':'快速捕获用户原文至待确认收件箱；复杂整理交给整理员，不反复规划。','organizer':'处理独立交接队列，复用已有分类、保留原文和修改记录；归属不明问用户，失败保留。'}

def installed(root):
    from pathlib import Path
    import sqlite3
    path=Path(root)/'data/modules.sqlite3'
    if not path.exists():return False
    c=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
    try:return bool(c.execute("SELECT 1 FROM sqlite_master WHERE name='duty_slots'").fetchone())
    finally:c.close()

def assigned(root,role):
    """Read-only lookup; callers such as prompts never implicitly migrate roles."""
    from pathlib import Path
    import sqlite3
    path=Path(root)/'data/modules.sqlite3'
    if not path.exists():return []
    c=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
    try:
        if not c.execute("SELECT 1 FROM sqlite_master WHERE name='duty_slots'").fetchone():return []
        return [r[0] for r in c.execute('SELECT id FROM duty_slots WHERE role_id=?',(role,))]
    finally:c.close()

def effective_extensions(root,role):
    from pathlib import Path
    import sqlite3
    result={'plugins':[],'skills':[]}
    if not installed(root):return result
    c=sqlite3.connect((Path(root)/'data/modules.sqlite3').as_uri()+'?mode=ro',uri=True)
    try:
        for row in c.execute('SELECT extensions FROM duty_slots WHERE role_id=?',(role,)):
            value=json.loads(row[0])
            for key in result:result[key].extend(value.get(key,[]))
    finally:c.close()
    return {key:list(dict.fromkeys(values)) for key,values in result.items()}

def context(root,role):
    slots=assigned(root,role)
    return '\n'.join(RULES[s] for s in slots if s in RULES)

class Duties:
    def __init__(self,db):
        self.db=db;Organizer(db)
        active={r[0] for r in list_roles(db.root)}
        with db.connect() as c:
            c.executescript('''CREATE TABLE IF NOT EXISTS duty_slots(id TEXT PRIMARY KEY,title TEXT,role_id TEXT,extensions TEXT);
            CREATE TABLE IF NOT EXISTS duty_handoffs(id TEXT PRIMARY KEY,record_id TEXT UNIQUE,status TEXT,request TEXT,files TEXT,result TEXT,created TEXT,updated TEXT);
            CREATE TABLE IF NOT EXISTS duty_changes(id INTEGER PRIMARY KEY,slot_id TEXT,before_role TEXT,after_role TEXT,created TEXT);''')
            for sid,title,role in SLOTS:c.execute('INSERT OR IGNORE INTO duty_slots VALUES(?,?,?,?)',(sid,title,role if role in active else None,'{}'))
    def slots(self):
        with self.db.connect() as c:rows={r['id']:dict(r) for r in c.execute('SELECT * FROM duty_slots')}
        return [rows[s[0]]|{'extensions':json.loads(rows[s[0]]['extensions'])} for s in SLOTS]
    def assign(self,slot,role_id):
        if slot not in RULES:raise ValueError('职责槽位不存在')
        if role_id:require_role(self.db.root,role_id)
        with self.db.connect() as c:
            c.execute('BEGIN IMMEDIATE');row=c.execute('SELECT role_id,extensions FROM duty_slots WHERE id=?',(slot,)).fetchone();old=row[0]
            ext=json.loads(row[1]);self._validate_extensions(ext.get('plugins',[]),ext.get('skills',[]),role_id)
            if old==role_id:return
            c.execute('UPDATE duty_slots SET role_id=? WHERE id=?',(role_id or None,slot))
            c.execute('INSERT INTO duty_changes(slot_id,before_role,after_role,created) VALUES(?,?,?,?)',(slot,old,role_id or None,stamp()))
            self.db.emit(c,'duty:'+uuid.uuid4().hex,'duty.assigned',{'slot':slot,'role_id':role_id})
    def _validate_extensions(self,plugins,skills,role_id):
        import re
        from ..plugin_runtime import discover
        from ..files import no_links
        for values in (plugins,skills):
            if not isinstance(values,list) or len(values)>30 or any(not isinstance(v,str) or not re.fullmatch(r'[A-Za-z0-9_-]+',v) for v in values):raise ValueError('扩展需为最多 30 个有效 ID 的列表')
        catalog=discover(self.db.root)
        for pid in plugins:
            meta=catalog.get(pid)
            if pid=='kia-organizer':raise ValueError('旧 Kia 整理插件已由职责工具替代，不应重复绑定')
            if not meta or meta.get('error') or meta.get('module_only'):raise ValueError('插件未安装或不能作为角色能力：'+pid)
            if role_id and meta.get('allowed_roles') and role_id not in meta['allowed_roles']:raise ValueError('插件限制了可用人格，不能分配给当前人格：'+pid)
        for name in skills:
            path=self.db.root/'extensions/skills'/name/'SKILL.md';no_links(path)
            if not path.is_file() or path.stat().st_size>65536:raise ValueError('Skill 未安装或超过 64 KiB：'+name)
        return {'plugins':list(dict.fromkeys(plugins)),'skills':list(dict.fromkeys(skills))}
    def set_extensions(self,slot,plugins,skills):
        if slot not in RULES:raise ValueError('职责槽位不存在')
        with self.db.connect() as c:
            c.execute('BEGIN IMMEDIATE');role=c.execute('SELECT role_id FROM duty_slots WHERE id=?',(slot,)).fetchone()[0]
            value=self._validate_extensions(plugins,skills,role)
            c.execute('UPDATE duty_slots SET extensions=? WHERE id=?',(json.dumps(value),slot))
            self.db.emit(c,'duty-extensions:'+uuid.uuid4().hex,'duty.extensions_changed',{'slot':slot,'plugins':value['plugins'],'skills':value['skills']})
        return value
    def capture(self,title,body,request='',files=''):
        title=str(title).strip();body=str(body).strip();request=str(request).strip();files=str(files).strip()
        if not title or len(title)>120 or not body or len(body)>30000 or len(request)>2000 or len(files)>4000:raise ValueError('记录标题、原文或交接说明长度无效')
        fingerprint=hashlib.sha256(('recorder|'+day()+'|'+body).encode()).hexdigest();rid=uuid.uuid4().hex;hid=uuid.uuid4().hex
        with self.db.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute('INSERT OR IGNORE INTO organized_records VALUES(?,?,?,?,?,?,?,?,?)',(rid,title,body,'收件箱',day(),'proposal','recorder',fingerprint,stamp()))
            rid=c.execute('SELECT id FROM organized_records WHERE fingerprint=?',(fingerprint,)).fetchone()[0]
            c.execute('INSERT OR IGNORE INTO duty_handoffs VALUES(?,?,?,?,?,?,?,?)',(hid,rid,'pending',request,files,'',stamp(),stamp()))
            row=dict(c.execute('SELECT h.*,r.title FROM duty_handoffs h JOIN organized_records r ON r.id=h.record_id WHERE record_id=?',(rid,)).fetchone())
            self.db.emit(c,'handoff:'+row['id'],'records.captured',{'record_id':rid,'handoff_id':row['id']})
            return row
    def handoffs(self,include_done=False):
        with self.db.connect() as c:return [dict(r) for r in c.execute("SELECT h.*,r.title,r.body,r.category FROM duty_handoffs h JOIN organized_records r ON r.id=h.record_id WHERE (? OR h.status!='done') ORDER BY h.created DESC LIMIT 200",(bool(include_done),))]
    def complete_handoff(self,id,category,title=None,note=''):
        if category not in Organizer(self.db).categories():raise ValueError('分类不明确时请先问用户')
        if len(str(note))>2000:raise ValueError('处理说明过长')
        with self.db.connect() as c:
            c.execute('BEGIN IMMEDIATE');h=c.execute('SELECT * FROM duty_handoffs WHERE id=?',(id,)).fetchone()
            if not h:raise ValueError('交接条目不存在')
            if h['status']=='done':return dict(h)
            row=c.execute('SELECT * FROM organized_records WHERE id=?',(h['record_id'],)).fetchone()
            if not row:raise ValueError('原始记录不存在，交接保留待处理')
            title=str(title or row['title']).strip()
            if not title or len(title)>120:raise ValueError('标题长度无效')
            c.execute('INSERT INTO record_revisions(record_id,before_json,created) VALUES(?,?,?)',(row['id'],json.dumps(dict(row),ensure_ascii=False),stamp()))
            c.execute('UPDATE organized_records SET title=?,category=? WHERE id=?',(title,category,row['id']))
            result=json.dumps({'category':category,'title':title,'note':str(note)},ensure_ascii=False)
            c.execute("UPDATE duty_handoffs SET status='done',result=?,updated=? WHERE id=?",(result,stamp(),id))
            self.db.emit(c,'organized:'+id,'records.organized',{'record_id':row['id'],'handoff_id':id})
            return dict(c.execute('SELECT * FROM duty_handoffs WHERE id=?',(id,)).fetchone())
    def fail_handoff(self,id,error):
        error=str(error).strip()
        if not error or len(error)>2000:raise ValueError('请填写简短失败原因')
        with self.db.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT status FROM duty_handoffs WHERE id=?',(id,)).fetchone()
            if not row:raise ValueError('交接条目不存在')
            if row['status']=='done':raise ValueError('已完成交接不能标记失败')
            c.execute("UPDATE duty_handoffs SET status='failed',result=?,updated=? WHERE id=?",(error,stamp(),id))
        return {'status':'failed','id':id}
