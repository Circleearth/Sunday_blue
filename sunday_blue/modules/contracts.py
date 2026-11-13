"""Immutable signed challenges, evidence-based progress and capped virtual-only settlement."""
import json,uuid
from datetime import datetime,timezone,timedelta
from .database import stamp
from .life import number
from .notices import notify
METRICS={'study_minutes':'有效学习分钟','mastery':'新达到掌握的知识点','reviews':'通过复习次数','correct':'做题正确数','exercise_daily':'每日足额运动分钟','manual':'自主目标（逐次确认事实）'}
class Contracts:
 def __init__(self,db):
  self.db=db
  with db.connect() as c:
   c.executescript('''CREATE TABLE IF NOT EXISTS challenge_contracts(id TEXT PRIMARY KEY,title TEXT,metric TEXT,target REAL,signed TEXT,deadline TEXT,reward INTEGER,penalty INTEGER,terms TEXT,status TEXT,settled TEXT);
    CREATE TABLE IF NOT EXISTS challenge_ledger(id TEXT PRIMARY KEY,contract_id TEXT,amount INTEGER,reason TEXT,created TEXT);
    CREATE TABLE IF NOT EXISTS challenge_settlement_evidence(contract_id TEXT PRIMARY KEY,payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS challenge_logs(id TEXT PRIMARY KEY,contract_id TEXT,amount REAL,note TEXT,created TEXT);
   ''')
   c.execute("INSERT OR IGNORE INTO challenge_ledger VALUES('initial',NULL,100,'初始契约积分',?)",(stamp(),))
   c.execute("INSERT OR IGNORE INTO challenge_ledger VALUES('initial-exercise',NULL,100,'初始运动契约积分',?)",(stamp(),))
 def options(self):return {'single_cap':30,'daily_cap':60,'base_reward':10}|self.db.get('challenge_options',{})
 def configure(self,single,daily,reward):
  v={'single_cap':int(number(single,0,50,'单次上限')),'daily_cap':int(number(daily,0,100,'每日上限')),'base_reward':int(number(reward,0,30,'基础积分'))};self.db.set('challenge_options',v)
 def sign(self,title,metric,target,deadline,reward_multiple=1,penalty_multiple=1,reward_note='',penalty_note='',request_id=None):
  now=datetime.now(timezone.utc).replace(microsecond=0);end=datetime.fromisoformat(deadline)
  if end.tzinfo is None:raise ValueError('截止时间必须包含时区')
  end=end.astimezone(timezone.utc);title=str(title).strip()
  if not title or len(title)>150 or metric not in METRICS or not now<end<=now+timedelta(days=366):raise ValueError('请填写目标和未来一年内的截止时间')
  target=number(target,1,1440 if metric=='exercise_daily' else 100000,'目标量');rm=number(reward_multiple,0,3,'奖励倍率');pm=number(penalty_multiple,0,3,'惩罚倍率');o=self.options()
  reward=min(90,round(o['base_reward']*rm));penalty=min(o['single_cap'],round(o['base_reward']*pm));rid=request_id or uuid.uuid4().hex
  terms=o|{'reward_multiple':rm,'penalty_multiple':pm,'reward_note':str(reward_note)[:500],'penalty_note':str(penalty_note)[:500]}
  with self.db.connect() as c:
   c.execute('BEGIN IMMEDIATE')
   if c.execute('SELECT 1 FROM challenge_contracts WHERE id=?',(rid,)).fetchone():return rid
   if c.execute("SELECT count(*) FROM challenge_contracts WHERE status IN ('active','review')").fetchone()[0]>=10:raise ValueError('同时最多10份待处理契约')
   source={'study_minutes':'activity_records','mastery':'learning_mastery','reviews':'learning_reviews','correct':'learning_attempts','exercise_daily':'exercise_records'}.get(metric)
   terms['baseline_row']=c.execute(f'SELECT COALESCE(max(rowid),0) FROM {source}').fetchone()[0] if source else 0
   c.execute('INSERT INTO challenge_contracts VALUES(?,?,?,?,?,?,?,?,?,?,NULL)',(rid,title,metric,target,now.isoformat(),end.isoformat(),reward,penalty,json.dumps(terms,ensure_ascii=False),'active'))
   notify(c,'contract-sign:'+rid,'已签约：'+title+'。'+('运动' if metric=='exercise_daily' else '学习')+'契约；目标 '+str(target)+' '+METRICS[metric]+'；游戏积分奖励 '+str(reward)+' / 扣分最多 '+str(penalty)+'。',True)
  return rid
 @staticmethod
 def domain(r):return 'exercise' if r['metric']=='exercise_daily' else 'study'
 def exercise_days(self,c,r):
  if r['status'] not in ('active','review'):
   saved=c.execute('SELECT payload FROM challenge_settlement_evidence WHERE contract_id=?',(r['id'],)).fetchone()
   if saved:return json.loads(saved[0])['daily']
  from .life_state import ZONE
  first=datetime.fromisoformat(r['signed']).astimezone(ZONE).date();last=datetime.fromisoformat(r['deadline']).astimezone(ZONE).date()
  records={x['day']:x['minutes'] for x in c.execute('SELECT day,sum(minutes) AS minutes FROM exercise_records WHERE day>=? AND day<=? AND rowid>? GROUP BY day',(first.isoformat(),last.isoformat(),json.loads(r['terms']).get('baseline_row',0)))}
  return [{'day':(first+timedelta(days=n)).isoformat(),'minutes':records.get((first+timedelta(days=n)).isoformat(),0)} for n in range((last-first).days+1)]
 def progress(self,c,r):
  if r['status'] not in ('active','review'):
   saved=c.execute('SELECT payload FROM challenge_settlement_evidence WHERE contract_id=?',(r['id'],)).fetchone()
   if saved:return json.loads(saved[0])['progress']
  if r['metric']=='exercise_daily':return min((d['minutes'] for d in self.exercise_days(c,r)),default=0)

  args=(r['signed'],r['deadline'],json.loads(r['terms']).get('baseline_row',0))
  if r['metric']=='study_minutes':return c.execute("SELECT COALESCE(sum(seconds),0)/60 FROM activity_records WHERE category='学习' AND started>=? AND finished<=? AND rowid>?",args).fetchone()[0]
  if r['metric']=='mastery':return c.execute('SELECT count(*) FROM learning_mastery WHERE first_mastered>=? AND first_mastered<=? AND rowid>?',args).fetchone()[0]
  if r['metric']=='reviews':return c.execute('SELECT count(*) FROM learning_reviews WHERE passed=1 AND created>=? AND created<=? AND rowid>?',args).fetchone()[0]
  if r['metric']=='correct':return c.execute('SELECT COALESCE(sum(correct),0) FROM learning_attempts WHERE created>=? AND created<=? AND rowid>?',args).fetchone()[0]
  return c.execute('SELECT COALESCE(sum(amount),0) FROM challenge_logs WHERE contract_id=?',(r['id'],)).fetchone()[0]
 def rows(self):
  with self.db.connect() as c:return [dict(r)|{'progress':self.progress(c,r),'domain':self.domain(r),'exercise_days':self.exercise_days(c,r) if r['metric']=='exercise_daily' else []} for r in c.execute('SELECT * FROM challenge_contracts ORDER BY signed DESC')]
 @staticmethod
 def ledger_filter(domain):
  return "(l.id='initial-exercise' OR t.metric='exercise_daily')" if domain=='exercise' else "(l.id='initial' OR (t.id IS NOT NULL AND t.metric<>'exercise_daily'))"
 def balance(self,domain='study'):
  if domain not in ('study','exercise'):raise ValueError('未知契约积分类型')
  with self.db.connect() as c:return c.execute('SELECT COALESCE(sum(l.amount),0) FROM challenge_ledger l LEFT JOIN challenge_contracts t ON t.id=l.contract_id WHERE '+self.ledger_filter(domain)).fetchone()[0]
 def log(self,rid,amount,note,request_id=None):
  amount=number(amount,.01,100000,'完成量');note=str(note).strip()
  if not note or len(note)>2000:raise ValueError('请简述实际完成的事实')
  with self.db.connect() as c:
   c.execute('BEGIN IMMEDIATE')
   if request_id:
    previous=c.execute('SELECT * FROM challenge_logs WHERE id=?',(request_id,)).fetchone()
    if previous:
     if previous['contract_id']!=rid or previous['amount']!=amount or previous['note']!=note:raise ValueError('重复请求内容不一致')
     return
   r=c.execute('SELECT * FROM challenge_contracts WHERE id=?',(rid,)).fetchone()
   if not r or r['status']!='active' or r['metric']!='manual' or datetime.now(timezone.utc)>datetime.fromisoformat(r['deadline']):raise ValueError('只有未到期的自主目标可以补充进展')
   if amount>max(0,r['target']-self.progress(c,r)):raise ValueError('本次完成量超过剩余目标')
   c.execute('INSERT OR IGNORE INTO challenge_logs VALUES(?,?,?,?,?)',(request_id or uuid.uuid4().hex,rid,amount,note,stamp()))
  self.tick()
 def _settle(self,c,r,status):
  if r['status'] not in ('active','review'):return
  amount=r['reward'] if status=='success' else 0
  if status in ('failed','cancelled'):
   from .life_state import ZONE
   start=datetime.now(ZONE).replace(hour=0,minute=0,second=0,microsecond=0).astimezone(timezone.utc).isoformat()
   scope=self.ledger_filter(self.domain(r))
   spent=c.execute('SELECT COALESCE(-sum(l.amount),0) FROM challenge_ledger l LEFT JOIN challenge_contracts t ON t.id=l.contract_id WHERE '+scope+' AND l.amount<0 AND l.created>=?',(start,)).fetchone()[0]
   balance=c.execute('SELECT COALESCE(sum(l.amount),0) FROM challenge_ledger l LEFT JOIN challenge_contracts t ON t.id=l.contract_id WHERE '+scope).fetchone()[0];cap=min(100,json.loads(r['terms'])['daily_cap'])
   amount=-min(r['penalty'],max(0,cap-spent),max(0,balance))
  c.execute('INSERT OR IGNORE INTO challenge_settlement_evidence VALUES(?,?)',(r['id'],json.dumps({'progress':self.progress(c,r),'daily':self.exercise_days(c,r) if r['metric']=='exercise_daily' else []})))
  c.execute('INSERT OR IGNORE INTO challenge_ledger VALUES(?,?,?,?,?)',('settle:'+r['id'],r['id'],amount,status,stamp()))
  c.execute('UPDATE challenge_contracts SET status=?,settled=? WHERE id=?',(status,stamp(),r['id']))
  for prefix in ('contract-sign:','contract-due:','contract-daily:'):
   for channel in ('local','qq'):c.execute(f"UPDATE reminder_occurrences SET {channel}_status='missed' WHERE id LIKE ? AND {channel}_status IN ('pending','failed')",(prefix+r['id']+'%',))
  self.db.emit(c,'contract-settle:'+r['id'],'challenge.settled',{'id':r['id'],'status':status,'points':amount,'domain':self.domain(r)})
  notify(c,'contract-result:'+r['id'],r['title']+' · '+{'success':'已达成','failed':'已核对未达成','cancelled':'主动解约'}[status]+f'；{"运动" if self.domain(r)=="exercise" else "学习"}契约积分 {amount:+d}。不涉及金币或现实预算。',True)
 def resolve(self,rid,cancel=False):
  with self.db.connect() as c:
   c.execute('BEGIN IMMEDIATE');r=c.execute('SELECT * FROM challenge_contracts WHERE id=?',(rid,)).fetchone()
   if not r:raise ValueError('契约不存在')
   if r['status'] not in ('active','review'):return
   if not cancel and datetime.now(timezone.utc)<datetime.fromisoformat(r['deadline']):raise ValueError('契约还未到期')
   self._settle(c,r,'success' if self.progress(c,r)>=r['target'] else 'cancelled' if cancel else 'failed')
 def tick(self,now=None):
  now=now or datetime.now(timezone.utc)
  from .life_state import ZONE
  with self.db.connect() as c:
   c.execute('BEGIN IMMEDIATE')
   for channel in ('local','qq'):c.execute(f"UPDATE reminder_occurrences SET {channel}_status='missed' WHERE id LIKE 'contract-%' AND due<? AND {channel}_status IN ('pending','failed')",((now-timedelta(days=1)).isoformat(),))
   for r in c.execute("SELECT * FROM challenge_contracts WHERE status IN ('active','review')").fetchall():
    if self.progress(c,r)>=r['target']:self._settle(c,r,'success');continue
    if datetime.fromisoformat(r['deadline'])<=now:
     c.execute("UPDATE challenge_contracts SET status='review' WHERE id=?",(r['id'],));notify(c,'contract-due:'+r['id'],r['title']+' 已到期，记录未显示达标。请先核对；不会因缺少记录自动扣分。',True)
    elif now.astimezone(ZONE).hour>=18:
     notify(c,'contract-daily:'+r['id']+':'+now.astimezone(ZONE).date().isoformat(),r['title']+f" · 当前 {self.progress(c,r):g}/{r['target']:g}；截止 "+datetime.fromisoformat(r['deadline']).astimezone(ZONE).strftime('%m-%d %H:%M'),True)
