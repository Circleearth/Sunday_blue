"""Pause-safe focus clock. A committed finish owns both its record and coins."""
from datetime import date, timedelta
import json
import threading
import time
import uuid
from .database import day, stamp
from .rewards import Rewards
from ..roles import require_role
from .focus_preferences import PHASES, options, save_options


class Focus:
    def __init__(self,database,on_change=lambda *a:None,clock=time.monotonic,on_complete=lambda result:None):
        self.db,self.changed,self.clock=database,on_change,clock
        self.completed=on_complete
        self.lock=threading.RLock();self.anchor=None;self.last_settlement=None
        with self.db.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS focus_runs (
                id TEXT PRIMARY KEY,category TEXT,label TEXT,role_id TEXT,state TEXT,elapsed REAL,
                started TEXT,finished TEXT,settlement TEXT);
                CREATE UNIQUE INDEX IF NOT EXISTS one_focus_run ON focus_runs((1)) WHERE state IN ('running','paused');
                CREATE TABLE IF NOT EXISTS activity_records (
                id TEXT PRIMARY KEY,category TEXT,label TEXT,role_id TEXT,seconds REAL,day TEXT,started TEXT,finished TEXT);
                CREATE TABLE IF NOT EXISTS focus_timers (
                run_id TEXT PRIMARY KEY,phase TEXT,duration REAL,long_every INTEGER,end_reason TEXT);''')
            # Never award time while the process was closed or unavailable.
            db.execute("UPDATE focus_runs SET state='paused' WHERE state='running'")

    def categories(self):
        return self.db.get('focus_categories',['工作','学习','运动','家务'])

    def options(self):return options(self.db)

    def set_options(self,values):
        result=save_options(self.db,values);self.changed('focus');return result

    def cycle(self):
        with self.db.connect() as db:
            count=db.execute("SELECT count(*) FROM focus_timers WHERE phase='focus' AND end_reason='complete'").fetchone()[0]
            latest=db.execute('''SELECT t.* FROM focus_timers t JOIN focus_runs r ON r.id=t.run_id
                WHERE r.state='finished' ORDER BY r.finished DESC,r.rowid DESC LIMIT 1''').fetchone()
        phase='focus'
        if latest and latest['phase']=='focus' and latest['end_reason']=='complete':
            phase='long_break' if count%latest['long_every']==0 else 'short_break'
        return {'completed':count,'next_phase':phase}

    def _active(self):
        with self.db.connect() as db:
            row=db.execute('''SELECT r.*,COALESCE(t.phase,'focus') AS phase,COALESCE(t.duration,0) AS duration
                FROM focus_runs r LEFT JOIN focus_timers t ON t.run_id=r.id
                WHERE r.state IN ('running','paused')''').fetchone()
        return dict(row) if row else None

    def status(self):
        with self.lock:
            row=self._active()
            if not row:return {'id':None,'state':'idle','category':'工作','label':'','role_id':'rui','elapsed':0.0,'phase':'focus','duration':0}
            if row['state']=='running' and self.anchor is not None:
                gap=max(0,self.clock()-self.anchor)
                if gap<=30:row['elapsed']+=gap
            if row['duration']:row['elapsed']=min(row['elapsed'],row['duration'])
            return row

    def checkpoint(self,auto_finish=True):
        with self.lock:
            row=self._active()
            if not row or row['state']!='running':return
            current=self.clock();delta=max(0,current-self.anchor) if self.anchor is not None else 0
            asleep=delta>30
            if not asleep and row['duration']:delta=min(delta,max(0,row['duration']-row['elapsed']))
            with self.db.connect() as db:
                if asleep:
                    db.execute("UPDATE focus_runs SET state='paused' WHERE id=?",(row['id'],))
                else:
                    db.execute('UPDATE focus_runs SET elapsed=elapsed+? WHERE id=?',(delta,row['id']))
            self.anchor=None if asleep else current
            if asleep:self.changed('focus','检测到休眠或长时间停顿，计时已暂停；离线时间未计入。')
            elif auto_finish and row['duration'] and row['elapsed']+delta>=row['duration']:
                self.finish()

    def start(self,category,label='',role_id='rui',phase='focus',duration=0):
        category=str(category).strip();label=str(label).strip()
        if not category or len(category)>40 or len(label)>200:raise ValueError('类别需为 1–40 字，说明不超过 200 字。')
        require_role(self.db.root,role_id)
        if phase not in PHASES or isinstance(duration,bool) or not isinstance(duration,(int,float)) or not 0<=duration<=14400:
            raise ValueError('无效的番茄钟阶段或时长。')
        if phase!='focus' and duration<=0:raise ValueError('休息需要设置倒计时时长。')
        with self.lock:
            if self._active():raise ValueError('已有专注计时，请先结束或继续当前计时。')
            rid=uuid.uuid4().hex
            with self.db.connect() as db:
                db.execute('INSERT INTO focus_runs VALUES(?,?,?,?,?,?,?,?,?)',(rid,category,label,role_id,'running',0,stamp(),None,None))
                if duration:
                    db.execute('INSERT INTO focus_timers VALUES(?,?,?,?,NULL)',(rid,phase,duration,self.options()['long_every']))
            self.anchor=self.clock();self.last_settlement=None
            categories=self.categories()
            if category not in categories:self.db.set('focus_categories',categories+[category])
        self.changed('focus','开始了，先做好眼前这一小段。')
        return self.status()

    def pause(self):
        with self.lock:
            self.checkpoint();row=self._active()
            if not row:return self.status()
            with self.db.connect() as db:db.execute("UPDATE focus_runs SET state='paused' WHERE id=?",(row['id'],))
            self.anchor=None
        self.changed('focus','计时暂停，休息不扣金币或关系。')
        return self.status()

    def resume(self):
        with self.lock:
            row=self._active()
            if not row or row['state']!='paused':raise ValueError('没有暂停中的专注。')
            with self.db.connect() as db:db.execute("UPDATE focus_runs SET state='running' WHERE id=?",(row['id'],))
            self.anchor=self.clock()
        self.changed('focus','欢迎回来，从这一刻继续就好。')
        return self.status()

    def finish(self):
        with self.lock:
            self.checkpoint(auto_finish=False);row=self._active()
            if not row:
                if self.last_settlement:return self.last_settlement
                raise ValueError('没有可以结算的专注。')
            seconds=row['elapsed'];valid=seconds>120 and row['phase']=='focus';record=None;coins=0;personal=False
            timed_complete=bool(row['duration'] and seconds>=row['duration'])
            with self.db.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                stored=db.execute('SELECT state,settlement FROM focus_runs WHERE id=?',(row['id'],)).fetchone()
                if stored['state']=='finished':return json.loads(stored['settlement'])
                if valid:
                    previous=db.execute('SELECT COALESCE(max(seconds),0) FROM activity_records').fetchone()[0]
                    record={k:row[k] for k in ('id','category','label','role_id','started')}
                    record.update(seconds=round(seconds,2),day=day(),finished=stamp())
                    db.execute('INSERT INTO activity_records VALUES(?,?,?,?,?,?,?,?)',tuple(record[k] for k in
                        ('id','category','label','role_id','seconds','day','started','finished')))
                    earned=db.execute('''SELECT COALESCE(sum(c.amount),0) FROM coin_ledger c
                        JOIN activity_records a ON c.reason='focus:'||a.id WHERE a.day=?''',(day(),)).fetchone()[0]
                    coins=max(0,min(int(seconds//60),180-earned))
                    db.execute('INSERT OR IGNORE INTO coin_ledger VALUES(?,?,?,?)',('focus:'+row['id'],coins,'focus:'+row['id'],stamp()))
                    personal=seconds>previous
                    self.db.emit(db,'focus:'+row['id'],'focus.completed',record|{'coins':coins})
                stats=self._stats(db)
                feedback=('这段努力已经记下了。先松松肩膀，下一步由你决定。' if valid else '这一小段先不计入有效记录；调整一下再开始也可以。')
                if row['phase']!='focus':feedback='休息结束，按自己的节奏开始下一轮。休息不计记录或金币。'
                result=dict(valid=valid,record=record,coins_earned=coins,balance=stats['balance'],today_seconds=stats['today_seconds'],
                            streak=stats['streak'],personal_best=personal,milestones=stats['milestones'],feedback=feedback,
                            run_id=row['id'],phase=row['phase'],completed_timer=timed_complete)
                db.execute('UPDATE focus_timers SET end_reason=? WHERE run_id=?',('complete' if timed_complete else 'early',row['id']))
                db.execute("UPDATE focus_runs SET state='finished',finished=?,settlement=? WHERE id=?",(stamp(),json.dumps(result,ensure_ascii=False),row['id']))
            self.anchor=None;self.last_settlement=result
        self.changed('focus',feedback)
        if timed_complete:self.completed(result)
        return result

    def _stats(self,db):
        today=day();week=(date.fromisoformat(today)-timedelta(days=6)).isoformat()
        rows=db.execute('SELECT day,seconds FROM activity_records ORDER BY day DESC').fetchall()
        days={r['day'] for r in rows};cursor=date.fromisoformat(today)
        if today not in days:cursor-=timedelta(days=1)
        streak=0
        while cursor.isoformat() in days:streak+=1;cursor-=timedelta(days=1)
        return dict(today_seconds=sum(r['seconds'] for r in rows if r['day']==today),today_count=sum(r['day']==today for r in rows),
                    week_seconds=sum(r['seconds'] for r in rows if r['day']>=week),best_seconds=max((r['seconds'] for r in rows),default=0),
                    streak=streak,balance=Rewards.balance(db),milestones=[f'累计完成 {n} 次' for n in (1,5,10,25,50,100) if len(rows)>=n])

    def stats(self):
        with self.db.connect() as db:return self._stats(db)

    def records(self):
        with self.db.connect() as db:return [dict(r) for r in db.execute('SELECT * FROM activity_records ORDER BY finished DESC,rowid DESC LIMIT 30')]
