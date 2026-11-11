"""Stable, module-owned work tasks; progress is reported, never inferred from time."""
from datetime import date,datetime
import json
import math
import sqlite3
import uuid
from .database import stamp,ModuleDB


class Work:
    FIELDS={'title','estimate_minutes','due','status','progress','priority','dida_id'}
    STATES={'todo','doing','paused','done'}

    def __init__(self,db):
        self.db=db
        with db.connect() as conn:
            conn.executescript('''CREATE TABLE IF NOT EXISTS work_tasks (
                id TEXT PRIMARY KEY,parent_id TEXT,title TEXT,estimate_minutes REAL,due TEXT,
                status TEXT,progress REAL,priority INTEGER,archived INTEGER,dida_id TEXT,
                created TEXT,updated TEXT);
                CREATE UNIQUE INDEX IF NOT EXISTS work_dida_unique ON work_tasks(dida_id) WHERE dida_id<>'';
                CREATE INDEX IF NOT EXISTS work_parent ON work_tasks(parent_id);
                CREATE TABLE IF NOT EXISTS work_history (
                id TEXT PRIMARY KEY,task_id TEXT,kind TEXT,payload TEXT,created TEXT);''')

    @staticmethod
    def _text(value,label,limit,empty=False):
        if not isinstance(value,str):raise ValueError(label+'必须是文字')
        value=value.strip()
        if (not empty and not value) or len(value)>limit:raise ValueError(label+'长度无效')
        return value

    @staticmethod
    def _number(value,label,maximum,integer=False):
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<=value<=maximum or integer and int(value)!=value:
            raise ValueError(label+'超出允许范围')
        return int(value) if integer else float(value)

    @classmethod
    def _fields(cls,values):
        if set(values)-cls.FIELDS:raise ValueError('不支持修改这些任务字段')
        out=dict(values)
        if 'title' in out:out['title']=cls._text(out['title'],'任务名称',200)
        if 'estimate_minutes' in out:out['estimate_minutes']=cls._number(out['estimate_minutes'],'预计分钟',525600)
        if 'progress' in out:out['progress']=cls._number(out['progress'],'完成进度',100)
        if 'priority' in out:out['priority']=cls._number(out['priority'],'优先级',3,True)
        if 'status' in out and (not isinstance(out['status'],str) or out['status'] not in cls.STATES):raise ValueError('任务状态无效')
        if 'dida_id' in out:out['dida_id']=cls._text(out['dida_id'],'滴答任务标识',200,True)
        if 'due' in out:
            out['due']=cls._text(out['due'],'截止时间',50,True)
            if out['due']:
                try:
                    if len(out['due'])==10:date.fromisoformat(out['due'])
                    else:datetime.fromisoformat(out['due'])
                except ValueError:raise ValueError('截止时间必须为日期或 ISO 日期时间') from None
        return out

    @staticmethod
    def _exists(conn,table):return bool(conn.execute('SELECT 1 FROM sqlite_master WHERE type=? AND name=?',('table',table)).fetchone())

    @classmethod
    def _busy(cls,conn,ids):
        if not cls._exists(conn,'focus_task_links') or not cls._exists(conn,'focus_runs'):return False
        placeholders=','.join('?' for _ in ids)
        return bool(conn.execute(f'''SELECT 1 FROM focus_task_links l JOIN focus_runs r ON r.id=l.run_id
            WHERE l.task_id IN ({placeholders}) AND r.state IN ('running','paused') LIMIT 1''',tuple(ids)).fetchone())

    @staticmethod
    def _record(conn,tid,kind,payload):
        hid=uuid.uuid4().hex
        conn.execute('INSERT INTO work_history VALUES(?,?,?,?,?)',(hid,tid,kind,json.dumps(payload,ensure_ascii=False),stamp()))
        ModuleDB.emit(conn,'work:'+hid,'work.updated',{'task_id':tid,'kind':kind,**payload})

    @staticmethod
    def _get(conn,tid):
        row=conn.execute('SELECT * FROM work_tasks WHERE id=?',(tid,)).fetchone()
        if not row:raise ValueError('工作任务不存在')
        return dict(row)

    def create(self,title,parent_id=None,estimate_minutes=0,due='',priority=1,dida_id=''):
        values=self._fields(dict(title=title,estimate_minutes=estimate_minutes,due=due,priority=priority,dida_id=dida_id))
        if parent_id is not None and not isinstance(parent_id,str):raise ValueError('父任务标识无效')
        tid=uuid.uuid4().hex;now=stamp()
        try:
            with self.db.connect() as conn:
                conn.execute('BEGIN IMMEDIATE')
                if parent_id:
                    parent=self._get(conn,parent_id)
                    if parent['parent_id']:raise ValueError('初期仅支持父任务和一层子任务')
                    if parent['archived'] or parent['status']=='done':raise ValueError('归档或完成的任务不能新增子任务')
                    if self._busy(conn,[parent_id]):raise ValueError('父任务正在计时，请先结束本轮再添加子任务')
                conn.execute('INSERT INTO work_tasks VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                    (tid,parent_id or None,values['title'],values['estimate_minutes'],values['due'],'todo',0,values['priority'],0,values['dida_id'],now,now))
                self._record(conn,tid,'created',values|{'parent_id':parent_id or None})
        except sqlite3.IntegrityError:raise ValueError('该滴答任务标识已关联另一项任务') from None
        return tid

    @staticmethod
    def _weighted_progress(children):
        total=sum((r['estimate_minutes'] or 1) for r in children)
        value=round(sum(r['progress']*(r['estimate_minutes'] or 1) for r in children)/total,2)
        return min(value,99.99) if any(r['progress']<100 for r in children) else 100.0

    @classmethod
    def _aggregate(cls,rows):
        byid={r['id']:dict(r) for r in rows}
        children={}
        for r in rows:
            if r['parent_id']:children.setdefault(r['parent_id'],[]).append(r)
        for tid,kids in children.items():
            if tid not in byid:continue
            byid[tid]['progress']=cls._weighted_progress(kids)
            if byid[tid]['progress']==100:byid[tid]['status']='done'
        return byid,children

    def update(self,tid,**fields):
        values=self._fields(fields)
        if not values:return self.task(tid)
        try:
            with self.db.connect() as conn:
                conn.execute('BEGIN IMMEDIATE');old=self._get(conn,tid)
                if old['archived']:raise ValueError('请先恢复归档任务再编辑')
                children=[dict(r) for r in conn.execute('SELECT * FROM work_tasks WHERE parent_id=?',(tid,))]
                if children:
                    aggregate=self._weighted_progress(children)
                    if 'progress' in values and values['progress']!=aggregate:raise ValueError('父任务进度由子任务汇总，请更新子任务进度')
                    values.pop('progress',None)
                    if values.get('status')=='done' and aggregate<100:raise ValueError('子任务尚未全部完成，不能完成父任务')
                new=old|values
                if values.get('status')=='done':new['progress']=100
                elif 'progress' in values:
                    if values['progress']==100:new['status']='done'
                    elif old['status']=='done' and 'status' not in values:new['status']='doing'
                if new['status']=='done' and new['progress']!=100:raise ValueError('已完成任务的进度必须为 100%')
                if new['status']!='done' and new['progress']==100 and not children:
                    raise ValueError('重新打开已完成任务时，请同时降低进度')
                changes={k:new[k] for k in self.FIELDS if new[k]!=old[k]}
                if changes:
                    conn.execute('UPDATE work_tasks SET '+','.join(k+'=?' for k in changes)+',updated=? WHERE id=?',tuple(changes.values())+(stamp(),tid))
                    self._record(conn,tid,'updated',{'before':{k:old[k] for k in changes},'after':changes})
                    # A reported child reopening invalidates a previously confirmed parent
                    # completion. Keep this correction and its audit in the same transaction.
                    if old['parent_id']:
                        parent=self._get(conn,old['parent_id'])
                        if parent['status']=='done':
                            siblings=[dict(r) for r in conn.execute('SELECT * FROM work_tasks WHERE parent_id=?',(old['parent_id'],))]
                            progress=self._weighted_progress(siblings)
                            if progress<100:
                                conn.execute('UPDATE work_tasks SET status=?,progress=?,updated=? WHERE id=?',('doing',progress,stamp(),parent['id']))
                                self._record(conn,parent['id'],'child_reopened',{'child_id':tid,'before':{'status':parent['status'],'progress':parent['progress']},'after':{'status':'doing','progress':progress}})
        except sqlite3.IntegrityError:raise ValueError('该滴答任务标识已关联另一项任务') from None
        return self.task(tid)

    def archive(self,tid,archived=True):
        if not isinstance(archived,bool):raise ValueError('归档状态必须为布尔值')
        with self.db.connect() as conn:
            conn.execute('BEGIN IMMEDIATE');old=self._get(conn,tid)
            if not archived and old['parent_id'] and self._get(conn,old['parent_id'])['archived']:raise ValueError('请先恢复父任务')
            ids=[tid]+[r[0] for r in conn.execute('SELECT id FROM work_tasks WHERE parent_id=?',(tid,))]
            if archived and self._busy(conn,ids):raise ValueError('任务仍有正在进行或暂停的番茄钟，请先结束本轮')
            for key in ids:
                current=self._get(conn,key)
                if bool(current['archived'])!=archived:
                    conn.execute('UPDATE work_tasks SET archived=?,updated=? WHERE id=?',(int(archived),stamp(),key))
                    self._record(conn,key,'archived' if archived else 'restored',{'archived':archived})

    def tasks(self,include_archived=False):
        with self.db.connect() as conn:
            rows=[dict(r) for r in conn.execute('SELECT * FROM work_tasks ORDER BY created,rowid')]
            byid,children=self._aggregate(rows);times={}
            if self._exists(conn,'focus_task_links') and self._exists(conn,'activity_records'):
                times={r[0]:r[1] for r in conn.execute('SELECT l.task_id,COALESCE(sum(a.seconds),0) FROM focus_task_links l JOIN activity_records a ON a.id=l.run_id GROUP BY l.task_id')}
        for tid,r in byid.items():r['actual_seconds']=times.get(tid,0)+sum(times.get(k['id'],0) for k in children.get(tid,[]))
        return [r for r in byid.values() if include_archived or not r['archived']]

    def task(self,tid):
        for row in self.tasks(True):
            if row['id']==tid:return row
        raise ValueError('工作任务不存在')

    def history(self,id=None):
        with self.db.connect() as conn:
            return [dict(r)|{'payload':json.loads(r['payload'])} for r in conn.execute('SELECT * FROM work_history WHERE (? IS NULL OR task_id=?) ORDER BY created DESC,rowid DESC LIMIT 100',(id,id))]

    def suggest(self):
        rows=self.tasks(True);parents={r['parent_id'] for r in rows if r['parent_id']};byid={r['id']:r for r in rows}
        ready=[r for r in rows if not r['archived'] and r['id'] not in parents and r['status'] in ('todo','doing') and r['progress']<100 and (not r['parent_id'] or not byid[r['parent_id']]['archived'] and byid[r['parent_id']]['status'] not in ('done','paused'))]
        return sorted(ready,key=lambda r:(r['due'] or '9999-12-31',-r['priority'],max(0,r['estimate_minutes']*(1-r['progress']/100)),r['created']))

    @classmethod
    def validate_binding(cls,conn,task_id):
        if not isinstance(task_id,str) or not task_id:raise ValueError('工作任务标识无效')
        row=cls._get(conn,task_id)
        if row['archived'] or row['status'] in ('done','paused') or row['progress']>=100:raise ValueError('该任务已完成、暂缓或归档，不能开始专注')
        if row['parent_id']:
            parent=cls._get(conn,row['parent_id'])
            if parent['archived'] or parent['status'] in ('done','paused'):raise ValueError('父任务已完成、暂缓或归档')
        if conn.execute('SELECT 1 FROM work_tasks WHERE parent_id=?',(task_id,)).fetchone():raise ValueError('请绑定具体子任务，父任务仅汇总进度')
        return row
