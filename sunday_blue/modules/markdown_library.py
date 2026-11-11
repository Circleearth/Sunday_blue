"""Scoped Markdown library and reviewed manual saves. User navigation does not grant agent file permissions."""
from pathlib import Path
import os
from ..files import no_links,inside

MAX_DOCUMENT=2*1024*1024
class MarkdownLibrary:
    def __init__(self,db):self.db=db
    def preferences(self):return self.db.get('markdown_library',{'root':'','recent':[],'favorites':[]})
    def set_root(self,path):
        root=Path(path).absolute();no_links(root)
        if not root.is_dir():raise ValueError('请选择存在的资料文件夹')
        root=root.resolve();value=self.preferences();value['root']=str(root);self.db.set('markdown_library',value);return root
    def checked(self,path,root=None):
        root=Path(root or self.preferences()['root']).resolve();p=Path(path)
        if not p.is_absolute():p=root/p
        no_links(p);p=p.resolve()
        if not inside(p,root):raise PermissionError('文件不在当前资料文件夹内')
        if not p.is_file() or p.suffix.lower() not in ('.md','.markdown'):raise ValueError('请选择 Markdown 文件')
        if p.stat().st_size>MAX_DOCUMENT:raise ValueError('文档超过 2 MB，请用外部编辑器打开，避免卡住阅读界面')
        return p
    def read(self,path,remember=True,snapshot=False):
        p=self.checked(path)
        raw=p.read_bytes()
        if len(raw)>MAX_DOCUMENT:raise ValueError('文档过大')
        try:text=raw.decode('utf-8-sig')
        except UnicodeDecodeError:raise ValueError('请将文档保存为 UTF-8 编码') from None
        if remember:
            value=self.preferences();value['recent']=([str(p)]+[s for s in value.get('recent',[]) if s!=str(p)])[:30];self.db.set('markdown_library',value)
        return (p,text,raw) if snapshot else (p,text)
    def favorite(self,path):
        p=str(self.checked(path));value=self.preferences();items=value.get('favorites',[])
        if p in items:items.remove(p)
        else:items.append(p)
        value['favorites']=items;self.db.set('markdown_library',value)
    def search(self,query,root,cancel):
        query=query.strip().casefold()
        if not query:return [],False
        result=[];count=0;truncated=False
        for directory,dirs,files in os.walk(root,followlinks=False):
            if cancel.is_set():break
            safe=[]
            for name in dirs:
                if name.startswith('.') or name=='__pycache__':continue
                try:no_links(Path(directory)/name);safe.append(name)
                except (OSError,PermissionError):pass
            dirs[:]=safe
            for name in files:
                if cancel.is_set():return result,truncated
                if Path(name).suffix.lower() not in ('.md','.markdown'):continue
                count+=1
                if count>3000:return result,True
                try:
                    p=self.checked(Path(directory)/name,root);raw=p.read_bytes()
                    if len(raw)>MAX_DOCUMENT:continue
                    text=raw.decode('utf-8-sig');pos=text.casefold().find(query)
                    if query in name.casefold() or pos>=0:
                        result.append({'path':str(p),'label':str(p.relative_to(root)),'snippet':text[max(0,pos-35):max(0,pos-35)+140].replace('\n',' ')})
                        if len(result)>=100:return result,True
                except (OSError,ValueError):continue
        return result,truncated

    def save(self,path,text,original):
        import os,uuid
        from ..files import WRITE_LOCK
        from .document_changes import DocumentChanges
        if not isinstance(text,str) or len(text.encode('utf-8'))>MAX_DOCUMENT:raise ValueError('保存内容超过 2 MB')
        with WRITE_LOCK:
            p=self.checked(path)
            if p.read_bytes()!=original:raise ValueError('文件已被其他程序或角色修改，本次未覆盖。草稿保留；请复制草稿后刷新并核对差异。')
            changes=DocumentChanges(self.db)
            if not changes.eligible(p):raise ValueError('软件自身目录不支持共享修订；请选择独立的资料文件夹')
            changes.recover(p)
            before=original.decode('utf-8-sig')
            # Ignore newline representation changes introduced by the text widget.
            if before.replace('\r\n','\n')==text:return {'status':'unchanged','data':original}
            newline='\r\n' if b'\r\n' in original and original.count(b'\n')==original.count(b'\r\n') else '\n'
            data=text.replace('\r\n','\n').replace('\n',newline).encode('utf-8')
            if original.startswith(b'\xef\xbb\xbf'):data=b'\xef\xbb\xbf'+data
            if len(data)>MAX_DOCUMENT:raise ValueError('编码及换行转换后的内容超过 2 MB')
            rid=changes.prepare(p,original,data,'user');backup=self.db.root/'data/backups'/('markdown-'+rid+'.bak');backup.parent.mkdir(parents=True,exist_ok=True);backup.write_bytes(original)
            temporary=p.with_name('.'+p.name+'.'+uuid.uuid4().hex+'.tmp')
            try:
                with temporary.open('xb') as out:out.write(data);out.flush();os.fsync(out.fileno())
                self.checked(p)
                if p.read_bytes()!=original:raise ValueError('保存期间文件发生变化，本次未覆盖；草稿保留')
                os.replace(temporary,p)
            finally:temporary.unlink(missing_ok=True)
            try:handoff=changes.finish(rid);warning=''
            except Exception:handoff=None;warning='文件已保存，交接暂未写入。修订已留存，重新点击保存或打开修订记录可重试。'
            return {'status':'saved','data':data,'revision_id':rid,'handoff_id':handoff,'warning':warning}
