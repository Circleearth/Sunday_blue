"""Official Dida sync/completion adapter with a legacy read-only cookie fallback."""
import hashlib,json,threading
import requests
from ..storage import protect
from .database import stamp

class Dida:
    def __init__(self,db):
        self.db=db;self.lock=threading.Lock()
        with db.connect() as conn:
            conn.executescript("""CREATE TABLE IF NOT EXISTS dida_tasks (id TEXT PRIMARY KEY,project TEXT,title TEXT,status INTEGER,due TEXT,repeat TEXT,last_seen TEXT);
                CREATE TABLE IF NOT EXISTS dida_history (fingerprint TEXT PRIMARY KEY,task_id TEXT,payload TEXT,seen TEXT);
                CREATE TABLE IF NOT EXISTS dida_official_meta (id TEXT PRIMARY KEY,project_id TEXT,etag TEXT,due TEXT,kind TEXT);
                CREATE TABLE IF NOT EXISTS dida_completion_ops (operation TEXT PRIMARY KEY,task_id TEXT,state TEXT,created TEXT);""")
    def configure(self,token):
        token=token.strip()
        if not token or any(c in token for c in '\r\n";'):raise ValueError('无效 Cookie t')
        self.db.set('dida_auth',{'cookie_encrypted':protect(token)})
    def fetch(self,token,get=requests.get):
        headers={'Cookie':'t="'+token+'"','Accept':'application/json','User-Agent':'Mozilla/5.0'}
        def read(path):
            with get('https://api.dida365.com'+path,headers=headers,timeout=(5,15),allow_redirects=False) as response:
                if response.status_code==401:raise ValueError('滴答 Cookie 已失效，请重新配置；无需修改代码。')
                if response.status_code!=200:raise ValueError('滴答只读请求失败，HTTP '+str(response.status_code))
                return response.json()
        projects=read('/api/v2/projects');batch=read('/api/v3/batch/check/0')
        if not isinstance(projects,list) or not isinstance(batch,dict) or not isinstance(batch.get('syncTaskBean',{}).get('update'),list):raise ValueError('国内接口响应结构不符合预期，本次未更新本地记录')
        names={r['id']:r.get('name','') for r in projects}
        return [{'id':t['id'],'project':names.get(t.get('projectId'),t.get('projectId','')),'title':t.get('title',''),
            'status':t.get('status',0),'due':t.get('dueDate') or '', 'repeat':t.get('repeatFlag') or ''}
            for t in batch['syncTaskBean']['update'] if t.get('id') and not t.get('deleted')]
    def configure_api(self,token):
        token=token.strip()
        if not token.startswith('dp_') or any(c.isspace() for c in token):raise ValueError('请输入滴答账户中的 API 口令（dp_ 开头）')
        self.db.set('dida_mcp_auth',{'token_encrypted':protect(token)})
    def official_enabled(self):return bool(self.db.get('dida_mcp_auth',{}).get('token_encrypted'))
    def client(self):
        from .dida_mcp import DidaMCP
        encrypted=self.db.get('dida_mcp_auth',{}).get('token_encrypted','')
        if not encrypted:raise ValueError('勾选完成需要配置官方 API 口令。')
        return DidaMCP(protect(encrypted,decrypt=True))
    def normalize(self,task,names=None):
        if not isinstance(task,dict) or task.get('error') or not task.get('id') or not task.get('projectId'):
            raise ValueError('滴答任务结果无效，未改变本地完成状态。')
        return {'id':task['id'],'project':(names or {}).get(task['projectId'],task['projectId']),
            'title':task.get('title') or '', 'status':task.get('status',0),'due':task.get('dueDate') or '',
            'repeat':task.get('repeatFlag') or ''}
    def remember_meta(self,tasks):
        with self.db.connect() as db:
            for t in tasks:db.execute('INSERT INTO dida_official_meta VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET project_id=excluded.project_id,etag=excluded.etag,due=excluded.due,kind=excluded.kind',
                (t['id'],t['projectId'],t.get('etag') or '',t.get('dueDate') or '',t.get('kind') or 'TEXT'))
    def sync_official(self):
        client=self.client();projects=client.call('list_projects',{})
        tasks=client.call('filter_tasks',{'filter':{'status':[0]},'client_timezone':'Asia/Shanghai'})
        if not isinstance(projects,list) or not isinstance(tasks,list):raise ValueError('滴答同步返回格式异常')
        names={p['id']:p.get('name','') for p in projects}
        rows=[self.normalize(t,names) for t in tasks]
        # Reconcile cached tasks missing from the active result individually. Missing does not mean complete.
        active={r['id'] for r in rows}
        with self.db.connect() as db:old=[r[0] for r in db.execute('SELECT t.id FROM dida_tasks t JOIN dida_official_meta m ON m.id=t.id WHERE t.status IN (0,1)')]
        for tid in old:
            if tid in active:continue
            try:
                task=client.call('get_task_by_id',{'task_id':tid});row=self.normalize(task,names)
                tasks.append(task);rows.append(row)
            except ValueError:continue
        self.ingest(rows);self.remember_meta(tasks);return len(rows)
    def complete(self,task_id,expected_due,expected_etag):
        with self.lock:
            client=self.client();task=client.call('get_task_by_id',{'task_id':task_id})
            normalized=self.normalize(task)
            if normalized['id']!=task_id:raise ValueError('任务标识不匹配，未提交完成操作。')
            if normalized['status']==2:
                self.ingest([normalized]);self.remember_meta([task]);return '滴答已完成，状态已刷新。'
            if normalized['status'] not in (0,1) or task.get('kind')=='NOTE':raise ValueError('此条不是可完成的待办任务')
            if normalized['due']!=expected_due or (task.get('etag') or '')!=expected_etag:
                self.ingest([normalized]);self.remember_meta([task]);raise ValueError('任务已变化，请刷新后核对再勾选，避免完成下一次循环。')
            key=hashlib.sha256((task_id+'|'+expected_due+'|'+expected_etag).encode()).hexdigest()
            with self.db.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                if db.execute('SELECT 1 FROM dida_completion_ops WHERE operation=?',(key,)).fetchone():raise ValueError('这次完成操作已提交过，请同步或在滴答核对；不会自动重复提交。')
                db.execute('INSERT INTO dida_completion_ops VALUES(?,?,?,?)',(key,task_id,'pending',stamp()))
            try:
                result=client.call('complete_task',{'project_id':task['projectId'],'task_id':task_id})
                completed=self.normalize(result)
                if completed['id']!=task_id or result['projectId']!=task['projectId']:raise ValueError('完成回执标识不匹配，请同步核对。')
                if completed['status']!=2 and not (normalized['repeat'] and completed['due']!=normalized['due']):
                    raise ValueError('未收到明确完成回执，请同步核对。')
                self.ingest([normalized|{'status':2}]);self.ingest([completed]);self.remember_meta([result])
                with self.db.connect() as db:db.execute("UPDATE dida_completion_ops SET state='confirmed' WHERE operation=?",(key,))
                return '已同步到滴答清单。'
            except Exception:
                with self.db.connect() as db:db.execute("UPDATE dida_completion_ops SET state='unconfirmed' WHERE operation=?",(key,))
                raise
    def sync(self):
        if self.official_enabled():return self.sync_official()
        encrypted=self.db.get('dida_auth',{}).get('cookie_encrypted','')
        if not encrypted:raise ValueError('请先配置滴答账户中的 API 口令')
        rows=self.fetch(protect(encrypted,decrypt=True));self.ingest(rows);return len(rows)
    def ingest(self,rows):
        with self.db.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            for r in rows:
                payload=json.dumps(r,sort_keys=True,ensure_ascii=False);fingerprint=hashlib.sha256(payload.encode()).hexdigest()
                db.execute('INSERT OR IGNORE INTO dida_history VALUES(?,?,?,?)',(fingerprint,r['id'],payload,stamp()))
                db.execute('INSERT INTO dida_tasks VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET project=excluded.project,title=excluded.title,status=excluded.status,due=excluded.due,repeat=excluded.repeat,last_seen=excluded.last_seen',
                    (r['id'],r['project'],r['title'],r['status'],r['due'],r['repeat'],stamp()))
        self.db.set('dida_last_sync',stamp())
    def tasks(self):
        with self.db.connect() as db:return [dict(r) for r in db.execute("SELECT t.*,m.project_id,m.etag,m.kind FROM dida_tasks t LEFT JOIN dida_official_meta m ON m.id=t.id ORDER BY t.due,t.title")]
