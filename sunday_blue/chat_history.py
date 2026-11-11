"""Read-only dated history, bounded pages independent of the live composer."""
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QComboBox,QPushButton,QLabel,QTextBrowser
from .storage import plain

class ChatHistory(QDialog):
    def __init__(self,store,sid,parent=None):
        super().__init__(parent);self.store=store;self.sid=sid;self.cursors=[None];self.setWindowTitle('历史记录 · '+store.session(sid)['title']);self.resize(680,640)
        layout=QVBoxLayout(self);row=QHBoxLayout();self.days=QComboBox()
        for day,count in store.message_days(sid):self.days.addItem(f'{day} · {count} 条',day)
        row.addWidget(QLabel('按天查看'));row.addWidget(self.days,1);layout.addLayout(row)
        self.view=QTextBrowser();self.view.setOpenExternalLinks(False);layout.addWidget(self.view,1)
        self.status=QLabel();layout.addWidget(self.status);row=QHBoxLayout();self.newer=QPushButton('较新一页');self.older=QPushButton('更早一页');row.addWidget(self.newer);row.addWidget(self.older);layout.addLayout(row)
        self.days.currentIndexChanged.connect(self.change_day);self.newer.clicked.connect(self.previous);self.older.clicked.connect(self.next);self.load()
    def change_day(self,*args):self.cursors=[None];self.load()
    def load(self):
        from html import escape
        day=self.days.currentData();self.rows,more=self.store.message_page(self.sid,20,day,self.cursors[-1]) if day else ([],False)
        pieces=[]
        for m in self.rows:
            text=plain(m['content']).strip()
            if not text:continue
            name='我' if m['role']=='user' else '角色' if m['role']=='assistant' else m['role']
            pieces.append('<p><b>'+escape(name)+' · '+escape(m['created'])+'</b></p><p style="white-space:pre-wrap">'+escape(text)+'</p><hr>')
        self.view.setHtml(''.join(pieces) or '<p>这一页没有可显示的文本消息。</p>')
        self.newer.setEnabled(len(self.cursors)>1);self.older.setEnabled(more)
        self.status.setText(f'第 {len(self.cursors)} 页 · 每页最多 20 条 · 仅浏览，不改变聊天上下文')
    def next(self):
        if self.rows:self.cursors.append(self.rows[0]['id']);self.load()
    def previous(self):
        if len(self.cursors)>1:self.cursors.pop();self.load()
