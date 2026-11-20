from datetime import date
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QListWidget,QListWidgetItem,QLabel,QMessageBox,QPushButton
from ..modules.review_plan import ReviewPlan

def review_page(page):
 service=ReviewPlan(page.hub.db);dlg=QWidget();box=QVBoxLayout(dlg);box.addWidget(QLabel('按实际回忆结果选择；不会自动提高知识点熟悉度或发放掌握奖励。'));items=QListWidget();box.addWidget(items)
 def refresh():
  items.clear()
  for r in service.rows():
   item=QListWidgetItem(('今日待复习' if r['due']<=date.today().isoformat() else r['due'])+' · '+r['title']+'\n'+r['question']);item.setData(Qt.ItemDataRole.UserRole,r);items.addItem(item)
 def answer(rating):
  if not items.currentItem():return
  try:service.answer(items.currentItem().data(Qt.ItemDataRole.UserRole)['id'],rating);refresh()
  except ValueError as e:QMessageBox.information(dlg,'复习',str(e))
 row=QHBoxLayout();box.addLayout(row)
 for title in ('忘记','模糊','记住','熟练'):
  b=QPushButton(title);b.clicked.connect(lambda checked=False,t=title:answer(t));row.addWidget(b)
 dlg.refresh=refresh
 return dlg

def archive_page(page):
    from PySide6.QtWidgets import QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView
    pane=QWidget()
    box=QVBoxLayout(pane)
    title=QLabel('复习档案')
    box.addWidget(title)
    table=QTableWidget(0,4)
    table.setHorizontalHeaderLabels(['复习日期','知识点 / 错题','回忆结果','下次复习'])
    table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch)
    table.verticalHeader().hide()
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setAlternatingRowColors(True)
    box.addWidget(table)
    def refresh():
        with page.hub.db.connect() as c:
            rows=c.execute("""SELECT a.day,n.title || CASE WHEN p.error='' THEN '' ELSE ' · 错题' END,
                a.rating,a.next_due FROM review_attempts a JOIN review_plan p ON p.id=a.card
                JOIN learning_nodes n ON n.id=p.unit ORDER BY a.created DESC,a.rowid DESC""").fetchall()
        title.setText(f'复习档案 · {len(rows)} 次回忆记录')
        table.setRowCount(len(rows))
        for i,r in enumerate(rows):
            for k,value in enumerate(r):table.setItem(i,k,QTableWidgetItem(value))
    pane.refresh=refresh
    return pane

def error_page(page):
 from PySide6.QtWidgets import QFileDialog,QInputDialog
 from pathlib import Path
 service=ReviewPlan(page.hub.db);dlg=QWidget();box=QVBoxLayout(dlg);items=QListWidget();box.addWidget(items)
 with page.hub.db.connect() as c:c.execute('CREATE TABLE IF NOT EXISTS error_labels(id TEXT PRIMARY KEY,category TEXT,important INTEGER)')
 def refresh():
  items.clear()
  with page.hub.db.connect() as c:labels={r['id']:dict(r) for r in c.execute('SELECT * FROM error_labels')}
  for r in page.hub.learning.errors():
   meta=labels.get(r['id'],{});r.update(meta);item=QListWidgetItem(('★ 高频 · ' if r.get('important') else '')+r.get('category','未分类')+' · '+r['title']+'\n'+r['note']);item.setData(Qt.ItemDataRole.UserRole,r);items.addItem(item)
 def selected():return items.currentItem().data(Qt.ItemDataRole.UserRole) if items.currentItem() else None
 def tag():
  r=selected()
  if not r:return
  category,ok=QInputDialog.getText(dlg,'归类','分类名称',text=r.get('category',''))
  if not ok:return
  important=QMessageBox.question(dlg,'高频考点','标记为高频考点？')==QMessageBox.StandardButton.Yes
  with page.hub.db.connect() as c:c.execute('INSERT INTO error_labels VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET category=excluded.category,important=excluded.important',(r['id'],category[:80],int(important)))
  refresh()
 def plan():
  r=selected()
  if r:service.add(r['unit'],r['id']);QMessageBox.information(dlg,'已加入','错题已加入复习计划。')
 def export():
  path,_=QFileDialog.getSaveFileName(dlg,'导出错题集','错题集.md','Markdown (*.md)')
  if path:Path(path).write_text('# 错题集\n\n'+'\n\n'.join(items.item(i).text() for i in range(items.count())),encoding='utf-8')
 for title,action in [('分类 / 高频标记',tag),('加入复习计划',plan),('导出错题集',export)]:
  b=QPushButton(title);b.clicked.connect(action);box.addWidget(b)
 dlg.refresh=refresh;return dlg
