"""Saved daily/period reports with copyable facts and asynchronous role commentary."""
from PySide6.QtCore import QDate,Qt
from PySide6.QtWidgets import QVBoxLayout,QHBoxLayout,QListWidget,QListWidgetItem,QPlainTextEdit,QDialog,QDateEdit,QApplication,QLabel,QPushButton,QScrollArea
from .module_forms import ModulePage,button
from .life_widgets import label,card
from ..art_assets import ArtworkSlot
class ReportsPage(ModulePage):
 module='reports'
 def __init__(self,hub,parent=None):
  super().__init__(parent);self.hub=hub;box=self.layout_header('结算与回顾','上报前一天生活后生成日结算；周期报告使用截止日前的完整日期，不重复发金币。');row=QHBoxLayout();self.day=QDateEdit(QDate.currentDate().addDays(-1));self.day.setCalendarPopup(True);self.day.setMaximumDate(QDate.currentDate().addDays(-1));row.addWidget(self.day);button('生成 / 更新日结算',self.generate,row,True);button('查看所选报告',self.open_selected,row);button('复制所选报告',self.copy_selected,row);box.addLayout(row)
  self.items=QListWidget();self.items.setWordWrap(True);self.items.itemDoubleClicked.connect(lambda *_:self.open_selected());box.addWidget(self.items,1);self.dialog=None;hub.reports.ready.connect(lambda *_:self.refresh());hub.report_open.connect(self.show_report);self.refresh()
 def refresh(self):
  current=self.items.currentItem();rid=current.data(Qt.ItemDataRole.UserRole)['id'] if current else None;self.items.clear()
  for r in self.hub.reports.rows():
   item=QListWidgetItem(f"{r['start']} → {r['end']}（不含截止日） · "+{'day':'日结算','week':'周报','month':'月报','year':'年报'}[r['kind']]+' · '+{'queued':'等待评价','running':'正在评价','done':'已完成','fallback':'本次未评价'}[r['state']]);item.setData(Qt.ItemDataRole.UserRole,r);self.items.addItem(item)
   if r['id']==rid:self.items.setCurrentItem(item)
 def generate(self):
  rid=self.invoke(lambda:self.hub.reports.daily(self.day.date().toString('yyyy-MM-dd')))
  if rid:self.show_report(rid)
 def selected(self):
  item=self.items.currentItem();return item.data(Qt.ItemDataRole.UserRole) if item else None
 def copy_selected(self):
  r=self.selected()
  if r:QApplication.clipboard().setText(r['body']+'\n\n角色评价：'+r['comment'])
 def open_selected(self):
  r=self.selected()
  if r:self.show_report(r['id'])
 def show_report(self,rid):
  if self.dialog:self.dialog.close();self.dialog.deleteLater()
  dlg=QDialog(self);self.dialog=dlg;dlg.setWindowTitle('结算与回顾 · 每一份投入都记下');available=dlg.screen().availableGeometry();dlg.resize(min(900,available.width()-40),min(650,available.height()-40));box=QVBoxLayout(dlg);box.addWidget(label('每一份投入，都已经记下。','title'));row=QHBoxLayout();body=QPlainTextEdit();body.setReadOnly(True);row.addWidget(body,3);side,sl=card('陪伴评价');art=ArtworkSlot(self.hub.root,'settlement_host');art.setMinimumHeight(220);sl.addWidget(art,1);bubble=label('正在整理评价…','lifeAdvice');bubble.setTextFormat(Qt.TextFormat.PlainText);scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(bubble);scroll.setMaximumHeight(230);scroll.setMinimumHeight(110);sl.addWidget(scroll);row.addWidget(side,2);box.addLayout(row)
  def update(key=None):
   r=self.hub.reports.get(rid)
   if r:body.setPlainText(r['body']);bubble.setText(r['comment'] or ('事实已保存，角色评价正在排队。' if r['state']=='queued' else '正在整理评价…'))
  self.hub.reports.ready.connect(update)
  dlg.finished.connect(lambda *_:self.hub.reports.ready.disconnect(update))
  actions=QHBoxLayout();box.addLayout(actions);button('复制结算与评价',lambda:QApplication.clipboard().setText(body.toPlainText()+'\n\n角色评价：'+bubble.text()),actions,True);button('关闭',dlg.close,actions);update();dlg.show()
