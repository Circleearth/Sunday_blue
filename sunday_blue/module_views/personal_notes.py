from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QSplitter,QListWidget,QListWidgetItem,QLineEdit,QPlainTextEdit,QPushButton,QLabel,QFileDialog,QMessageBox,QTabWidget
from PySide6.QtCore import Qt,QTimer
from ..modules.personal_notes import PersonalNotes
class PersonalNotesPage(QWidget):
 def __init__(self,hub,parent=None):
  super().__init__(parent);self.hub=hub;self.service=PersonalNotes(hub.db);box=QVBoxLayout(self);box.setContentsMargins(24,24,24,24);heading=QLabel('随手记 · 把念头留在这里');heading.setObjectName('title');box.addWidget(heading);self.location=QLabel(str(self.service.directory()));self.location.setWordWrap(True);box.addWidget(self.location)
  split=QSplitter();self.tabs=QTabWidget();self.items=QListWidget();left=QWidget();nav=QVBoxLayout(left);search=QLineEdit();search.setPlaceholderText('筛选日期或标题');nav.addWidget(search);nav.addWidget(self.items,1);search.textChanged.connect(lambda q:[self.items.item(i).setHidden(q.casefold() not in self.items.item(i).text().casefold()) for i in range(self.items.count())]);split.addWidget(left);right=QWidget();layout=QVBoxLayout(right);self.title=QLineEdit();self.title.setPlaceholderText('这条笔记的标题');layout.addWidget(self.title);self.body=QPlainTextEdit();self.body.setPlaceholderText('灵感、杂念、想记住的事。保留原文，保存后按年月归档为 Markdown。');self.tabs.addTab(self.body,"写作");layout.addWidget(self.tabs,1);self.preview=QPlainTextEdit();self.preview.setReadOnly(True);self.preview.setPlaceholderText('点击左侧笔记查看已保存原文');self.tabs.addTab(self.preview,"阅读原文");split.addWidget(right);split.setSizes([280,720]);box.addWidget(split,1)
  row=QHBoxLayout();box.addLayout(row)
  for text,fn in [('保存这条笔记',self.save),('基于所选笔记续写',self.continue_note),('选择保存目录',self.choose),('刷新笔记列表',self.refresh)]:
   b=QPushButton(text);b.clicked.connect(fn);row.addWidget(b)
  self.items.currentItemChanged.connect(self.inspect);self.refresh();draft=hub.db.get('personal_notes_draft',{});self.title.setText(draft.get('title',''));self.body.setPlainText(draft.get('body',''));self.draft_timer=QTimer(self);self.draft_timer.setSingleShot(True);self.draft_timer.setInterval(600);self.draft_timer.timeout.connect(self.store_draft);self.title.textChanged.connect(lambda:self.draft_timer.start());self.body.textChanged.connect(lambda:self.draft_timer.start());hub.closed.connect(self.store_draft)
 def continue_note(self):
  item=self.items.currentItem()
  if not item:return
  if (self.title.text().strip() or self.body.toPlainText().strip()) and not self.can_leave():return
  r=item.data(Qt.ItemDataRole.UserRole)
  try:self.tabs.setCurrentWidget(self.body);self.title.setText(r['title']+' · 续记');self.body.setPlainText(self.service.read(r['id']).split('\n\n',2)[-1])
  except Exception as e:QMessageBox.warning(self,'无法续写',str(e))
 def store_draft(self):self.hub.db.set('personal_notes_draft',{'title':self.title.text(),'body':self.body.toPlainText()})
 def save(self):
  try:
   path=self.service.save(self.title.text(),self.body.toPlainText());self.title.clear();self.body.clear();self.body.document().setModified(False);self.refresh();self.location.setText('已保存：'+path);self.store_draft()
  except Exception as e:QMessageBox.warning(self,'未保存',str(e))
 def choose(self):
  path=QFileDialog.getExistingDirectory(self,'选择笔记根目录',str(self.service.directory()))
  if path:self.hub.db.set('personal_notes_dir',path);self.location.setText(path+'（新笔记使用这里，旧笔记保持原位置）')
 def refresh(self):
  self.items.clear()
  for r in self.service.rows():
   item=QListWidgetItem(r['created'][:10]+' · '+r['title']);item.setData(Qt.ItemDataRole.UserRole,r);self.items.addItem(item)
 def inspect(self,*args):
  item=self.items.currentItem()
  if item:
   try:self.tabs.setCurrentWidget(self.preview);self.preview.setPlainText(self.service.read(item.data(Qt.ItemDataRole.UserRole)['id']))
   except Exception as e:self.preview.setPlainText('读取失败：'+str(e))
 def can_leave(self,*args):
  if not self.body.toPlainText().strip() and not self.title.text().strip():return True
  answer=QMessageBox.question(self,'尚未保存','先保存当前笔记再离开？',QMessageBox.StandardButton.Save|QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel)
  if answer==QMessageBox.StandardButton.Save:self.save();return not self.body.toPlainText().strip()
  if answer==QMessageBox.StandardButton.Discard:self.body.clear();self.title.clear();return True
  return False
