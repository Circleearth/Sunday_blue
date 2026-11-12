"""Confirmed life inputs and conservative estimates; append-only reward adjustments."""
import hashlib,json,math,uuid
from datetime import date,timedelta,datetime
from .database import stamp,day as today
from .rewards import Rewards


def number(value,low,high,label):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not low<=value<=high:raise ValueError(f'{label}需在 {low}–{high} 范围内')
    return float(value)

def valid_day(value):
    value=value or today();date.fromisoformat(value)
    if value>today():raise ValueError('不能提前记录未来的事实')
    return value

class Life:
    def __init__(self,db):
        self.db=db;Rewards(db)
        from .life_state import LifeState
        self.state=LifeState(db)
        with db.connect() as c:
            c.executescript('''CREATE TABLE IF NOT EXISTS exercise_records(id TEXT PRIMARY KEY,kind TEXT,minutes REAL,intensity TEXT,day TEXT,coins INTEGER,revision INTEGER,fingerprint TEXT UNIQUE,created TEXT);
            CREATE TABLE IF NOT EXISTS daily_life(day TEXT PRIMARY KEY,meal TEXT,sleep_hours REAL,phone_total REAL,phone_fun REAL,screen_hours REAL,energy REAL,note TEXT,revision INTEGER,updated TEXT);
            CREATE TABLE IF NOT EXISTS life_revisions(id INTEGER PRIMARY KEY,source TEXT,before_json TEXT,created TEXT);
            CREATE TABLE IF NOT EXISTS housework_awards(day TEXT,title_key TEXT,coins INTEGER,PRIMARY KEY(day,title_key));
            CREATE TABLE IF NOT EXISTS housework_records(id TEXT PRIMARY KEY,title TEXT,day TEXT,coins INTEGER,created TEXT);''')
    @staticmethod
    def _award(c,key,amount,reason):
        c.execute('INSERT OR IGNORE INTO coin_ledger VALUES(?,?,?,?)',(key,amount,reason,stamp()))
    def _reprice_exercise(self,c,day):
        budget=20
        for r in c.execute('SELECT * FROM exercise_records WHERE day=? ORDER BY created,id',(day,)).fetchall():
            m=r['minutes'];base=int(min(m,30)//5+max(0,min(m-30,30))//10+max(0,min(m-60,60))//30)
            if r['intensity']=='high':base=min(base,8)
            coins=min(budget,base);budget-=coins;delta=coins-r['coins']
            if delta:
                rev=r['revision']+1;c.execute('UPDATE exercise_records SET coins=?,revision=? WHERE id=?',(coins,rev,r['id']))
                self.state.growth(c,r['id'],coins,r['coins'])
                self._award(c,f"exercise:{r['id']}:{rev}",delta,'exercise:'+r['id'])
    def exercise(self,kind,minutes,intensity,day=None,record_id=None,muscles=None):
        day=valid_day(day);kind=str(kind).strip();minutes=number(minutes,1,180,'运动分钟')
        if not kind or len(kind)>40 or intensity not in ('light','moderate','high'):raise ValueError('请填写运动名称和轻/中/高强度')
        if intensity=='high' and minutes>90:raise ValueError('高强度超过 90 分钟，请核对记录；长时间运动应按实际含休息的中/轻强度记录，不为奖励加量')
        from .life_state import MUSCLES
        muscles_provided=muscles is not None
        muscles=list(dict.fromkeys(muscles or []))
        if any(m not in MUSCLES for m in muscles):raise ValueError('训练部位无效')
        fingerprint=hashlib.sha256(json.dumps([day,kind.casefold(),minutes,intensity]).encode()).hexdigest()
        with self.db.connect() as c:
            c.execute('BEGIN IMMEDIATE');duplicate=c.execute('SELECT * FROM exercise_records WHERE fingerprint=?',(fingerprint,)).fetchone()
            if duplicate:
                if record_id and record_id!=duplicate['id']:raise ValueError('已有相同运动记录，请编辑已有记录')
                if muscles_provided:
                    c.execute('INSERT INTO exercise_details VALUES(?,?) ON CONFLICT(record_id) DO UPDATE SET muscles=excluded.muscles',(duplicate['id'],json.dumps(muscles)))
                return dict(duplicate)
            old=c.execute('SELECT * FROM exercise_records WHERE id=?',(record_id,)).fetchone() if record_id else None
            if record_id and not old:raise ValueError('运动记录不存在')
            rid=record_id or uuid.uuid4().hex
            if old:
                c.execute('INSERT INTO life_revisions(source,before_json,created) VALUES(?,?,?)',(rid,json.dumps(dict(old),ensure_ascii=False),stamp()))
                c.execute('UPDATE exercise_records SET kind=?,minutes=?,intensity=?,day=?,fingerprint=?,revision=revision+1 WHERE id=?',(kind,minutes,intensity,day,fingerprint,rid))
                if old['day']!=day:self._reprice_exercise(c,old['day'])
            else:c.execute('INSERT INTO exercise_records VALUES(?,?,?,?,?,0,0,?,?)',(rid,kind,minutes,intensity,day,fingerprint,stamp()))
            if muscles_provided or not old:c.execute('INSERT INTO exercise_details VALUES(?,?) ON CONFLICT(record_id) DO UPDATE SET muscles=excluded.muscles',(rid,json.dumps(muscles)))
            self._reprice_exercise(c,day);row=dict(c.execute('SELECT * FROM exercise_records WHERE id=?',(rid,)).fetchone())
            self.db.emit(c,'exercise:'+rid+':'+str(row['revision'])+':'+fingerprint,'exercise.recorded',row)
            return row
    def exercises(self):
        with self.db.connect() as c:return [dict(r) for r in c.execute('SELECT e.*,d.muscles FROM exercise_records e LEFT JOIN exercise_details d ON e.id=d.record_id ORDER BY day DESC,created DESC LIMIT 200')]
    def save_daily(self,day,meal='',sleep_hours=None,phone_total=None,phone_fun=None,screen_hours=None,energy=None,note='',sleep_start=None,sleep_end=None):
        day=valid_day(day);meal=str(meal).strip();note=str(note).strip()
        if len(meal)>4000 or len(note)>2000:raise ValueError('饮食或备注过长')
        if sleep_start is not None or sleep_end is not None:
            if not sleep_start or not sleep_end:raise ValueError('请同时填写入睡与起床时间')
            start=datetime.strptime(sleep_start,'%H:%M');end=datetime.strptime(sleep_end,'%H:%M')
            seconds=(end-start).total_seconds()
            if seconds<0:seconds+=86400
            if seconds<=0:raise ValueError('入睡与起床时间不能相同')
            sleep_hours=round(seconds/3600,3)
        values={'sleep_hours':sleep_hours,'phone_total':phone_total,'phone_fun':phone_fun,'screen_hours':screen_hours,'energy':energy}
        for k,high in [('sleep_hours',24),('phone_total',1440),('phone_fun',1440),('screen_hours',24),('energy',100)]:
            if values[k] is not None:values[k]=number(values[k],0,high,k)
        if phone_fun is not None and (phone_total is None or phone_fun>phone_total):raise ValueError('娱乐时长不能超过总体使用时长；请同时填写总体时长')
        if not meal and not note and all(v is None for v in values.values()):raise ValueError('至少填写一项实际记录')
        payload={'day':day,'meal':meal,**values,'note':note}
        with self.db.connect() as c:
            c.execute('BEGIN IMMEDIATE');old=c.execute('SELECT * FROM daily_life WHERE day=?',(day,)).fetchone()
            if sleep_start is not None:
                c.execute('INSERT INTO daily_life_details VALUES(?,?,?) ON CONFLICT(day) DO UPDATE SET sleep_start=excluded.sleep_start,sleep_end=excluded.sleep_end',(day,sleep_start,sleep_end))
            if old and all(old[k]==v for k,v in payload.items()):return dict(old)|{'sleep_start':sleep_start,'sleep_end':sleep_end}
            rev=old['revision']+1 if old else 1
            if old:c.execute('INSERT INTO life_revisions(source,before_json,created) VALUES(?,?,?)',('daily:'+day,json.dumps(dict(old),ensure_ascii=False),stamp()))
            c.execute('INSERT INTO daily_life VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(day) DO UPDATE SET meal=excluded.meal,sleep_hours=excluded.sleep_hours,phone_total=excluded.phone_total,phone_fun=excluded.phone_fun,screen_hours=excluded.screen_hours,energy=excluded.energy,note=excluded.note,revision=excluded.revision,updated=excluded.updated',tuple(payload.values())+(rev,stamp()))
            self._award(c,'life-upload:'+day,1,'如实上传生活数据（不是达标奖励）')
            self.db.emit(c,f'life:{day}:{rev}','life.recorded',{'day':day,'revision':rev})
        return self.daily(day)
    def daily(self,day=None):
        day=day or today();date.fromisoformat(day)
        with self.db.connect() as c:
            row=c.execute('SELECT l.*,d.sleep_start,d.sleep_end FROM daily_life l LEFT JOIN daily_life_details d ON l.day=d.day WHERE l.day=?',(day,)).fetchone();return dict(row) if row else {}
    @staticmethod
    def housework_credit(c,title,day,target):
        key=title.strip().casefold();old=c.execute('SELECT coins FROM housework_awards WHERE day=? AND title_key=?',(day,key)).fetchone()
        previous=old[0] if old else 0;used=c.execute('SELECT COALESCE(sum(coins),0) FROM housework_awards WHERE day=?',(day,)).fetchone()[0]
        delta=max(0,min(target-previous,12-used))
        c.execute('INSERT INTO housework_awards VALUES(?,?,?) ON CONFLICT(day,title_key) DO UPDATE SET coins=excluded.coins',(day,key,previous+delta))
        return delta
    def housework(self,title,key=None):
        title=str(title).strip()
        if not title or len(title)>120:raise ValueError('请填写简短的家务内容')
        # Same title/day is one completion regardless of caller idempotency key.
        rid=hashlib.sha256((today()+'|'+title.casefold()).encode()).hexdigest()
        with self.db.connect() as c:
            c.execute('BEGIN IMMEDIATE');old=c.execute('SELECT * FROM housework_records WHERE id=?',(rid,)).fetchone()
            if old:return dict(old)
            count=c.execute('SELECT count(*) FROM housework_records WHERE day=?',(today(),)).fetchone()[0];coins=self.housework_credit(c,title,today(),1 if count<5 else 0)
            c.execute('INSERT INTO housework_records VALUES(?,?,?,?,?)',(rid,title,today(),coins,stamp()));self._award(c,'housework:'+rid,coins,'housework:'+rid)
            self.db.emit(c,'housework:'+rid,'housework.completed',{'title':title,'day':today(),'coins':coins})
            return dict(id=rid,title=title,day=today(),coins=coins)
    def _energy(self,day):
        previous=(date.fromisoformat(day)-timedelta(days=1)).isoformat()
        prior=self.daily(previous);daily=prior or self.daily(day);work=study=0.0
        with self.db.connect() as c:
            if c.execute("SELECT 1 FROM sqlite_master WHERE name='activity_records'").fetchone():
                rows=c.execute('SELECT category,sum(seconds)/60 AS minutes FROM activity_records WHERE day=? GROUP BY category',(day,)).fetchall()
                work=sum(r['minutes'] for r in rows if r['category']=='工作');study=sum(r['minutes'] for r in rows if r['category']=='学习')
            exercise=c.execute('SELECT COALESCE(sum(minutes),0) FROM exercise_records WHERE day=?',(day,)).fetchone()[0]
        sleep=daily.get('sleep_hours');screen=daily.get('phone_total')/60 if daily.get('phone_total') is not None else daily.get('screen_hours');subjective=daily.get('energy')
        # Missing inputs are unknown: neutral anchors are explicit estimates, not evidence of health.
        physical=70 if subjective is None else subjective
        if sleep is not None:physical+=max(-35,min(10,(sleep-7)*8))
        physical-=min(30,exercise*.12);focus=physical-min(35,(work+study)/15)
        eye=min(100,screen*9) if screen is not None else min(100,(work+study)/60*6)
        with self.db.connect() as c:
            if c.execute("SELECT 1 FROM sqlite_master WHERE name='life_timers'").fetchone():
                for activity in c.execute("SELECT t.physical,t.focus,t.rest,d.effective FROM life_timers t JOIN life_timer_days d ON t.id=d.run_id WHERE d.day=? AND t.state='finished'",(day,)):
                    minutes=activity['effective']/60;sign=1 if activity['rest'] else -1
                    physical+=sign*min(20,minutes*{'low':.03,'medium':.08,'high':.15}[activity['physical']])
                    focus+=sign*min(25,minutes*{'low':.04,'medium':.1,'high':.2}[activity['focus']])
        clamp=lambda x:round(max(0,min(100,x)))
        hints=['这些数值是行为估计，不是医学测量；未记录不等于未完成。']
        if sleep is None:hints.append('睡眠未知，补记后估计更有参考价值。')
        if screen is None:hints.append('屏幕时长未知，视疲劳仅根据专注记录粗估。')
        if focus<45 or eye>=60:hints.append('可以先离屏休息，再决定是否继续；不会强制中断任务。')
        else:hints.append('可选择一段适量专注，并在结束后活动、远眺。')
        return dict(physical=clamp(physical),focus=clamp(focus),eye_strain=clamp(eye),confidence=f'已填写 {sum(v is not None for v in (sleep,screen,subjective))}/3 项恢复参考',suggestions=hints,work_minutes=work,study_minutes=study,exercise_minutes=exercise,day=day)
    def energy(self,day=None):
        day=day or today();result=self._energy(day);target=date.fromisoformat(day)
        caps=self.state.caps(day);result.update(caps);result['physical_value']=round(caps['physical_cap']*result['physical']/100,2);result['focus_value']=round(caps['focus_cap']*result['focus']/100,2);result['muscles']=self.state.muscles(day)
        result['trend']=[self._energy((target-timedelta(days=n)).isoformat()) for n in range(6,-1,-1)]
        return result
