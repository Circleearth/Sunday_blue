"""One structured official-Dida tool, with reviewed targets and durable operation keys."""
import hashlib,json
from datetime import datetime,timezone,timedelta
from .dida import Dida
from .database import ModuleDB,stamp
ZONE=timezone(timedelta(hours=8))
SCHEMA={'name':'dida_task','description':'滴答官方任务操作。先 list/get 核对任务ID、名称、etag。所有写入展示确认，不使用模糊标题删除。due/start 用明确 ISO日期或日期时间（北京时间）；repeat 为 {frequency:daily|weekly|monthly,interval:整数,weekdays:[MO,...]}；一次任务 repeat:null。remind_minutes 是提前分钟列表，0表示准时。未提供字段保持不变，不自行编造。','input_schema':{'type':'object','properties':{'action':{'type':'string','enum':['list','get','create','update','complete','delete']},'task_id':{'type':'string'},'expected_title':{'type':'string'},'expected_etag':{'type':'string'},'fields':{'type':'object','properties':{'title':{'type':'string'},'content':{'type':['string','null']},'project_id':{'type':'string'},'start':{'type':['string','null']},'due':{'type':['string','null']},'repeat':{'type':['object','null']},'remind_minutes':{'type':'array','items':{'type':'integer'}},'priority':{'type':'integer','enum':[0,1,3,5]}},'additionalProperties':False}},'required':['action'],'additionalProperties':False}}

def normalize(fields,creating=False):
 if not isinstance(fields,dict) or set(fields)-set(SCHEMA['input_schema']['properties']['fields']['properties']):raise ValueError('未知任务字段')
 out={}
 for key in ('title','content','project_id','priority'):
  if key in fields:out[{'project_id':'projectId'}.get(key,key)]=fields[key]
 if creating and not str(out.get('title','')).strip():raise ValueError('任务名称不能为空')
 if 'title' in out and (not isinstance(out['title'],str) or not out['title'].strip() or len(out['title'])>500):raise ValueError('任务名称无效')
 if 'priority' in out and (type(out['priority'])!=int or out['priority'] not in (0,1,3,5)):raise ValueError('优先级无效')
 for key,name in [('start','startDate'),('due','dueDate')]:
  if key not in fields:continue
  value=fields[key]
  if value is None:out[name]=None;continue
  parsed=datetime.fromisoformat(value)
  if parsed.tzinfo is None:parsed=parsed.replace(tzinfo=ZONE)
  out[name]=parsed.astimezone(ZONE).isoformat();out['timeZone']='Asia/Shanghai';out['isAllDay']=len(value)==10
 if out.get('startDate') and out.get('dueDate') and out['startDate']>out['dueDate']:raise ValueError('截止时间早于开始时间')
 if 'repeat' in fields:
  repeat=fields['repeat']
  if repeat is None:out['repeatFlag']=None
  else:
   freq=repeat.get('frequency');interval=repeat.get('interval',1);days=repeat.get('weekdays',[])
   if freq not in ('daily','weekly','monthly') or type(interval)!=int or not 1<=interval<=365:raise ValueError('循环规则无效')
   if set(repeat)-{'frequency','interval','weekdays'} or any(x not in ['MO','TU','WE','TH','FR','SA','SU'] for x in days):raise ValueError('循环星期无效')
   if days and freq!='weekly':raise ValueError('仅每周循环可指定星期')
   out['repeatFlag']='RRULE:FREQ='+freq.upper()+';INTERVAL='+str(interval)+(';BYDAY='+','.join(dict.fromkeys(days)) if days else '')
 if 'remind_minutes' in fields:
  values=fields['remind_minutes']
  if not isinstance(values,list) or len(values)>5 or any(type(v)!=int or not 0<=v<=43200 for v in values):raise ValueError('提醒提前分钟无效（最多5项，0–43200）')
  out['reminders']=['TRIGGER:PT0S' if v==0 else 'TRIGGER:-PT'+str(v)+'M' for v in dict.fromkeys(values)]
 if creating:
  out.setdefault('repeatFlag',None)  # Override account defaults: a plain task is single occurrence.
  if out.get('dueDate') and not out.get('startDate'):out['startDate']=out['dueDate']
 return out

def dispatch(root,action,task_id='',expected_title='',expected_etag=None,fields=None,approve=None,source=''):
 db=ModuleDB(root);service=Dida(db)
 if action=='list':return {'items':service.tasks(),'note':'本地最近同步结果；get 获取远端当前版本'}
 client=service.client()
 if action=='get':return client.call('get_task_by_id',{'task_id':task_id})
 if action not in ('create','update','complete','delete'):raise ValueError('未知操作')
 payload=normalize(fields or {},action=='create');task=None
 if action!='create':
  task=client.call('get_task_by_id',{'task_id':task_id});service.normalize(task)
  if task['id']!=task_id or not expected_title or task['title']!=expected_title or expected_etag is None or (task.get('etag') or '')!=expected_etag:raise ValueError('任务或版本不匹配，请先 get 查看后再操作')
  if payload.get('projectId',task['projectId'])!=task['projectId']:raise ValueError('本工具暂不移动任务清单，请保留原 project_id')
  if action=='update' and not payload:raise ValueError('没有需要修改的字段')
 if payload.get('reminders') and not (payload.get('startDate') or payload.get('dueDate') or (task or {}).get('startDate') or (task or {}).get('dueDate')):raise ValueError('提醒必须关联具体日期时间')
 if payload.get('repeatFlag') and not (payload.get('dueDate') or payload.get('startDate') or (task or {}).get('dueDate')):raise ValueError('循环任务需要开始或截止日期')
 key=hashlib.sha256(json.dumps([source,action,task_id,payload],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
 with db.connect() as c:
  c.execute('CREATE TABLE IF NOT EXISTS dida_write_ops(id TEXT PRIMARY KEY,state TEXT,result TEXT,created TEXT)')
  previous=c.execute('SELECT * FROM dida_write_ops WHERE id=?',(key,)).fetchone()
  if previous:
   if previous['state']=='confirmed':return json.loads(previous['result'])
   raise ValueError('此操作曾提交且结果未确认，请先同步核对；不会自动重试')
 if not approve or not approve('滴答任务 '+action,expected_title or payload.get('title',''),json.dumps({'before':task,'changes':payload},ensure_ascii=False,indent=2)):return {'status':'denied'}
 if task:
  fresh=client.call('get_task_by_id',{'task_id':task_id})
  if any(fresh.get(k)!=task.get(k) for k in ('etag','title','dueDate','status','projectId')):raise ValueError('确认期间任务发生变化，请重新读取')
 with db.connect() as c:
  c.execute('BEGIN IMMEDIATE')
  if c.execute('SELECT 1 FROM dida_write_ops WHERE id=?',(key,)).fetchone():raise ValueError('操作已提交，请核对状态')
  c.execute('INSERT INTO dida_write_ops VALUES(?,?,?,?)',(key,'pending','',stamp()))
 try:
  if action=='create':result=client.call('create_task',{'task':payload,'client_timezone':'Asia/Shanghai'})
  elif action=='update':result=client.call('update_task',{'task_id':task_id,'task':payload|{'id':task_id,'projectId':task['projectId'],'etag':expected_etag},'client_timezone':'Asia/Shanghai'})
  elif action=='complete':result={'message':service.complete(task_id,task.get('dueDate') or '',expected_etag)}
  else:
   receipt=client.call('delete_task',{'project_id':task['projectId'],'task_id':task_id})
   if not isinstance(receipt,dict) or receipt.get('deleted')!=task_id:raise ValueError('删除回执未确认，请同步核对')
   result={'status':'deleted','id':task_id}
   service.ingest([service.normalize(task)|{'status':-1}])
  if action in ('create','update'):
   normalized=service.normalize(result)
   if action=='update' and normalized['id']!=task_id:raise ValueError('回执任务不匹配')
   service.ingest([normalized]);service.remember_meta([result])
  with db.connect() as c:c.execute("UPDATE dida_write_ops SET state='confirmed',result=? WHERE id=?",(json.dumps(result,ensure_ascii=False),key))
  return result
 except Exception:
  with db.connect() as c:c.execute("UPDATE dida_write_ops SET state='unconfirmed' WHERE id=?",(key,))
  raise
