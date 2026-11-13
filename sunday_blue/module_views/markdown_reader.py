"""Native, scoped Markdown reader without web engines or remote resource fetching."""
import threading,uuid
from pathlib import Path
from PySide6.QtCore import Qt,QUrl,Signal,QDir
from PySide6.QtGui import QDesktopServices,QTextCursor,QImageReader
from PySide6.QtWidgets import (QFileSystemModel,QWidget,QVBoxLayout,QHBoxLayout,QSplitter,QTreeView,QLabel,QPushButton,
    QMessageBox,QLineEdit,QListWidget,QListWidgetItem,QTextBrowser,QPlainTextEdit,QTabWidget,QFileDialog,QSpinBox)
from ..modules.markdown_library import MarkdownLibrary
from ..files import inside,no_links,WRITE_LOCK
from ..numeric_inputs import NumberSpin as QSpinBox, DecimalSpin as QDoubleSpinBox

class SafeMarkdown(QTextBrowser):
    def __init__(self,library,parent=None):super().__init__(parent);self.library=library
    def loadResource(self,kind,url):
        # Only explicitly selected library images; no remote/file escape/embedded network content.
        try:
            if int(kind)!=2:return None
            resolved=self.document().baseUrl().resolved(url)
            if not resolved.isLocalFile():return None
            path=Path(resolved.toLocalFile());no_links(path);path=path.resolve();root=Path(self.library.preferences()['root']).resolve()
            if not inside(path,root) or path.suffix.lower() not in ('.png','.jpg','.jpeg','.gif','.webp','.bmp') or path.stat().st_size>8*1024*1024:return None
            reader=QImageReader(str(path));size=reader.size()
            if size.width()*size.height()>20000000:return None
            return reader.read()
        except (OSError,ValueError,PermissionError):return None

class MarkdownPage(QWidget):
    searched=Signal(str,object,bool,str)
    recovered=Signal()
    save_completed=Signal(object,str)
    revisions_ready=Signal(object,str)
    def __init__(self,hub,parent=None):
        super().__init__(parent);self.hub=hub;self.library=MarkdownLibrary(hub.db);self.current=None;self.cancel=threading.Event();self.ticket='';self.back_stack=[];self.original=b'';self.saving=False;self._after_save=None
        outer=QVBoxLayout(self);outer.setContentsMargins(24,20,24,20);head=QHBoxLayout();title=QLabel('资料阅读');title.setObjectName('title');head.addWidget(title);head.addStretch()
        for text,fn in [('选择资料文件夹',self.choose_root),('刷新当前文档',self.reload),('在文件夹中查看',self.reveal)]:
            b=QPushButton(text);b.clicked.connect(fn);head.addWidget(b)
        outer.addLayout(head);self.root_label=QLabel('选择资料文件夹，例如 D:\\MasterData');self.root_label.setWordWrap(True);self.root_label.setObjectName('muted');outer.addWidget(self.root_label)
        split=QSplitter();outer.addWidget(split,1);left=QWidget();ll=QVBoxLayout(left);ll.setContentsMargins(0,0,8,0)
        self.search=QLineEdit();self.search.setPlaceholderText('搜索文件名或正文，回车开始');self.search.returnPressed.connect(self.start_search);ll.addWidget(self.search)
        self.navigation=QTabWidget();ll.addWidget(self.navigation)
        self.tree=QTreeView();self.tree.setEnabled(False);self.model=QFileSystemModel(self);self.model.setFilter(QDir.Filter.AllDirs|QDir.Filter.Files|QDir.Filter.NoDotAndDotDot);self.model.setNameFilters(['*.md','*.markdown']);self.model.setNameFilterDisables(False);self.model.setReadOnly(True);self.tree.setModel(self.model);self.tree.setHeaderHidden(True)
        for col in (1,2,3):self.tree.hideColumn(col)
        self.tree.clicked.connect(lambda index:self.open_file(self.model.filePath(index)) if not self.model.isDir(index) else None)
        self.navigation.addTab(self.tree,'目录');self.results=QListWidget();self.results.setWordWrap(True);self.navigation.addTab(self.results,'搜索');self.saved=QListWidget();self.navigation.addTab(self.saved,'收藏 / 最近')
        for widget in (self.results,self.saved):widget.itemClicked.connect(lambda item:self.open_file(item.data(Qt.ItemDataRole.UserRole)))
        split.addWidget(left)
        center=QWidget();cl=QVBoxLayout(center);cl.setContentsMargins(8,0,8,0);self.filename=QLabel('打开一篇文档，开始阅读');self.filename.setObjectName('cardTitle');self.filename.setWordWrap(True);cl.addWidget(self.filename)
        toolbar=QHBoxLayout();back=QPushButton('返回');back.clicked.connect(self.go_back);toolbar.addWidget(back);self.star=QPushButton('收藏');self.star.clicked.connect(self.favorite);toolbar.addWidget(self.star)
        self.save_button=QPushButton('保存');self.save_button.setObjectName('primary');self.save_button.clicked.connect(lambda:self.save_document());toolbar.addWidget(self.save_button)
        self.revisions_button=QPushButton('修订记录');self.revisions_button.clicked.connect(self.show_revisions);toolbar.addWidget(self.revisions_button)
        self.find=QLineEdit();self.find.setPlaceholderText('文内查找');self.find.returnPressed.connect(self.find_next);toolbar.addWidget(self.find,1)
        self.size=QSpinBox();self.size.setRange(12,28);self.size.setValue(16);self.size.setSuffix(' px');self.size.valueChanged.connect(self.apply_size);toolbar.addWidget(self.size);cl.addLayout(toolbar)
        self.views=QTabWidget();self.reader=SafeMarkdown(self.library);self.reader.setOpenLinks(False);self.reader.anchorClicked.connect(self.link);self.source=QPlainTextEdit();self.source.setReadOnly(False);self.source.setEnabled(False);self.views.addTab(self.reader,'阅读');self.views.addTab(self.source,'编辑 Markdown');cl.addWidget(self.views,1);split.addWidget(center)
        right=QWidget();rl=QVBoxLayout(right);rl.setContentsMargins(8,0,0,0);rl.addWidget(QLabel('文档目录'));self.outline=QListWidget();self.outline.itemClicked.connect(self.jump);rl.addWidget(self.outline);split.addWidget(right);split.setSizes([240,700,180]);split.setStretchFactor(1,1)
        self.status=QLabel('按原目录阅读；选择文件夹不会改变角色的文件权限。');self.status.setWordWrap(True);outer.addWidget(self.status)
        self.searched.connect(self.search_finished);hub.closed.connect(self.cancel.set);self.apply_size()
        self.save_completed.connect(self.save_finished);self.revisions_ready.connect(self.show_revision_result);self.source.textChanged.connect(self.edited);self.views.currentChanged.connect(self.preview_draft)
        root=self.library.preferences().get('root')
        if root:self.set_root(root)
        self.recovered.connect(lambda:self.hub.changed.emit('documents'))
        def recover_pending():
            try:
                from ..modules.document_changes import DocumentChanges
                with WRITE_LOCK:DocumentChanges(self.hub.db).recover()
                self.recovered.emit()
            except Exception:pass  # Explicit Save / revision history remains a retry path.
        threading.Thread(target=recover_pending,daemon=True,name='markdown-recovery').start()
    def edited(self):
        if self.current:self.filename.setText(self.current.name+(' · 尚未保存' if self.source.document().isModified() else ''))
    def preview_draft(self,index):
        if index==0 and self.current:self.reader.setMarkdown(self.source.toPlainText())
    def can_leave(self,action=None):
        if self.saving:self.status.setText('正在后台保存和生成交接，请稍候再切换。');return False
        if not self.current or not self.source.document().isModified():return True
        answer=QMessageBox.question(self,'尚未保存','文档有未保存修改，是否保存后离开？',QMessageBox.StandardButton.Save|QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)
        if answer==QMessageBox.StandardButton.Save:self.save_document(action);return False
        if answer==QMessageBox.StandardButton.Discard:
            self.source.setPlainText(self.original.decode('utf-8-sig'));self.source.document().setModified(False);self.edited();self.preview_draft(0);return True
        return False
    def save_document(self,after=None):
        if self.saving or not self.current:return
        path=self.current;text=self.source.toPlainText();original=self.original;self.saving=True;self._after_save=after
        self.source.setReadOnly(True);self.save_button.setEnabled(False);self.revisions_button.setEnabled(False);self.status.setText('后台保存中：核对外部修改、备份、生成修订和交接…')
        def work():
            try:result=self.library.save(path,text,original);error=''
            except Exception as exc:result=None;error=str(exc)
            try:self.save_completed.emit(result,error)
            except RuntimeError:pass
        threading.Thread(target=work,daemon=True,name='markdown-save').start()
    def save_finished(self,result,error):
        self.saving=False;self.source.setReadOnly(False);self.save_button.setEnabled(True);self.revisions_button.setEnabled(True);action=self._after_save;self._after_save=None
        if error:self.status.setText(error);return
        self.original=result['data'];self.source.document().setModified(False);self.edited();self.reader.setMarkdown(self.source.toPlainText())
        self.status.setText(result.get('warning') or ('未检测到内容变化，没有新增修订。' if result['status']=='unchanged' else '已保存，改前/改后和差异已交接给记录员、整理员。'))
        self.hub.changed.emit('documents')
        if action and not result.get('warning'):action()
    def show_revisions(self):
        if not self.current or self.saving:return
        path=self.current;self.revisions_button.setEnabled(False)
        def work():
            try:
                from ..modules.document_changes import DocumentChanges
                changes=DocumentChanges(self.hub.db)
                with WRITE_LOCK:changes.recover(path)
                rows=changes.history(path);error=''
            except Exception as exc:rows=[];error=str(exc)
            try:self.revisions_ready.emit(rows,error)
            except RuntimeError:pass
        threading.Thread(target=work,daemon=True,name='markdown-revisions').start()
    def show_revision_result(self,rows,error):
        self.revisions_button.setEnabled(True)
        if error:self.status.setText(error);return
        from ..modules.document_changes import DocumentChanges
        from .document_revisions import RevisionDialog
        dialog=RevisionDialog(rows,DocumentChanges(self.hub.db),self);dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose);dialog.show()
        self.hub.changed.emit('documents')
    def apply_size(self,*args):
        self.reader.document().setDefaultStyleSheet(f'body {{font-size:{self.size.value()}px;line-height:1.65}} pre {{white-space:pre-wrap}}')
        font=self.reader.font();font.setPixelSize(self.size.value());self.reader.setFont(font)
    def choose_root(self):
        path=QFileDialog.getExistingDirectory(self,'选择 Markdown 资料文件夹',self.library.preferences().get('root',''))
        if path:self.set_root(path)
    def set_root(self,path):
        if not self.can_leave(lambda:self.set_root(path)):return
        try:root=self.library.set_root(path)
        except Exception as exc:self.status.setText(str(exc));return
        self.cancel.set();self.ticket='';self.current=None;self.back_stack=[];self.reader.clear();self.source.clear();self.source.document().setModified(False);self.source.setEnabled(False);self.outline.clear();self.results.clear();self.filename.setText('选择文档');self.root_label.setText(str(root));self.tree.setEnabled(True);self.model.setRootPath(str(root));self.tree.setRootIndex(self.model.index(str(root)));self.refresh_saved();self.status.setText('点击目录中的 Markdown 文件阅读；回车搜索正文。')
    def refresh_saved(self):
        self.saved.clear();value=self.library.preferences();root=Path(value['root']).resolve()
        for label,paths in [('★',value.get('favorites',[])),('最近',value.get('recent',[]))]:
            for path in paths:
                if not inside(Path(path),root):continue
                item=QListWidgetItem(label+' · '+str(Path(path).relative_to(root)));item.setData(Qt.ItemDataRole.UserRole,path);self.saved.addItem(item)
    def open_file(self,path,remember_back=True):
        if not self.can_leave(lambda:self.open_file(path,remember_back)):return
        try:p,text,raw=self.library.read(path,snapshot=True)
        except Exception as exc:self.status.setText(str(exc));return
        if remember_back and self.current and self.current!=p:self.back_stack.append(self.current)
        self.current=p;self.original=raw;self.filename.setText(p.name);self.source.setPlainText(text);self.source.document().setModified(False);self.source.setEnabled(True);self.filename.setText(p.name);self.reader.document().setBaseUrl(QUrl.fromLocalFile(str(p.parent)+'/'));self.reader.setMarkdown(text);self.outline.clear()
        block=self.reader.document().begin()
        while block.isValid():
            level=block.blockFormat().headingLevel()
            if level:
                item=QListWidgetItem('  '*(level-1)+block.text());item.setData(Qt.ItemDataRole.UserRole,block.position());self.outline.addItem(item)
            block=block.next()
        self.status.setText(f'{p} · {len(text):,} 字符 · UTF-8');self.star.setText('取消收藏' if str(p) in self.library.preferences().get('favorites',[]) else '收藏');self.refresh_saved()
    def reload(self):
        if self.current:self.open_file(self.current,False)
    def reveal(self):
        root=self.library.preferences().get('root')
        if root:QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.current.parent if self.current else root)))
    def favorite(self):
        if self.current:self.library.favorite(self.current);self.refresh_saved();self.star.setText('取消收藏' if str(self.current) in self.library.preferences().get('favorites',[]) else '收藏')
    def go_back(self):
        if self.back_stack and self.can_leave(self.go_back):self.open_file(self.back_stack.pop(),False)
    def find_next(self):
        if self.find.text() and not self.reader.find(self.find.text()):self.reader.moveCursor(QTextCursor.MoveOperation.Start);self.reader.find(self.find.text())
    def jump(self,item):
        cursor=self.reader.textCursor();cursor.setPosition(item.data(Qt.ItemDataRole.UserRole));self.reader.setTextCursor(cursor);self.reader.ensureCursorVisible()
    def link(self,url):
        if url.toString().startswith('#'):self.reader.scrollToAnchor(url.fragment());return
        resolved=self.reader.document().baseUrl().resolved(url)
        if resolved.isLocalFile():
            self.open_file(resolved.toLocalFile())
            if resolved.fragment():self.reader.scrollToAnchor(resolved.fragment())
        elif resolved.scheme() in ('https','http'):QDesktopServices.openUrl(resolved)
        else:self.status.setText('不支持打开此类型的链接')
    def start_search(self):
        root=self.library.preferences().get('root');query=self.search.text().strip()
        if not root or not query:return
        self.cancel.set();self.cancel=threading.Event();cancel=self.cancel;ticket=uuid.uuid4().hex;self.ticket=ticket;self.status.setText('正在后台搜索…');self.navigation.setCurrentWidget(self.results)
        def work():
            try:rows,limited=self.library.search(query,Path(root),cancel);error=''
            except Exception as exc:rows=[];limited=False;error=str(exc)
            if not cancel.is_set():
                try:self.searched.emit(ticket,rows,limited,error)
                except RuntimeError:pass
        threading.Thread(target=work,daemon=True,name='markdown-search').start()
    def search_finished(self,ticket,rows,limited,error):
        if ticket!=self.ticket:return
        self.results.clear()
        for row in rows:
            item=QListWidgetItem(row['label']+'\n'+row['snippet']);item.setData(Qt.ItemDataRole.UserRole,row['path']);self.results.addItem(item)
        self.status.setText(error or f'找到 {len(rows)} 项'+(' · 已达到搜索上限，请细化关键词（最多扫描 3000 篇，显示 100 项）' if limited else ''))
