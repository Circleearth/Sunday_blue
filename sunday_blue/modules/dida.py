"""Domestic Dida read-only adapter, based on the user's working cookie client.
No writes, no subprocess/runtime dependency on the original project.
"""
import hashlib,json
import requests
from ..storage import protect
from .database import stamp

class Dida:
    def __init__(self,db):
        self.db=db
        with db.connect() as conn:
            conn.executescript("""CREATE TABLE IF NOT EXISTS dida_tasks (id TEXT PRIMARY KEY,project TEXT,title TEXT,status INTEGER,due TEXT,repeat TEXT,last_seen TEXT);
                CREATE TABLE IF NOT EXISTS dida_history (fingerprint TEXT PRIMARY KEY,task_id TEXT,payload TEXT,seen TEXT);""")
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
    def sync(self):
        encrypted=self.db.get('dida_auth',{}).get('cookie_encrypted','')
        if not encrypted:raise ValueError('请先配置国内滴答 Cookie t；本页不接受 Open API OAuth token')
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
        with self.db.connect() as db:return [dict(r) for r in db.execute('SELECT * FROM dida_tasks ORDER BY due,title')]
