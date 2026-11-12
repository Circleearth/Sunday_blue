"""Additive capacity snapshots, daily reporting cycles and conservative recovery hints."""
from datetime import datetime,date,timedelta,timezone
import json

ZONE=timezone(timedelta(hours=8))
MUSCLES={'胸':'胸','背':'背','肩':'肩','手臂':'手臂','核心':'核心','臀腿':'臀腿'}
class LifeState:
 def __init__(self,db):
  self.db=db
  with db.connect() as c:
   c.executescript('''CREATE TABLE IF NOT EXISTS vitality_state(id INTEGER PRIMARY KEY,cap REAL,last_settled TEXT);
    INSERT OR IGNORE INTO vitality_state VALUES(1,30,NULL);
    CREATE TABLE IF NOT EXISTS vitality_days(day TEXT PRIMARY KEY,physical_cap REAL,focus_cap REAL);
    CREATE TABLE IF NOT EXISTS exercise_growth(record_id TEXT PRIMARY KEY,coins INTEGER,gain REAL);
    CREATE TABLE IF NOT EXISTS daily_life_details(day TEXT PRIMARY KEY,sleep_start TEXT,sleep_end TEXT);
    CREATE TABLE IF NOT EXISTS exercise_details(record_id TEXT PRIMARY KEY,muscles TEXT);''')
 @staticmethod
 def growth(c,rid,coins,previous_coins=0):
  row=c.execute('SELECT * FROM exercise_growth WHERE record_id=?',(rid,)).fetchone();previous=row['coins'] if row else previous_coins;gain=row['gain'] if row else 0
  if coins==previous:return
  cap=c.execute('SELECT cap FROM vitality_state WHERE id=1').fetchone()[0]
  change=(coins-previous)*.12/(1+(cap-30)/30)**1.5 if coins>previous else -gain*(previous-coins)/max(previous,1)
  c.execute('UPDATE vitality_state SET cap=? WHERE id=1',(max(30,cap+change),))
  c.execute('INSERT INTO exercise_growth VALUES(?,?,?) ON CONFLICT(record_id) DO UPDATE SET coins=excluded.coins,gain=excluded.gain',(rid,coins,max(0,gain+change)))
  c.execute('UPDATE vitality_days SET physical_cap=? WHERE day=?',(max(30,cap+change),datetime.now(ZONE).date().isoformat()))
 def settle(self,now=None):
  now=now or datetime.now(ZONE);now=now.astimezone(ZONE)
  boundary=now.replace(hour=9,minute=30,second=0,microsecond=0)
  target=(now.date() if now>=boundary else now.date()-timedelta(days=1))
  with self.db.connect() as c:
   c.execute('BEGIN IMMEDIATE');row=c.execute('SELECT * FROM vitality_state WHERE id=1').fetchone();cap=row['cap']
   start=date.fromisoformat(row['last_settled'])+timedelta(days=1) if row['last_settled'] else target
   while start<=target:
    recent=c.execute('SELECT 1 FROM exercise_records WHERE day>=? AND day<? LIMIT 1',((start-timedelta(days=3)).isoformat(),start.isoformat())).fetchone()
    if not recent:cap=max(30,cap-(cap-30)*.008)
    c.execute('INSERT OR IGNORE INTO vitality_days VALUES(?,?,100)',(start.isoformat(),cap));start+=timedelta(days=1)
   if not row['last_settled'] or row['last_settled']<target.isoformat():c.execute('UPDATE vitality_state SET cap=?,last_settled=? WHERE id=1',(cap,target.isoformat()))
  return self.caps(now.date().isoformat())
 def caps(self,day):
  with self.db.connect() as c:
   row=c.execute('SELECT * FROM vitality_days WHERE day=?',(day,)).fetchone()
   current=c.execute('SELECT cap FROM vitality_state WHERE id=1').fetchone()[0]
  return dict(row) if row else dict(day=day,physical_cap=current if day==datetime.now(ZONE).date().isoformat() else 30,focus_cap=100)
 def report_cycle(self,now=None):
  now=(now or datetime.now(ZONE)).astimezone(ZONE);boundary=now.replace(hour=9,minute=30,second=0,microsecond=0)
  if now<boundary:boundary-=timedelta(days=1)
  key='life-report:'+boundary.date().isoformat();source=(boundary.date()-timedelta(days=1)).isoformat()
  with self.db.connect() as c:
   c.execute('BEGIN IMMEDIATE')
   c.execute("UPDATE reminder_occurrences SET qq_status='missed' WHERE schedule_id='life-report' AND id!=? AND qq_status IN ('pending','failed')",(key,))
   c.execute("INSERT OR IGNORE INTO reminder_occurrences VALUES(?,?,?,?,?,?)",(key,'life-report',boundary.isoformat(),f'生活上报：请补记 {source} 的睡眠、饮食与手机使用；今日状态属于 {boundary.date()}。','off','pending'))
   # Only confirmed pre-send failures can be retried. Uncertain sends stay visible for review.
   c.execute("UPDATE reminder_occurrences SET qq_status='pending' WHERE id=? AND qq_status='failed' AND NOT EXISTS(SELECT 1 FROM reminder_delivery_details d WHERE d.occurrence_id=? AND d.updated>?)",(key,key,(now-timedelta(minutes=5)).astimezone(timezone.utc).isoformat(timespec='seconds')))
 def muscles(self,day):
  previous=(date.fromisoformat(day)-timedelta(days=1)).isoformat();scores={k:0 for k in MUSCLES};known=set()
  with self.db.connect() as c:
   rows=c.execute('SELECT e.*,d.muscles FROM exercise_records e LEFT JOIN exercise_details d ON d.record_id=e.id WHERE e.day=?',(previous,)).fetchall()
  for row in rows:
   parts=json.loads(row['muscles'] or '[]')
   if not parts:parts={'足球':['臀腿','核心'],'快走':['臀腿'],'慢跑':['臀腿'],'羽毛球':['肩','手臂','臀腿'],'骑行':['臀腿']}.get(row['kind'],[])
   for part in parts:
    known.add(part);scores[part]+=row['minutes']*{'light':.5,'moderate':1,'high':1.5}[row['intensity']]
  return [{'part':p,'level':('unknown' if p not in known else 'red' if v>=75 else 'orange' if v>=45 else 'yellow' if v>=20 else 'green'),'load':v} for p,v in scores.items()]
