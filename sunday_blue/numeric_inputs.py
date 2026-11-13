"""Numeric editors: editable digits only; units are inert QLabel adornments."""
from PySide6.QtCore import Qt,QEvent,QTimer,QSize
from PySide6.QtWidgets import QSpinBox as QtSpinBox,QDoubleSpinBox as QtDoubleSpinBox,QLabel
class NumericMixin:
 def __init__(self,*a,**kw):
  super().__init__(*a,**kw);self._unit=QLabel(self);self._unit.setTextFormat(Qt.TextFormat.PlainText);self._unit.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents);self._unit.setObjectName('muted');self._unit.hide();self._first_focus=False;self.lineEdit().installEventFilter(self)
 def setSuffix(self,text):self._unit.setText(str(text).strip());self._unit.setVisible(bool(text));self._place_unit();self.updateGeometry()
 def setPrefix(self,text):self.setSuffix(text)
 def _place_unit(self):
  if not hasattr(self,'_unit'):return
  edit=self.lineEdit();width=self._unit.fontMetrics().horizontalAdvance(self._unit.text())+12 if self._unit.text() else 0
  edit.setTextMargins(0,0,width,0);r=edit.geometry();self._unit.setGeometry(r.right()-width,r.top(),width,r.height());self._unit.raise_()
 def resizeEvent(self,event):super().resizeEvent(event);self._place_unit()
 def sizeHint(self):
  size=super().sizeHint();extra=self._unit.fontMetrics().horizontalAdvance(self._unit.text())+12 if hasattr(self,'_unit') and self._unit.text() else 0
  return QSize(size.width()+extra,size.height())
 def focusInEvent(self,event):
  super().focusInEvent(event);self._first_focus=True;QTimer.singleShot(0,self.lineEdit().selectAll)
 def focusOutEvent(self,event):
  self._first_focus=False;super().focusOutEvent(event)
 def eventFilter(self,obj,event):
  if obj is self.lineEdit():
   if event.type()==QEvent.Type.FocusIn:self._first_focus=True;QTimer.singleShot(0,self.lineEdit().selectAll)
   elif event.type()==QEvent.Type.MouseButtonRelease and self._first_focus:self._first_focus=False;QTimer.singleShot(0,self.lineEdit().selectAll)
   elif event.type()==QEvent.Type.FocusOut:self._first_focus=False
  return super().eventFilter(obj,event)
 def wheelEvent(self,event):
  if self.hasFocus():super().wheelEvent(event)
  else:event.ignore()
class NumberSpin(NumericMixin,QtSpinBox):pass
class DecimalSpin(NumericMixin,QtDoubleSpinBox):pass
