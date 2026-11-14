"""Private user-reported wellbeing facts; excluded from model reports by default."""
import json
from contextlib import nullcontext
from datetime import date,timedelta
from .database import stamp
from .life import number,valid_day
class PrivateWellbeing:
 def __init__(self,db):
  self.db=db
  with db.connect() as c:c.executescript('''CREATE TABLE IF NOT EXISTS private_wellbeing(day TEXT PRIMARY KEY,count INTEGER,minutes REAL,discomfort INTEGER,impact INTEGER,updated TEXT);
   CREATE TABLE IF NOT EXISTS private_wellbeing_revisions(id INTEGER PRIMARY KEY,day TEXT,before_json TEXT,created TEXT);''')
 def save(self,day,count,minutes,discomfort=False,impact=False,_connection=None):
  day=valid_day(day);count=number(count,0,100,'次数');minutes=number(minutes,0,1440,'总分钟')
  if count!=int(count):raise ValueError('次数必须是整数')
  count=int(count)
  if count==0 and minutes>0:raise ValueError('次数为0时总时间应为0')
  with (nullcontext(_connection) if _connection is not None else self.db.connect()) as c:
   if _connection is None:c.execute('BEGIN IMMEDIATE')
   if c.execute("SELECT 1 FROM sqlite_master WHERE name='daily_finalized'").fetchone() and c.execute('SELECT 1 FROM daily_finalized WHERE day=?',(day,)).fetchone():raise ValueError('该日上报已确认锁定')
   old=c.execute('SELECT * FROM private_wellbeing WHERE day=?',(day,)).fetchone()
   values=(count,minutes,int(discomfort),int(impact))
   if old and tuple(old[k] for k in ('count','minutes','discomfort','impact'))==values:return
   if old:c.execute('INSERT INTO private_wellbeing_revisions(day,before_json,created) VALUES(?,?,?)',(day,json.dumps(dict(old)),stamp()))
   c.execute('INSERT INTO private_wellbeing VALUES(?,?,?,?,?,?) ON CONFLICT(day) DO UPDATE SET count=excluded.count,minutes=excluded.minutes,discomfort=excluded.discomfort,impact=excluded.impact,updated=excluded.updated',(day,*values,stamp()))
 def get(self,day):
  with self.db.connect() as c:r=c.execute('SELECT * FROM private_wellbeing WHERE day=?',(day,)).fetchone();return dict(r) if r else {}
 def status(self,day=None):
  target=date.fromisoformat(day) if day else date.today();start=(target-timedelta(days=29)).isoformat();week=(target-timedelta(days=6)).isoformat();limit=self.db.get('private_control_reference',5)
  with self.db.connect() as c:rows=[dict(r) for r in c.execute('SELECT * FROM private_wellbeing WHERE day>=? AND day<=?',(start,target.isoformat()))]
  recent=[r for r in rows if r['day']>=week];count=sum(r['count'] for r in recent);ratio=count/max(limit,1)
  level='red' if any(r['discomfort'] or r['impact'] for r in recent) else 'red' if ratio>=1.5 else 'orange' if ratio>=1 else 'yellow' if ratio>=.5 else 'green'
  return {'level':level,'week_count':count,'month_count':sum(r['count'] for r in rows),'week_minutes':sum(r['minutes'] for r in recent),'limit':limit,'ratio':ratio,'daily_average':count/7,'recorded_days':len(rows),'note':('有不适或影响生活的自报：建议暂停、调整；持续不适请咨询专业人员。' if any(r['discomfort'] or r['impact'] for r in recent) else '已达到个人控制目标150%以上，建议暂停并安排其他活动。') if level=='red' else '超过个人参考目标，可回顾时间安排；次数本身不表示健康异常。' if level=='orange' else '接近个人参考目标，不是医学警戒线。' if level=='yellow' else '暂无已报告的不适或生活影响；未上报不等于没有发生。'}
