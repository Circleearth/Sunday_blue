"""Local spaced repetition, linked to existing knowledge and error IDs."""
from datetime import date,timedelta
from .database import stamp
class ReviewPlan:
 def __init__(self,db):
  self.db=db
  with db.connect() as c:c.executescript("CREATE TABLE IF NOT EXISTS review_plan(id TEXT PRIMARY KEY,unit TEXT,error TEXT,due TEXT,interval INTEGER,stage INTEGER); CREATE TABLE IF NOT EXISTS review_attempts(id INTEGER PRIMARY KEY,card TEXT,rating TEXT,day TEXT,next_due TEXT,created TEXT);")
 def add(self,unit,error=''):
  key=unit+':'+error
  with self.db.connect() as c:
   if not c.execute("SELECT 1 FROM learning_nodes WHERE id=? AND kind='unit'",(unit,)).fetchone():raise ValueError('请选择知识点')
   if error and not c.execute('SELECT 1 FROM learning_errors WHERE id=? AND unit=?',(error,unit)).fetchone():raise ValueError('错题与知识点不匹配')
   c.execute('INSERT OR IGNORE INTO review_plan VALUES(?,?,?,?,1,0)',(key,unit,error,(date.today()+timedelta(days=1)).isoformat()))
  return key
 def rows(self):
  with self.db.connect() as c:return [dict(r) for r in c.execute("SELECT p.*,n.title,COALESCE(e.note,'') AS question FROM review_plan p JOIN learning_nodes n ON n.id=p.unit LEFT JOIN learning_errors e ON e.id=p.error WHERE p.unit NOT IN (SELECT id FROM learning_hidden) ORDER BY p.due,n.title")]
 def answer(self,key,rating):
  if rating not in ('忘记','模糊','记住','熟练'):raise ValueError('复习结果无效')
  today=date.today().isoformat()
  with self.db.connect() as c:
   c.execute('BEGIN IMMEDIATE');r=c.execute('SELECT * FROM review_plan WHERE id=?',(key,)).fetchone()
   if not r:raise ValueError('计划不存在')
   if r['due']>today:raise ValueError('尚未到复习日期，避免重复提交')
   stage=0 if rating=='忘记' else r['stage']+1
   interval=1 if rating=='忘记' else max(1,r['interval']//2) if rating=='模糊' else min(180,([1,3,7,14,30][min(stage,4)] if stage<5 else r['interval']*2)*(2 if rating=='熟练' else 1))
   due=(date.today()+timedelta(days=interval)).isoformat();c.execute('UPDATE review_plan SET due=?,interval=?,stage=? WHERE id=?',(due,interval,stage,key));c.execute('INSERT INTO review_attempts(card,rating,day,next_due,created) VALUES(?,?,?,?,?)',(key,rating,today,due,stamp()))
 def history(self,key):
  with self.db.connect() as c:return [dict(r) for r in c.execute('SELECT * FROM review_attempts WHERE card=? ORDER BY id DESC',(key,))]

 def remind(self):
  today=date.today().isoformat();count=sum(r['due']<=today for r in self.rows())
  if not count:return
  with self.db.connect() as c:
   c.execute('INSERT OR IGNORE INTO reminder_occurrences VALUES(?,?,?,?,?,?)',('learning-review:'+today,'learning-review',stamp(),f'今日有 {count} 项知识或错题待复习，可在学习页打开今日复习。','pending','off'))
