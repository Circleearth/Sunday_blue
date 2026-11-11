"""Read-only Markdown library. User navigation does not grant agent file permissions."""
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
    def read(self,path,remember=True):
        p=self.checked(path)
        raw=p.read_bytes()
        if len(raw)>MAX_DOCUMENT:raise ValueError('文档过大')
        try:text=raw.decode('utf-8-sig')
        except UnicodeDecodeError:raise ValueError('请将文档保存为 UTF-8 编码') from None
        if remember:
            value=self.preferences();value['recent']=([str(p)]+[s for s in value.get('recent',[]) if s!=str(p)])[:30];self.db.set('markdown_library',value)
        return p,text
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
