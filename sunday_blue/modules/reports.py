"""Idempotent report snapshots and bounded asynchronous role commentary."""
import calendar,hashlib,json,threading
from datetime import date,datetime,timedelta
from PySide6.QtCore import QObject,Signal
from .database import stamp
from .life_state import ZONE
from ..models import RoleProvider
from ..personas import read_persona
from ..storage import plain
FALLBACK='晕乎乎，今天不评价了。'

def previous_month_end(d):return d.replace(day=1)-timedelta(days=1)
def period_window(kind,today):
 if kind=='week':
  end=today-timedelta(days=(today.weekday()+1)%7);return end-timedelta(days=7),end
 if kind=='month':
  last=today.replace(day=calendar.monthrange(today.year,today.month)[1]);end=last if today==last else previous_month_end(today);return previous_month_end(end),end
 end=date(today.year,12,31) if today.month==12 and today.day==31 else date(today.year-1,12,31);return date(end.year-1,12,31),end

class Reports(QObject):
 ready=Signal(str)
 def __init__(self,hub):
  super().__init__(hub);self.hub=hub;self.db=hub.db;self.busy=False;self.cancel=threading.Event();hub.closed.connect(self.close)
  with self.db.connect() as c:
   c.executescript('''CREATE TABLE IF NOT EXISTS settlement_reports(id TEXT PRIMARY KEY,kind TEXT,start TEXT,end TEXT,digest TEXT,body TEXT,comment TEXT,state TEXT,updated TEXT);''');c.execute("UPDATE settlement_reports SET state='queued' WHERE state='running'")
 def snapshot(self,start,end):
  with self.db.connect() as c:
   records=[dict(r) for r in c.execute('SELECT category,label,seconds,day,id FROM activity_records WHERE day>=? AND day<? ORDER BY day',(start,end))]
   life=[dict(r) for r in c.execute('SELECT day,sleep_hours,meal,phone_total,phone_fun FROM daily_life WHERE day>=? AND day<? ORDER BY day',(start,end))]
   exercise=[dict(r) for r in c.execute('SELECT day,kind,minutes FROM exercise_records WHERE day>=? AND day<?',(start,end))]
   coins=c.execute("SELECT COALESCE(sum(amount),0) FROM coin_ledger WHERE reason IN (SELECT 'focus:'||id FROM activity_records WHERE day>=? AND day<?) OR reason IN (SELECT 'study-first:'||day FROM activity_records WHERE day>=? AND day<?)",(start,end,start,end)).fetchone()[0]
   other_coins=c.execute("SELECT COALESCE(sum(amount),0) FROM coin_ledger WHERE reason IN (SELECT 'exercise:'||id FROM exercise_records WHERE day>=? AND day<?) OR reason IN (SELECT 'housework:'||id FROM housework_records WHERE day>=? AND day<?) OR id IN (SELECT 'life-upload:'||day FROM daily_life WHERE day>=? AND day<?)",(start,end,start,end,start,end)).fetchone()[0]
   points=c.execute("SELECT COALESCE(sum(amount),0) FROM work_points WHERE id IN (SELECT 'work:'||id FROM activity_records WHERE day>=? AND day<?)",(start,end)).fetchone()[0]
   contracts=[dict(r) for r in c.execute("SELECT t.title,t.metric,t.status,l.amount,date(l.created,'+8 hours') AS day FROM challenge_ledger l JOIN challenge_contracts t ON t.id=l.contract_id WHERE date(l.created,'+8 hours')>=? AND date(l.created,'+8 hours')<?",(start,end))]
   progress=[dict(r) for r in c.execute('SELECT l.title,a.day,l.progress_start,t.progress FROM focus_task_links l JOIN activity_records a ON a.id=l.run_id LEFT JOIN work_tasks t ON t.id=l.task_id WHERE a.day>=? AND a.day<?',(start,end))]
  totals={k:round(sum(r['seconds']/60 for r in records if r['category']==k),1) for k in ('工作','学习','家务')}
  payload={'contracts':contracts,'start_inclusive':start,'end_exclusive':end,'minutes':totals,'focus_coins':coins,'life_coins':other_coins,'total_activity_coins':coins+other_coins,'work_points':points,'records':records[-60:],'daily':life[-366:],'exercise':exercise[-60:],'tasks_current_progress_not_historical':progress[-30:],'record_count':len(records),'private_records':'excluded'}
  return payload
 def prepare(self,kind,start,end):
  if not start<end:raise ValueError('报告区间无效')
  payload=self.snapshot(start,end);raw=json.dumps(payload,ensure_ascii=False,sort_keys=True);digest=hashlib.sha256(raw.encode()).hexdigest();rid=f'{kind}:{start}:{end}'
  title={'day':'日结算','week':'周报','month':'月报','year':'年报'}[kind]
  lines=[f'{title}｜{start} 至 {(date.fromisoformat(end)-timedelta(days=1)).isoformat()}',f"工作 {payload['minutes']['工作']} 分钟 · 学习 {payload['minutes']['学习']} 分钟 · 家务 {payload['minutes']['家务']} 分钟",f"专注金币 {payload['focus_coins']} · 生活/运动金币 {payload['life_coins']} · 合计获得 {payload['total_activity_coins']} 金币 · 工作积分 {payload['work_points']}（不是任务完成度）"]
  lines+=[f"{r['day']} {r['category']} · {r['label'] or '未命名'} · {r['seconds']/60:.1f} 分钟" for r in payload['records']]
  lines+=[f"{r['day']} 睡眠 {r['sleep_hours'] if r['sleep_hours'] is not None else '未报'}h · 手机 {r['phone_total'] if r['phone_total'] is not None else '未报'} 分 · 娱乐 {r['phone_fun'] if r['phone_fun'] is not None else '未报'} 分" for r in payload['daily']]
  lines+=[f"饮食：{r['day']} {r['meal'][:160]}" for r in payload['daily'] if r['meal']]
  lines+=[f"运动：{r['day']} {r['kind']} {r['minutes']} 分钟" for r in payload['exercise']]
  lines+=[f"任务：{r['title']}，开始时 {r['progress_start']}%，目前 {r['progress']}%（非历史快照）" for r in payload['tasks_current_progress_not_historical']]
  lines+=[f"契约：{r['day']} {r['title']} · {'运动' if r['metric']=='exercise_daily' else '学习'}契约积分 {r['amount']:+d} · {dict(success='已达成',failed='核对未达成',cancelled='已解约').get(r['status'],r['status'])}" for r in payload['contracts']]
  lines+=['私人性活动记录不包含在复制文本或模型输入中。','记录缺失不等于没有完成；长区间细目仅展示最近60条，时长汇总涵盖全部。']
  body='\n'.join(lines)
  with self.db.connect() as c:
   old=c.execute('SELECT digest FROM settlement_reports WHERE id=?',(rid,)).fetchone()
   if old and old['digest']==digest:return rid
   c.execute("INSERT INTO settlement_reports VALUES(?,?,?,?,?,?,?,'queued',?) ON CONFLICT(id) DO UPDATE SET digest=excluded.digest,body=excluded.body,comment='',state='queued',updated=excluded.updated",(rid,kind,start,end,digest,body,'',stamp()))
  self.ready.emit(rid);return rid
 def daily(self,day):
  target=date.fromisoformat(day)
  if target>=datetime.now(ZONE).date():raise ValueError('完整日结算仅针对已经结束的日期')
  state=self.hub.focus.status()
  if state['state']!='idle' and datetime.fromisoformat(state['started']).astimezone(ZONE).date()==target:
   self.hub.db.set('focus_loop',{});self.hub.focus.finish(record_day=day)
  rid=self.prepare('day',day,(target+timedelta(days=1)).isoformat());self.last_check=None;self.due();self.pump();return rid
 def due(self,today=None):
  today=today or datetime.now(ZONE).date()
  if getattr(self,'last_check',None)==today:return
  self.last_check=today
  for kind in ('week','month','year'):
   start,end=period_window(kind,today);data=self.snapshot(start.isoformat(),end.isoformat())
   if data['record_count'] or data['daily'] or data['exercise'] or data['contracts']:self.prepare(kind,start.isoformat(),end.isoformat())
 def get(self,rid):
  with self.db.connect() as c:
   row=c.execute('SELECT * FROM settlement_reports WHERE id=?',(rid,)).fetchone();return dict(row) if row else None
 def rows(self):
  with self.db.connect() as c:return [dict(r) for r in c.execute('SELECT * FROM settlement_reports ORDER BY end DESC,kind LIMIT 500')]
 def pump(self):
  if self.busy or self.cancel.is_set():return
  with self.db.connect() as c:r=c.execute("SELECT * FROM settlement_reports WHERE state='queued' ORDER BY updated LIMIT 1").fetchone()
  if not r:return
  r=dict(r);budget=self.db.get('report_model_budget',{});today=datetime.now(ZONE).date().isoformat()
  if budget.get('day')!=today:budget={'day':today,'calls':0}
  if budget['calls']>=12:return
  budget['calls']+=1;self.db.set('report_model_budget',budget);self.busy=True
  with self.db.connect() as c:c.execute("UPDATE settlement_reports SET state='running' WHERE id=? AND digest=?",(r['id'],r['digest']))
  role=next((s['role_id'] for s in self.hub.duties.slots() if s['id']=='director' and s['role_id']),None)
  config=self.hub.config.snapshot()
  def work():
   state='done'
   try:
    if not role:raise ValueError('No director')
    provider=RoleProvider(self.hub.root,role,config,self.cancel,purpose='settlement_report');provider.config['stream']=False;provider.config['thinking_budget']=0;provider.config.pop('reasoning_effort',None);provider.config['request_timeout']=(5,45)
    if not provider.config.get('model'):raise ValueError('No model')
    system='你是用户熟悉的总负责人。'+ '\n'.join(k+':'+v[:500] for k,v in read_persona(self.hub.root,role).items())+'\n依据报告做具体自然评价，不提问、不编造成果、不将投入时长当任务完成度。关键词：真实投入、知识掌握、工作推进、恢复、可持续节奏。先认可已有成果，再给一条简短建议。日评80字以内；周期报告按成果、规律、调整三段，500字内。不把估算当医学事实。'
    blocks,_,_=provider.complete(system,[{'role':'user','content':r['body'][:18000]}],max_tokens=400 if r['kind']=='day' else 1800);text=plain(blocks).strip()
    if not text:raise ValueError('Empty')
   except Exception:text=FALLBACK;state='fallback'
   try:
    if self.cancel.is_set():return
    with self.db.connect() as c:c.execute('UPDATE settlement_reports SET comment=?,state=?,updated=? WHERE id=? AND digest=?',(text,state,stamp(),r['id'],r['digest']))
    if not self.cancel.is_set():self.ready.emit(r['id'])
   finally:self.busy=False
  threading.Thread(target=work,daemon=True,name='settlement-report').start()
 def close(self):self.cancel.set()
