"""Append-only Markdown notebook. No model calls or role-memory writes."""
from pathlib import Path
from datetime import datetime
import re,uuid,os
class PersonalNotes:
 def __init__(self,db):
  self.db=db
  with db.connect() as c:c.execute('CREATE TABLE IF NOT EXISTS personal_notes(id TEXT PRIMARY KEY,title TEXT,path TEXT,created TEXT)')
 def directory(self):return Path(self.db.get('personal_notes_dir',str(self.db.root/'data/notebooks')))
 def save(self,title,body):
  title=title.strip()
  if not title or not body.strip() or len(title)>120:raise ValueError('请填写120字内标题和正文')
  now=datetime.now();key=uuid.uuid4().hex;folder=self.directory()/now.strftime('%Y/%m');folder.mkdir(parents=True,exist_ok=True)
  safe=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',title).strip(' .')[:80] or '笔记'
  target=folder/(now.strftime('%d_%H%M%S_')+safe+'_'+key[:6]+'.md');text='# '+title+'\n\n记录时间：'+now.isoformat(timespec='seconds')+'\n\n'+body
  with target.open('x',encoding='utf-8') as f:f.write(text)
  with self.db.connect() as c:c.execute('INSERT INTO personal_notes VALUES(?,?,?,?)',(key,title,str(target),now.isoformat()))
  return str(target)
 def rows(self):
  with self.db.connect() as c:return [dict(r) for r in c.execute('SELECT * FROM personal_notes ORDER BY created DESC')]
 def read(self,key):
  with self.db.connect() as c:r=c.execute('SELECT path FROM personal_notes WHERE id=?',(key,)).fetchone()
  if not r:raise ValueError('笔记不存在')
  return Path(r[0]).read_text(encoding='utf-8')
