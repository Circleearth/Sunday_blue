from datetime import timedelta
import hashlib
from .database import day as living_day
from datetime import datetime
from .life_state import ZONE
from .database import stamp,record_interval

def record(db,category,node,start,end):
 a=datetime.fromisoformat(start);b=datetime.fromisoformat(end)
 if a.tzinfo is None or b.tzinfo is None:raise ValueError('时间需包含时区')
 seconds=(b-a).total_seconds()
 if category not in ('工作','学习') or seconds<=120 or seconds>43200 or b>datetime.now(ZONE):raise ValueError('请选择同一天内已结束的实际时间段，超过2分钟且不超过12小时')
 key='manual:'+hashlib.sha256((category+node+start+end).encode()).hexdigest()
 with db.connect() as c:
  c.execute('BEGIN IMMEDIATE')
  if c.execute('SELECT 1 FROM activity_records WHERE id=?',(key,)).fetchone():return key
  for r in c.execute('SELECT started,finished FROM activity_records'):
   if datetime.fromisoformat(r['started'])<b and datetime.fromisoformat(r['finished'])>a:raise ValueError('与已有活动时间重叠，请核对后补报')
  if c.execute("SELECT 1 FROM focus_runs WHERE state IN ('running','paused')").fetchone():raise ValueError('请先结束正在进行的专注')
  table='work_tasks' if category=='工作' else 'learning_nodes';r=c.execute('SELECT * FROM '+table+' WHERE id=?',(node,)).fetchone()
  if not r:raise ValueError('关联项目不存在')
  if category=='学习' and r['kind']!='unit':raise ValueError('请选择知识点')
  day=living_day(a);c.execute('INSERT INTO activity_records VALUES(?,?,?,?,?,?,?,?)',(key,category,'[补报] '+r['title'],None,seconds,day,start,end))
  record_interval(c,key,a,b)
  if category=='工作':
   c.execute('INSERT INTO focus_task_links VALUES(?,?,?,?)',(key,node,r['title'],r['progress']));c.execute('INSERT INTO work_points VALUES(?,?,?,?)',('work:'+key,int(seconds//60),'work:'+key,stamp()))
  else:c.execute('INSERT INTO learning_focus_links VALUES(?,?)',(key,node))
  db.emit(c,key,'activity.backfilled',{'id':key,'category':category,'day':day,'seconds':seconds})
 return key
