"""Transactional reparent and sibling order; stable IDs preserve linked history."""
import json
from .database import stamp

def move(db,domain,key,parent,before=None):
 if domain not in ('work','learning'):raise ValueError('目录类型错误')
 table,col=('work_tasks','parent_id') if domain=='work' else ('learning_nodes','parent');order=domain+'_order'
 with db.connect() as c:
  c.execute('BEGIN IMMEDIATE');rows={r['id']:dict(r) for r in c.execute('SELECT * FROM '+table)}
  if key not in rows or parent is not None and parent not in rows:raise ValueError('目录已变化，请刷新后重试')
  descendants={key}
  while True:
   expanded=descendants|{r['id'] for r in rows.values() if r[col] in descendants}
   if expanded==descendants:break
   descendants=expanded
  if parent in descendants:raise ValueError('不能把节点移进自身或其子节点')
  if before==key and parent==rows[key][col]:return
  if before is not None and (before not in rows or rows[before][col]!=parent):raise ValueError('目标顺序已变化，请重试')
  ancestors=[];p=parent
  while p:
   if p in ancestors:raise ValueError('目标目录存在循环')
   ancestors.append(p);p=rows[p][col]
  if domain=='learning':
   hidden={r[0] for r in c.execute('SELECT id FROM learning_hidden')}
   if key in hidden or any(p in hidden for p in ancestors):raise ValueError('请先恢复已删除目录')
   expected={'subject':None,'chapter':'subject','unit':'chapter'}[rows[key]['kind']]
   if (rows[parent]['kind'] if parent else None)!=expected:raise ValueError('课程放在顶层，章节放入课程，知识点放入章节')
   if c.execute("SELECT 1 FROM sqlite_master WHERE name='focus_runs'").fetchone():
    busy={r[0] for r in c.execute("SELECT l.unit FROM learning_focus_links l JOIN focus_runs f ON f.id=l.run_id WHERE f.state IN ('running','paused')")}
    if descendants & busy:raise ValueError('请先结束关联知识点的专注')
  else:
   from .work import Work
   if any(rows[i]['archived'] for i in descendants|set(ancestors)):raise ValueError('请先恢复归档任务')
   if parent!=rows[key][col] and any(rows[i]['status']=='done' for i in ancestors):raise ValueError('请先重新打开已完成的目标任务')
   if Work._busy(c,list(descendants|set(ancestors))):raise ValueError('请先结束相关任务的专注')
   for node in descendants:
    depth=1;p=node
    while p!=key:depth+=1;p=rows[p][col]
    if depth+len(ancestors)>32:raise ValueError('任务最多32层')
  c.execute('CREATE TABLE IF NOT EXISTS '+order+'(id TEXT PRIMARY KEY,position INTEGER)');positions=dict(c.execute('SELECT id,position FROM '+order))
  old=rows[key][col]
  siblings=sorted((r for r in rows.values() if r[col]==parent and r['id']!=key),key=lambda r:(positions.get(r['id'],100000),r['created']))
  ids=[r['id'] for r in siblings];ids.insert(ids.index(before) if before else len(ids),key)
  c.execute('UPDATE '+table+' SET '+col+'=? WHERE id=?',(parent,key));c.executemany('INSERT INTO '+order+' VALUES(?,?) ON CONFLICT(id) DO UPDATE SET position=excluded.position',[(i,n) for n,i in enumerate(ids)])
  c.execute('CREATE TABLE IF NOT EXISTS tree_move_history(id INTEGER PRIMARY KEY,domain TEXT,node TEXT,old_parent TEXT,new_parent TEXT,before_node TEXT,created TEXT)');c.execute('INSERT INTO tree_move_history(domain,node,old_parent,new_parent,before_node,created) VALUES(?,?,?,?,?,?)',(domain,key,old,parent,before,stamp()))
  if domain=='work':Work._record(c,key,'moved',{'old_parent':old,'new_parent':parent,'before':before})
