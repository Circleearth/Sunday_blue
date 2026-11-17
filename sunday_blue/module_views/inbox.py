import json
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QListWidget,QListWidgetItem,QPlainTextEdit,QComboBox,QLabel,QPushButton,QCheckBox,QMessageBox,QSplitter,QWidget

def show_inbox(page):
 hub=page.hub;service=hub.inbox_assistant;dlg=QDialog(page);dlg.setWindowTitle('灵感收件箱 · 原文与整理分开');area=dlg.screen().availableGeometry();dlg.resize(min(980,area.width()-40),min(680,area.height()-40));box=QVBoxLayout(dlg);auto=QCheckBox('空闲时自动整理（每天最多8次模型请求；专注时暂停）');auto.setChecked(hub.db.get('inbox_auto',True));auto.toggled.connect(lambda v:hub.db.set('inbox_auto',v));box.addWidget(auto)
 split=QSplitter();items=QListWidget();split.addWidget(items);panel=QWidget();right=QVBoxLayout(panel);status=QLabel();status.setWordWrap(True);right.addWidget(status);original=QPlainTextEdit();original.setReadOnly(True);right.addWidget(QLabel('完整原文（只读）'));right.addWidget(original);category=QComboBox();category.addItems(hub.organizer.categories());right.addWidget(category);summary=QPlainTextEdit();summary.setPlaceholderText('整理摘要');right.addWidget(summary);todos=QPlainTextEdit();todos.setPlaceholderText('确认要创建的任务，每行一项；可删除不需要的建议');right.addWidget(todos);split.addWidget(panel);box.addWidget(split,1)
 def selected():return items.currentItem().data(Qt.ItemDataRole.UserRole) if items.currentItem() else None
 def inspect():
  r=selected()
  if not r:return
  p=service.proposal(r['id']) or {};original.setPlainText(r['body']);summary.setPlainText(p.get('summary',''));todos.setPlainText('\n'.join(json.loads(p.get('todos','[]'))));category.setCurrentText(p.get('category') or '收件箱');status.setText(p.get('error') or {'running':'后台正在整理；可以关闭窗口继续学习。','ready':'请核对摘要和任务后确认。原文不会改变。','accepted':'已确认；任务已进入工作页，不重复创建。'}.get(p.get('state'),'等待整理；可以手动开始。'))
 def refresh():
  current=selected();key=current['id'] if current else None;items.clear()
  for r in hub.duties.handoffs(True):
   p=service.proposal(r['id']) or {};item=QListWidgetItem(r['title']+' · '+{'pending':'待整理','running':'整理中','ready':'待核对','accepted':'已确认','done':'已完成','failed':'待重试'}.get(p.get('state',r['status']),'待处理'));item.setData(Qt.ItemDataRole.UserRole,r);items.addItem(item)
   if r['id']==key:items.setCurrentItem(item)
  if items.currentRow()<0 and items.count():items.setCurrentRow(0)
  inspect()
 def run():
  r=selected()
  if r and not service.pump(r['id']):QMessageBox.information(dlg,'暂未开始','已有任务运行、今日额度用完、交接已完成，或整理员尚未绑定。')
 def accept():
  r=selected()
  if not r:return
  if QMessageBox.question(dlg,'确认整理','保留原文，保存摘要，并将列出的事项创建为工作页任务。确认？')!=QMessageBox.StandardButton.Yes:return
  try:service.accept(r['id'],category.currentText(),summary.toPlainText(),[t.strip() for t in todos.toPlainText().splitlines() if t.strip()]);refresh()
  except Exception as e:QMessageBox.warning(dlg,'尚未确认',str(e))
 row=QHBoxLayout();box.addLayout(row)
 for title,fn in [('开始 / 重试整理',run),('确认摘要与任务',accept),('刷新列表',refresh),('关闭',dlg.close)]:
  b=QPushButton(title);b.clicked.connect(fn);row.addWidget(b)
 def notify():status.setText('后台处理状态已更新，点击刷新列表查看；当前编辑内容未覆盖。')
 service.changed.connect(notify)
 items.currentItemChanged.connect(lambda *_:inspect());refresh()
 try:dlg.exec()
 finally:service.changed.disconnect(notify)
