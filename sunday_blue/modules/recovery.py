"""Persistent recovery and pressure policy. Missing records never imply failure."""
import hashlib,json,time
from datetime import datetime
from .database import day,stamp

class Recovery:
    def __init__(self,db,clock=time.time):self.db=db;self.clock=clock
    def status(self):
        value=self.db.get('recovery_state',{});now=self.clock()
        value['active']=value.get('until',0)>now
        value['distressed']=value.get('mood_until',0)>now and value.get('mood') in ('tired','sad','irritable')
        return value
    def report(self,mood):
        if mood not in ('calm','tired','sad','irritable'):raise ValueError('请选择当前状态')
        value=self.db.get('recovery_state',{});value.update(mood=mood,mood_until=self.clock()+7200)
        self.db.set('recovery_state',value);return self.status()
    def fatigue(self):
        from .life import Life
        with self.db.connect() as c:
            if not c.execute("SELECT 1 FROM sqlite_master WHERE name='daily_life'").fetchone():return False
        life=Life.__new__(Life);life.db=self.db;state=life._energy(day())
        return state['physical']<40 or state['focus']<35 or state['eye_strain']>=70
    def protected(self):
        state=self.status()
        return state['active'] or state['distressed'] or (state.get('ready_until',0)<self.clock() and self.fatigue())
    def decision(self,urgent=False,known=True):
        if urgent:return 'allow'
        if not known:return 'ignore'
        return 'defer' if self.protected() else 'gentle'
    def end_work(self,minutes=60):
        if not isinstance(minutes,int) or isinstance(minutes,bool) or not 5<=minutes<=240:raise ValueError('恢复时长应为 5–240 分钟')
        from .work import Work
        work=Work(self.db)
        with self.db.connect() as c:
            rows=[dict(r) for r in c.execute("SELECT id,label,seconds FROM activity_records WHERE day=? AND category='工作' ORDER BY finished",(day(),))]
            changes=[dict(r) for r in c.execute("SELECT task_id,payload,created FROM work_history WHERE kind='updated' AND created>=?",((__import__('datetime').date.fromisoformat(day())-__import__('datetime').timedelta(days=1)).isoformat(),))]
        # Only actual progress changes today, not all-time completed tasks.
        progress=[]
        for r in changes:
            if datetime.fromisoformat(r['created']).astimezone().date().isoformat()!=day():continue
            p=json.loads(r['payload']);after=p.get('after',{})
            if 'progress' in after or after.get('status')=='done':progress.append({'task_id':r['task_id'],'before':p.get('before',{}),'after':after})
        snapshot={'day':day(),'minutes':round(sum(r['seconds'] for r in rows)/60,1),'segments':len(rows),'progress':progress[-20:],
                  'completed':[t['title'] for t in work.tasks(True) if t['status']=='done' and any(p['task_id']==t['id'] and p['after'].get('status')=='done' for p in progress)][:15]}
        key=hashlib.sha256(json.dumps([day(),[r['id'] for r in rows],progress],sort_keys=True).encode()).hexdigest()
        value=self.db.get('recovery_state',{})
        if value.get('settlement_key')==key:return value.get('summary',snapshot)
        value.update(until=self.clock()+minutes*60,ready_until=0,settlement_key=key,summary=snapshot,preference='rest')
        with self.db.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute('INSERT INTO module_settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',('recovery_state',json.dumps(value,ensure_ascii=False)))
            self.db.emit(c,'afterwork:'+key,'work.day_closed',snapshot)
        return snapshot
    def finish(self,preference='rest'):
        if preference not in ('rest','study','activity'):raise ValueError('请选择继续休息、学习或轻量活动')
        value=self.db.get('recovery_state',{});value.update(until=self.clock()+3600 if preference=='rest' else 0,preference=preference,ready_until=self.clock()+3600 if preference!='rest' else 0)
        self.db.set('recovery_state',value);return self.suggestion()
    def suggestion(self):
        s=self.status();hour=datetime.fromtimestamp(self.clock()).hour
        if s['active']:return '恢复时间里可以聊天或休息，不需要消费金币，也不需要补做打卡。'
        if s['distressed'] or self.fatigue() or hour>=22 or hour<7:return '现在更适合继续休息；白天的工作成果不会因此被否定。'
        return {'study':'如果你仍愿意，可以选一小段学习，随时可以停。','activity':'如果你愿意，可以散步或轻量活动，不追求强度。'}.get(s.get('preference'),'恢复时间结束也不代表必须继续努力；先按你的意愿休息。')
    def negative_allowed(self,key,known=True):
        if self.decision(known=known) in ('ignore','defer'):return False
        with self.db.connect() as c:
            c.execute('BEGIN IMMEDIATE');row=c.execute("SELECT value FROM module_settings WHERE key='negative_feedback_gate'").fetchone();v=json.loads(row[0]) if row else {}
            now=self.clock()
            if v.get('day')==day() and (v.get('count',0)>=1 or now-v.get('last',0)<21600 or v.get('key')==key):return False
            c.execute('INSERT INTO module_settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',('negative_feedback_gate',json.dumps({'day':day(),'count':1,'last':now,'key':key})))
        return True
    def context(self):
        state=self.status()
        if not state and not self.protected():return ''
        rule='恢复/疲劳保护：'+self.suggestion()+' 未记录不代表未完成；不因晚间未学习否定白天成果。'
        if self.protected():rule+=' 暂停非紧急催促、批评、调侃和扣分；正常聊天和情绪交流照常。'
        return rule
