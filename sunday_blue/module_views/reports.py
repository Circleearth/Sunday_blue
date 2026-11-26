"""Saved daily/period reports with copyable facts and asynchronous role commentary."""
from PySide6.QtCore import QDate,Qt
from PySide6.QtWidgets import QVBoxLayout,QHBoxLayout,QListWidget,QListWidgetItem,QPlainTextEdit,QDialog,QDateEdit,QApplication,QLabel,QPushButton,QScrollArea
from .module_forms import ModulePage,button
from .life_widgets import label,card
from ..art_assets import ArtworkSlot
from ..modules.database import day as living_day
class ReportsPage(ModulePage):
 module='reports'
 def __init__(self,hub,parent=None):
  super().__init__(parent);self.hub=hub;box=self.layout_header('结算与回顾','上报前一天生活后生成日结算；周期报告使用截止日前的完整日期，不重复发金币。');row=QHBoxLayout();self.day=QDateEdit(self.latest_complete_day());self.day.setCalendarPopup(True);self.day.setMaximumDate(self.latest_complete_day());row.addWidget(self.day);button('查看该日结算',self.generate,row,True);self.open_button=button('打开选中报告',self.open_selected,row);self.copy_button=button('复制',self.copy_selected,row);box.addLayout(row)
  self.items=QListWidget();self.items.setWordWrap(True);self.items.currentRowChanged.connect(self.update_actions);self.items.itemDoubleClicked.connect(lambda *_:self.open_selected());box.addWidget(self.items,1);self.dialog=None;hub.reports.ready.connect(lambda *_:self.refresh());hub.report_open.connect(self.show_report);self.refresh()
 @staticmethod
 def latest_complete_day():
  return QDate.fromString(living_day(),'yyyy-MM-dd').addDays(-1)

 def showEvent(self,event):
  super().showEvent(event)
  latest=self.latest_complete_day()
  was_latest=self.day.date()==self.day.maximumDate()
  self.day.setMaximumDate(latest)
  if was_latest:self.day.setDate(latest)

 def update_actions(self,*_):
  found=bool(self.items.currentItem())
  self.open_button.setEnabled(found)
  self.copy_button.setEnabled(found)

 def refresh(self):
  current=self.items.currentItem();rid=current.data(Qt.ItemDataRole.UserRole)['id'] if current else None;self.items.clear()
  for r in self.hub.reports.rows():
   item=QListWidgetItem(f"{r['start']} → {r['end']}（不含截止日） · "+{'day':'日结算','week':'周报','month':'月报','year':'年报'}[r['kind']]+' · '+{'queued':'等待评价','running':'正在评价','done':'已完成','fallback':'本次未评价'}[r['state']]);item.setData(Qt.ItemDataRole.UserRole,r);self.items.addItem(item)
   if r['id']==rid:self.items.setCurrentItem(item)
  self.update_actions()
 def generate(self):
  from datetime import date,timedelta
  day=self.day.date().toString('yyyy-MM-dd');rid='day:'+day+':'+(date.fromisoformat(day)+timedelta(days=1)).isoformat()
  if self.hub.reports.get(rid):self.show_report(rid)
  else:
   from PySide6.QtWidgets import QMessageBox
   QMessageBox.information(self,'尚无该日报告','请在生活上报中填写或修改该日资料，保存时统一生成结算。')
 def selected(self):
  item=self.items.currentItem();return item.data(Qt.ItemDataRole.UserRole) if item else None
 def copy_selected(self):
  r=self.selected()
  if r:
   QApplication.clipboard().setText(r['body']+'\n\n角色评价：'+r['comment'])
   self.copy_button.setText('已复制')
   from PySide6.QtCore import QTimer
   QTimer.singleShot(1800,self.copy_button,lambda:self.copy_button.setText('复制'))
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
  actions=QHBoxLayout();box.addLayout(actions);button('复制结算与评价',lambda:QApplication.clipboard().setText(body.toPlainText()+'\n\n角色评价：'+bubble.text()),actions,True);button('重新生成评价',lambda:self.invoke(lambda:self.hub.reports.retry(rid)),actions);button('关闭',dlg.close,actions);update();dlg.show()
