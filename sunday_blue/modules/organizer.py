"""Shared user records. AI proposals never silently become confirmed facts."""
import hashlib
import json
import uuid
from datetime import date
from .database import stamp

CATEGORIES=('收件箱','日记完整记录','项目资料','知识摘录','生活备忘')
class Organizer:
    def __init__(self,db):
        self.db=db
        with db.connect() as conn:
            conn.executescript("""CREATE TABLE IF NOT EXISTS organized_records (
                id TEXT PRIMARY KEY,title TEXT,body TEXT,category TEXT,day TEXT,status TEXT,
                origin TEXT,fingerprint TEXT UNIQUE,created TEXT);
                CREATE TABLE IF NOT EXISTS record_revisions (id INTEGER PRIMARY KEY,record_id TEXT,before_json TEXT,created TEXT);""")
    def categories(self):return list(dict.fromkeys(list(CATEGORIES)+self.db.get('organizer_categories',[])))
    def add_category(self,title):
        title=str(title).strip()
        if not title or len(title)>30 or any(c in title for c in '/\\<>:'):raise ValueError('分类名称需简短明确，不能包含路径符号')
        if title.casefold() in {v.casefold() for v in self.categories()}:return
        self.db.set('organizer_categories',self.categories()+[title])

    def capture(self,title,body,category='收件箱',day=None,origin='user',confirmed=False):
        if category not in self.categories():raise ValueError('请选已有分类；归属不明先询问用户。')
        title=str(title).strip();body=str(body).strip();day=day or date.today().isoformat();date.fromisoformat(day)
        if not title or len(title)>120 or not body or len(body)>30000:raise ValueError('标题或内容长度无效')
        fingerprint=hashlib.sha256((origin+'|'+day+'|'+body).encode()).hexdigest();rid=uuid.uuid4().hex
        with self.db.connect() as db:
            db.execute('INSERT OR IGNORE INTO organized_records VALUES(?,?,?,?,?,?,?,?,?)',(rid,title,body,category,day,'confirmed' if confirmed else 'proposal',origin,fingerprint,stamp()))
            return dict(db.execute('SELECT * FROM organized_records WHERE fingerprint=?',(fingerprint,)).fetchone())
    def search(self,query='',day=None):
        with self.db.connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM organized_records WHERE (instr(title,?)>0 OR instr(body,?)>0) AND (? IS NULL OR day=?) ORDER BY day DESC,created DESC LIMIT 100",(query,query,day,day))]
    def organize(self,rid,category,title=None,confirm=False):
        if category not in self.categories():raise ValueError('分类不明确时请先问用户')
        with self.db.connect() as db:
            db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT * FROM organized_records WHERE id=?',(rid,)).fetchone()
            if not row:raise ValueError('记录不存在')
            title=(title or row['title']).strip()
            if not title or len(title)>120:raise ValueError('标题无效')
            db.execute('INSERT INTO record_revisions(record_id,before_json,created) VALUES(?,?,?)',(rid,json.dumps(dict(row),ensure_ascii=False),stamp()))
            db.execute('UPDATE organized_records SET category=?,title=?,status=? WHERE id=?',(category,title,'confirmed' if confirm else row['status'],rid))
    def undo(self,rid):
        with self.db.connect() as db:
            db.execute('BEGIN IMMEDIATE');r=db.execute('SELECT * FROM record_revisions WHERE record_id=? ORDER BY id DESC LIMIT 1',(rid,)).fetchone()
            if not r:raise ValueError('没有可撤销的整理')
            before=json.loads(r['before_json']);db.execute('UPDATE organized_records SET title=?,category=?,status=? WHERE id=?',(before['title'],before['category'],before['status'],rid))
            db.execute('DELETE FROM record_revisions WHERE id=?',(r['id'],))
