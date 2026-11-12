"""Learning evidence, chapter progress and review scheduling; focus remains time owner."""
import json,uuid
from datetime import datetime,timedelta,timezone
from .database import stamp
from .life import number

class Learning:
 def __init__(self,db):
  self.db=db
  with db.connect() as c:c.executescript('''
   CREATE TABLE IF NOT EXISTS learning_nodes(id TEXT PRIMARY KEY,parent TEXT,kind TEXT,title TEXT,self_score REAL DEFAULT 0,done INTEGER DEFAULT 0,created TEXT);
   CREATE TABLE IF NOT EXISTS learning_attempts(id TEXT PRIMARY KEY,unit TEXT,total INTEGER,correct INTEGER,note TEXT,created TEXT);
   CREATE TABLE IF NOT EXISTS learning_reviews(id TEXT PRIMARY KEY,unit TEXT,passed INTEGER,note TEXT,day TEXT,created TEXT,UNIQUE(unit,day));
   CREATE TABLE IF NOT EXISTS learning_errors(id TEXT PRIMARY KEY,unit TEXT,note TEXT,resolved INTEGER DEFAULT 0,created TEXT);
   CREATE TABLE IF NOT EXISTS learning_focus_links(run_id TEXT PRIMARY KEY,unit TEXT);
   CREATE TABLE IF NOT EXISTS learning_mastery(unit TEXT PRIMARY KEY,first_mastered TEXT);
  ''')
 def options(self):return {'mastery_threshold':80,'minimum_questions':10}|self.db.get('learning_options',{})
 def configure(self,threshold,minimum):
  value={'mastery_threshold':int(number(threshold,60,100,'掌握阈值')),'minimum_questions':int(number(minimum,5,100,'最低题量'))};self.db.set('learning_options',value)
 def add(self,kind,title,parent=None):
  title=str(title).strip()
  if kind not in ('subject','chapter','unit') or not title or len(title)>150:raise ValueError('请填写150字内名称')
  with self.db.connect() as c:
   if kind!='subject':
    row=c.execute('SELECT kind FROM learning_nodes WHERE id=?',(parent,)).fetchone()
    if not row or row['kind']!=('subject' if kind=='chapter' else 'chapter'):raise ValueError('请先选择对应学科或章节')
   else:parent=None
   prior=c.execute('SELECT id FROM learning_nodes WHERE kind=? AND title=? AND parent IS ?',(kind,title,parent)).fetchone()
   if prior:return prior[0]
   nid=uuid.uuid4().hex;c.execute('INSERT INTO learning_nodes VALUES(?,?,?,?,0,0,?)',(nid,parent,kind,title,stamp()));return nid
 def _unit(self,c,uid):
  if not c.execute("SELECT 1 FROM learning_nodes WHERE id=? AND kind='unit'",(uid,)).fetchone():raise ValueError('请选择一个知识点')
 def rows(self):
  with self.db.connect() as c:return [dict(r) for r in c.execute('SELECT * FROM learning_nodes ORDER BY created,rowid')]
 def evidence(self,uid):
  opt=self.options()
  with self.db.connect() as c:
   self._unit(c,uid);node=c.execute('SELECT * FROM learning_nodes WHERE id=?',(uid,)).fetchone()
   attempts=c.execute('SELECT * FROM learning_attempts WHERE unit=? ORDER BY created DESC,rowid DESC LIMIT 50',(uid,)).fetchall()
   reviews=c.execute('SELECT * FROM learning_reviews WHERE unit=? ORDER BY day DESC',(uid,)).fetchall()
   seconds=c.execute('SELECT COALESCE(sum(a.seconds),0) FROM activity_records a JOIN learning_focus_links l ON l.run_id=a.id WHERE l.unit=?',(uid,)).fetchone()[0]
   errors=c.execute('SELECT count(*) FROM learning_errors WHERE unit=? AND resolved=0',(uid,)).fetchone()[0]
  total=sum(r['total'] for r in attempts);correct=sum(r['correct'] for r in attempts);accuracy=100*correct/total if total else 0
  score=min(node['self_score'],accuracy) if total>=opt['minimum_questions'] else min(node['self_score'],accuracy,59)
  passed=bool(reviews and reviews[0]['passed']);mastered=total>=opt['minimum_questions'] and score>=opt['mastery_threshold'] and passed and not errors
  streak=0
  for r in reviews:
   if not r['passed']:break
   streak+=1
  due=(datetime.fromisoformat(reviews[0]['day'])+timedelta(days=([1,3,7,14,30][min(max(streak-1,0),4)] if passed else 1))).date().isoformat() if reviews else node['created'][:10]
  return dict(total=total,correct=correct,accuracy=accuracy,score=score,mastered=mastered,due=due,errors=errors,minutes=seconds/60,reviews=len(reviews))
 def assess(self,uid,score):
  score=number(score,0,100,'自评')
  with self.db.connect() as c:self._unit(c,uid);c.execute('UPDATE learning_nodes SET self_score=? WHERE id=?',(score,uid))
  self._mastered(uid)
 def _mastered(self,uid):
  if self.evidence(uid)['mastered']:
   with self.db.connect() as c:c.execute('INSERT OR IGNORE INTO learning_mastery VALUES(?,?)',(uid,stamp()))
 def practice(self,uid,total,correct,note='',request_id=None,error_id=None):
  if isinstance(total,bool) or isinstance(correct,bool) or int(total)!=total or int(correct)!=correct:raise ValueError('题数需为整数')
  total=int(number(total,1,10000,'题数'));correct=int(number(correct,0,total,'正确题数'));note=str(note).strip()
  if total>correct and not note:raise ValueError('请记录错因或待复习的问题')
  if len(note)>4000:raise ValueError('错题说明过长')
  key=request_id or uuid.uuid4().hex
  with self.db.connect() as c:
   c.execute('BEGIN IMMEDIATE');self._unit(c,uid)
   previous=c.execute('SELECT * FROM learning_attempts WHERE id=?',(key,)).fetchone()
   if previous:
    if (previous['unit'],previous['total'],previous['correct'],previous['note'])!=(uid,total,correct,note):raise ValueError('重复请求内容不一致')
    return
   if error_id and not c.execute('SELECT 1 FROM learning_errors WHERE id=? AND unit=?',(error_id,uid)).fetchone():raise ValueError('错题与知识点不匹配')
   c.execute('INSERT INTO learning_attempts VALUES(?,?,?,?,?,?)',(key,uid,total,correct,note,stamp()))
   if total>correct and not error_id:c.execute('INSERT INTO learning_errors VALUES(?,?,?,0,?)',(key,uid,note,stamp()))
   if error_id:c.execute('UPDATE learning_errors SET resolved=? WHERE id=?',(int(total==correct),error_id))
   self.db.emit(c,'learning-practice:'+key,'learning.practice',{'unit':uid,'total':total,'correct':correct})
  self._mastered(uid)
 def review(self,uid,passed,note=''):
  from .life_state import ZONE
  day=datetime.now(ZONE).date().isoformat()
  with self.db.connect() as c:
   c.execute('BEGIN IMMEDIATE');self._unit(c,uid)
   if c.execute('SELECT 1 FROM learning_reviews WHERE unit=? AND day=?',(uid,day)).fetchone():raise ValueError('今天已记录复习结果，明天再检验；练习不受限制')
   c.execute('INSERT INTO learning_reviews VALUES(?,?,?,?,?,?)',(uuid.uuid4().hex,uid,int(bool(passed)),str(note)[:4000],day,stamp()))
  self._mastered(uid)
 def errors(self):
  with self.db.connect() as c:return [dict(r) for r in c.execute('SELECT e.*,n.title FROM learning_errors e JOIN learning_nodes n ON n.id=e.unit ORDER BY e.resolved,e.created DESC')]
 def bind(self,run_id,uid):
  with self.db.connect() as c:
   self._unit(c,uid)
   if not c.execute("SELECT 1 FROM focus_runs r LEFT JOIN focus_timers t ON t.run_id=r.id WHERE r.id=? AND r.category='学习' AND COALESCE(t.phase,'focus')='focus' AND r.state IN ('running','paused')",(run_id,)).fetchone():raise ValueError('只能绑定正在进行的学习专注')
   prior=c.execute('SELECT unit FROM learning_focus_links WHERE run_id=?',(run_id,)).fetchone()
   if prior and prior['unit']!=uid:raise ValueError('本轮已绑定其他知识点，请结束后切换')
   c.execute('INSERT OR IGNORE INTO learning_focus_links VALUES(?,?)',(run_id,uid))
 def chapter_done(self,nid,done):
  with self.db.connect() as c:c.execute("UPDATE learning_nodes SET done=? WHERE id=? AND kind='chapter'",(int(done),nid))
 def summary(self):
  units=[n for n in self.rows() if n['kind']=='unit'];evidence=[self.evidence(n['id']) for n in units]
  with self.db.connect() as c:minutes=c.execute("SELECT COALESCE(sum(seconds),0)/60 FROM activity_records WHERE category='学习'").fetchone()[0]
  return dict(minutes=minutes,units=len(units),mastered=sum(e['mastered'] for e in evidence),questions=sum(e['total'] for e in evidence),correct=sum(e['correct'] for e in evidence))
