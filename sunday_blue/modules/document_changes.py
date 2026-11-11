"""Durable file-change journal and idempotent handoff, no LLM summarization."""
import difflib,hashlib,uuid
from pathlib import Path
from .database import stamp
from .duties import Duties,assigned
from ..files import inside,no_links

def digest(data):return hashlib.sha256(data).hexdigest() if data is not None else 'missing'

class DocumentChanges:
    def __init__(self,db):
        self.db=db;Duties(db)
        with db.connect() as c:c.execute('''CREATE TABLE IF NOT EXISTS document_changes (
            id TEXT PRIMARY KEY,path TEXT,actor TEXT,before_text TEXT,after_text TEXT,
            before_hash TEXT,after_hash TEXT,state TEXT,handoff_id TEXT,created TEXT)''')
    def eligible(self,path,role=None):
        root=self.db.get('markdown_library',{}).get('root')
        if not root or Path(path).suffix.lower() not in ('.md','.markdown'):return False
        no_links(Path(path))
        if not inside(Path(path).resolve(),Path(root).resolve()):return False
        # Private app files never enter shared handoffs even if the whole app was selected.
        if any(inside(Path(path).resolve(),(self.db.root/folder).resolve()) for folder in ('data','personas','extensions','.git')):return False
        return role is None or bool(set(assigned(self.db.root,role)) & {'recorder','organizer'})
    def prepare(self,path,before,after,actor):
        rid=uuid.uuid4().hex
        with self.db.connect() as c:c.execute('INSERT INTO document_changes VALUES(?,?,?,?,?,?,?,?,?,?)',(rid,str(path),actor,(before or b'').decode('utf-8-sig'),after.decode('utf-8-sig'),digest(before),digest(after),'prepared',None,stamp()))
        return rid
    @staticmethod
    def difference(before,after):
        # Full snapshots are durable; bounded diff avoids pathological matcher CPU costs.
        if len(before)+len(after)>120000 or len(before.splitlines())+len(after.splitlines())>4000:
            return '文档较大，差异预览省略；完整改前/改后快照已保存，可切换查看。'
        text=''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='修改前',tofile='修改后',n=3))
        return text[:18000]+('\n…差异预览已截断，完整快照仍保留。' if len(text)>18000 else '')
    def finish(self,rid):
        row=self.get(rid);diff=self.difference(row['before_text'],row['after_text'])
        body=f"操作者：{row['actor']}\n文件：{row['path']}\n时间：{row['created']}\n修订 ID：{rid}\n这是实际文件修改回执，不代表文中推断已经确认。\n\n{diff}"
        record_id='change:'+rid;hid='change:'+rid
        with self.db.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            current=c.execute('SELECT state,handoff_id FROM document_changes WHERE id=?',(rid,)).fetchone()
            if current['handoff_id']:return current['handoff_id']
            if current['state'] not in ('prepared','saved'):raise ValueError('这次修订没有成功写入，不能生成完成交接')
            c.execute('INSERT OR IGNORE INTO organized_records VALUES(?,?,?,?,?,?,?,?,?)',(record_id,('Markdown 修改 · '+Path(row['path']).name)[:120],body,'收件箱',row['created'][:10],'proposal','file-change',record_id,stamp()))
            c.execute('INSERT OR IGNORE INTO duty_handoffs VALUES(?,?,?,?,?,?,?,?)',(hid,record_id,'pending','记录员与整理员核对修订；尊重用户主动修改，必要时整理关联资料，不自动覆盖或回滚。',row['path'],'',stamp(),stamp()))
            c.execute("UPDATE document_changes SET state='saved',handoff_id=? WHERE id=?",(hid,rid))
            self.db.emit(c,'file-change:'+rid,'document.changed',{'revision_id':rid,'handoff_id':hid,'actor':row['actor'],'path':row['path']})
        return hid
    def get(self,rid):
        with self.db.connect() as c:row=c.execute('SELECT * FROM document_changes WHERE id=?',(rid,)).fetchone()
        if not row:raise ValueError('修订不存在')
        return dict(row)
    def history(self,path):
        with self.db.connect() as c:return [dict(r) for r in c.execute('SELECT id,path,actor,state,handoff_id,created FROM document_changes WHERE path=? ORDER BY created DESC,rowid DESC LIMIT 100',(str(path),))]
    def recover(self,path=None):
        with self.db.connect() as c:rows=[dict(r) for r in c.execute("SELECT * FROM document_changes WHERE state='prepared' AND (? IS NULL OR path=?) ORDER BY created LIMIT 100",(str(path) if path else None,str(path) if path else None))]
        for row in rows:
            p=Path(row['path'])
            try:
                if not self.eligible(p):continue
                no_links(p)
                if p.exists() and p.stat().st_size>2*1024*1024:continue
                current=p.read_bytes() if p.exists() else None
                if digest(current)==row['after_hash']:self.finish(row['id'])
                elif digest(current)==row['before_hash']:
                    with self.db.connect() as c:c.execute("UPDATE document_changes SET state='not_applied' WHERE id=?",(row['id'],))
                # Ambiguous external modification stays pending for manual inspection.
            except (OSError,ValueError):continue
