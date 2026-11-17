from datetime import date,timedelta
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QListWidget,QPlainTextEdit,QPushButton,QMessageBox,QSplitter
from ..modules.day_plan import BASE,EVENINGS
class WeeklyPlanPage(QWidget):
 def __init__(self,hub,parent=None):
  super().__init__(parent);self.hub=hub;self.current=None;box=QVBoxLayout(self);box.setContentsMargins(28,24,28,24);title=QLabel('每周节奏 · 为生活留出位置');title.setObjectName('title');box.addWidget(title);box.addWidget(QLabel('计划只是安排，不代表已经完成；每个工作日可以有不同节奏。'))
  split=QSplitter();self.days=QListWidget();self.days.addItems(['周一 · 学习主攻','周二 · 副业攻坚','周三 · 学习与兴趣','周四 · 学习强化','周五 · 自由创造','周六 · 自主安排','周日 · 休息与复盘','晚归日','晚归次日']);split.addWidget(self.days);pane=QWidget();right=QVBoxLayout(pane);self.heading=QLabel();self.heading.setObjectName('title');right.addWidget(self.heading);self.editor=QPlainTextEdit();self.editor.setPlaceholderText('时间段 · 安排；每行一项，可以自由调整');right.addWidget(self.editor);save=QPushButton('保存这一天的安排');save.clicked.connect(self.save);right.addWidget(save);split.addWidget(pane);split.setSizes([260,740]);box.addWidget(split,1);self.days.currentRowChanged.connect(self.select);self.days.setCurrentRow(date.today().weekday());self.draft_timer=QTimer(self);self.draft_timer.setSingleShot(True);self.draft_timer.setInterval(600);self.draft_timer.timeout.connect(self.can_leave);self.editor.textChanged.connect(lambda:self.draft_timer.start());hub.closed.connect(self.can_leave)
 def defaults(self,i):
  if i<5:return '\n'.join(t+' · '+v for t,v in sorted(BASE+EVENINGS[i]))
  if i==7:return '午休空余 · 学习20分钟\n18:10–20:00 · 机动时间\n20:00–23:00 · 游戏或活动\n23:00以后 · 洗漱、安静入睡'
  if i==8:return '07:20–08:00 · 学习40分钟\n08:00–08:20 · 早餐、准备出门'
  return ''
 def select(self,i):
  if self.current is not None and self.editor.document().isModified():self.hub.db.set('weekly_plan:'+str(self.current),self.editor.toPlainText())
  self.current=i;self.heading.setText(self.days.item(i).text());self.editor.setPlainText(self.hub.db.get('weekly_plan:'+str(i),self.defaults(i)));self.editor.document().setModified(False)
 def save(self):
  self.hub.db.set('weekly_plan:'+str(self.current),self.editor.toPlainText());self.editor.document().setModified(False);QMessageBox.information(self,'已保存','每周计划已保存。切换日期也会自动保存草稿。')
 def can_leave(self,*args):
  if self.current is not None:self.hub.db.set('weekly_plan:'+str(self.current),self.editor.toPlainText());self.editor.document().setModified(False)
  return True
