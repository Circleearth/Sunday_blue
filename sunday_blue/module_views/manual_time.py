from PySide6.QtWidgets import QDateTimeEdit,QMessageBox
from PySide6.QtCore import QDateTime
from .module_forms import form_dialog
from ..modules.manual_time import record

def show_backfill(page,category,node):
 dlg,form,error,buttons=form_dialog(page,'补报遗漏时间');start=QDateTimeEdit(QDateTime.currentDateTime().addSecs(-1800));end=QDateTimeEdit(QDateTime.currentDateTime())
 for text,w in [('开始时间',start),('结束时间',end)]:w.setCalendarPopup(True);w.setDisplayFormat('yyyy-MM-dd HH:mm');form.addRow(text,w)
 error.setText('补报计入实际时长；学习不补发金币，工作计入积分。请勿重复记录。')
 def save():
  if QMessageBox.question(dlg,'确认补报','确认这段时间确实完成且未被记录？')!=QMessageBox.StandardButton.Yes:return
  page.save_dialog(dlg,error,lambda:record(page.hub.db,category,node,start.dateTime().toPython().astimezone().isoformat(),end.dateTime().toPython().astimezone().isoformat()))
 buttons.accepted.connect(save);dlg.exec()
