"""Saved revision viewer: bounded colored diff and full before/after snapshots."""
from html import escape
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QSplitter,QListWidget,QListWidgetItem,QTabWidget,QTextBrowser,QPlainTextEdit,QLabel

class RevisionDialog(QDialog):
    def __init__(self,rows,changes,parent=None):
        super().__init__(parent);self.changes=changes;self.setWindowTitle('已保存的文档修订');self.resize(950,650)
        layout=QVBoxLayout(self);layout.addWidget(QLabel('绿色为新增，红色为删除；此处查看保存历史，不会自动接受、撤销或覆盖文件。'))
        split=QSplitter();layout.addWidget(split);self.items=QListWidget();split.addWidget(self.items);tabs=QTabWidget();split.addWidget(tabs);split.setStretchFactor(1,1)
        self.diff=QTextBrowser();self.diff.setOpenLinks(False);tabs.addTab(self.diff,'增删差异')
        self.before=QPlainTextEdit();self.after=QPlainTextEdit()
        for name,w in [('修改前',self.before),('修改后',self.after)]:w.setReadOnly(True);tabs.addTab(w,name)
        for row in rows:
            item=QListWidgetItem(row['created']+' · '+row['actor']+'\n'+{'saved':'已保存并交接','prepared':'待核对 / 待补交接','not_applied':'未写入'}.get(row['state'],row['state']));item.setData(Qt.ItemDataRole.UserRole,row['id']);self.items.addItem(item)
        self.items.currentItemChanged.connect(self.select)
        if rows:self.items.setCurrentRow(0)
    def select(self,item,*args):
        if not item:return
        row=self.changes.get(item.data(Qt.ItemDataRole.UserRole));self.before.setPlainText(row['before_text']);self.after.setPlainText(row['after_text'])
        lines=[]
        for line in self.changes.difference(row['before_text'],row['after_text']).splitlines():
            color='#136c40' if line.startswith('+') else '#a02c38' if line.startswith('-') else self.palette().text().color().name()
            lines.append('<div style="white-space:pre-wrap;color:'+color+'">'+escape(line)+'</div>')
        self.diff.setHtml(''.join(lines))
