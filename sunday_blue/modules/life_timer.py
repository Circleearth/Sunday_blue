"""Persistent pause-safe activity clock; mutually exclusive with active focus."""
import time,uuid
from datetime import datetime,timedelta
from .database import stamp,day
from .life import number
class LifeTimer:
 def __init__(self,db,clock=time.monotonic):
  self.db=db;self.clock=clock;self.anchor=None
  with db.connect() as c:
   c.executescript('''CREATE TABLE IF NOT EXISTS life_timers(id TEXT PRIMARY KEY,title TEXT,state TEXT,started TEXT,finished TEXT,elapsed REAL,effective REAL,physical TEXT,focus TEXT,rest INTEGER,day TEXT);
   CREATE TABLE IF NOT EXISTS life_timer_days(run_id TEXT,day TEXT,seconds REAL,effective REAL,PRIMARY KEY(run_id,day));
   CREATE UNIQUE INDEX IF NOT EXISTS one_life_timer ON life_timers((1)) WHERE state IN ('running','paused');''')
   c.execute("UPDATE life_timers SET state='paused' WHERE state='running'")
 def status(self):
  with self.db.connect() as c:row=c.execute("SELECT * FROM life_timers WHERE state IN ('running','paused')").fetchone()
  return dict(row) if row else {'state':'idle','elapsed':0}
 @staticmethod
 def no_focus(c):
  if c.execute("SELECT 1 FROM sqlite_master WHERE name='focus_runs'").fetchone() and c.execute("SELECT 1 FROM focus_runs WHERE state='running'").fetchone():raise ValueError('请先暂停番茄钟，避免同一时间重复统计')
 def start(self,title):
  title=str(title).strip()
  if not title or len(title)>120:raise ValueError('请填写活动名称（120字内）')
  with self.db.connect() as c:
   c.execute('BEGIN IMMEDIATE');self.no_focus(c)
   if c.execute("SELECT 1 FROM life_timers WHERE state IN ('running','paused')").fetchone():raise ValueError('已有活动，请先结束')
   c.execute('INSERT INTO life_timers VALUES(?,?,?, ?,NULL,0,NULL,NULL,NULL,0,?)',(uuid.uuid4().hex,title,'running',stamp(),day()))
  self.anchor=self.clock()
  from .attention import Attention
  Attention(self.db).configure({'mode':'auto'})
 def checkpoint(self):
  state=self.status()
  if state['state']!='running':return
  now=self.clock();delta=max(0,now-self.anchor) if self.anchor is not None else 0;self.anchor=now
  with self.db.connect() as c:
   if delta>30:c.execute("UPDATE life_timers SET state='paused' WHERE id=?",(state['id'],));self.anchor=None
   else:
    c.execute('UPDATE life_timers SET elapsed=elapsed+? WHERE id=?',(delta,state['id']))
    end=datetime.now().astimezone();start=end-timedelta(seconds=delta)
    while start<end:
     midnight=(start+timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0);stop=min(end,midnight);seconds=(stop-start).total_seconds()
     c.execute('INSERT INTO life_timer_days VALUES(?,?,?,0) ON CONFLICT(run_id,day) DO UPDATE SET seconds=seconds+excluded.seconds',(state['id'],start.date().isoformat(),seconds));start=stop
 def pause(self):
  self.checkpoint()
  with self.db.connect() as c:c.execute("UPDATE life_timers SET state='paused' WHERE state='running'")
  self.anchor=None
 def resume(self):
  with self.db.connect() as c:
   c.execute('BEGIN IMMEDIATE');self.no_focus(c)
   c.execute("UPDATE life_timers SET state='running' WHERE state='paused'")
  self.anchor=self.clock()
  from .attention import Attention
  Attention(self.db).configure({'mode':'auto'})
 def finish(self,effective,physical='low',focus='low',rest=False):
  self.pause();state=self.status()
  if state['state']=='idle':raise ValueError('没有进行中的活动')
  effective=number(effective,0,state['elapsed']+.01,'有效秒数')
  if physical not in ('low','medium','high') or focus not in ('low','medium','high'):raise ValueError('消耗强度无效')
  with self.db.connect() as c:
   c.execute('BEGIN IMMEDIATE')
   c.execute("UPDATE life_timers SET state='finished',finished=?,effective=?,physical=?,focus=?,rest=? WHERE id=? AND state='paused'",(stamp(),effective,physical,focus,int(rest),state['id']))
   c.execute('UPDATE life_timer_days SET effective=seconds*? WHERE run_id=?',(effective/max(state['elapsed'],.001),state['id']))
   self.db.emit(c,'life-timer:'+state['id'],'life.activity',{'id':state['id'],'day':state['day'],'effective':effective,'rest':bool(rest)})
 def history(self):
  with self.db.connect() as c:return [dict(r) for r in c.execute("SELECT * FROM life_timers WHERE state='finished' ORDER BY started DESC LIMIT 100")]
