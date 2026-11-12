"""Work, daily life and duty-slot views. Domain services own validation and all writes."""
from datetime import date
import json
from PySide6.QtCore import Qt,QDate,QTimer
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QPushButton,
    QLineEdit,QPlainTextEdit,QComboBox,QCheckBox,QSpinBox,QDoubleSpinBox,QDateEdit,
    QFrame,QTreeWidget,QTreeWidgetItem,QListWidget,QListWidgetItem,QProgressBar,QTabWidget,
    QDialog,QDialogButtonBox,QMessageBox,QInputDialog,QScrollArea)
from ..roles import list_roles
from ..modules.life_state import MUSCLES

STATUS={'todo':'待开始','doing':'进行中','paused':'暂缓','done':'已完成'}
INTENSITY={'light':'轻','moderate':'中','high':'高'}

def button(text,fn,layout,primary=False):
    widget=QPushButton(text)
    if primary:widget.setObjectName('primary')
    widget.clicked.connect(fn);layout.addWidget(widget);return widget

def hm_pair(default_minutes=None):
    """Aligned input: [x] 小时 [x] 分钟. Empty boxes show the grey hint 未记录;
    typing a digit takes effect immediately. .value() -> total minutes, None
    only when both boxes are still empty. .load(minutes or None)."""
    widget=QWidget();row=QHBoxLayout(widget);row.setContentsMargins(0,0,0,0)
    hours=PlaceholderSpin(zero_is_placeholder=True);mins=PlaceholderSpin(zero_is_placeholder=True)
    hours.setRange(-1,24);mins.setRange(-1,59)
    hours.setValue((default_minutes or 0)//60 if default_minutes is not None else -1)
    mins.setValue((default_minutes or 0)%60 if default_minutes is not None else -1)
    def _v(spin):return spin.value() if spin.value()>=0 else 0
    widget.value=lambda:(_v(hours)*60+_v(mins) if hours.value()>=0 or mins.value()>=0 else None)
    def load(m):
        if m is None:hours.setValue(-1);mins.setValue(-1)
        else:hours.setValue(m//60);mins.setValue(m%60)
    widget.load=load
    widget.hours=hours;widget.mins=mins
    row.addWidget(hours);row.addWidget(QLabel(' 小时'));row.addWidget(mins);row.addWidget(QLabel(' 分钟'));row.addStretch()
    return widget

def clock_pair():
    """Required clock time as [x] 小时 [x] 分钟, both starting empty with the
    grey hint 未记录. Typing one box takes effect immediately; an untouched box
    counts as 0 (6 小时 + empty = 06:00).
    .value() -> 'HH:mm' or None (both boxes empty). .load('HH:mm' or None)."""
    widget=QWidget();row=QHBoxLayout(widget);row.setContentsMargins(0,0,0,0)
    hours=PlaceholderSpin();mins=PlaceholderSpin();hours.setRange(-1,23);mins.setRange(-1,59)
    hours.setValue(-1);mins.setValue(-1)
    widget.value=lambda:('%02d:%02d'%(max(0,hours.value()),max(0,mins.value())) if hours.value()>=0 or mins.value()>=0 else None)
    def load(text):
        if text:
            a,b=text.split(':');hours.setValue(int(a));mins.setValue(int(b))
        else:hours.setValue(-1);mins.setValue(-1)
    widget.load=load
    widget.hours=hours;widget.mins=mins
    row.addWidget(hours);row.addWidget(QLabel(' 小时'));row.addWidget(mins);row.addWidget(QLabel(' 分钟'));row.addStretch()
    return widget

class PlaceholderSpin(QSpinBox):
    """Grey placeholder hint instead of an uneditable special value: while the
    box is empty its text is genuinely '', so a typed digit lands immediately
    in either focus state (click or Tab) — no select-all needed first."""
    def __init__(self,placeholder='未记录',zero_is_placeholder=False,parent=None):
        super().__init__(parent)
        self.zero_is_placeholder=zero_is_placeholder
        self.lineEdit().setPlaceholderText(placeholder)
    def textFromValue(self,value):
        if value<0 or (value==0 and self.zero_is_placeholder):return ''
        return str(value)
    def valueFromText(self,text):
        try:return int(text)
        except ValueError:return -1 if self.minimum()<0 else 0
    def displayText(self,value):
        return '' if self.textFromValue(value)=='' else super().displayText(value)

def form_dialog(parent,title):
    dialog=QDialog(parent);dialog.setWindowTitle(title);dialog.setMinimumWidth(450)
    layout=QVBoxLayout(dialog);form=QFormLayout();form.setSpacing(12);layout.addLayout(form)
    error=QLabel();error.setWordWrap(True);layout.addWidget(error)
    buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
    buttons.rejected.connect(dialog.reject);layout.addWidget(buttons)
    return dialog,form,error,buttons

def spin(value=0,maximum=100000,suffix='',placeholder='未设置',zero_placeholder=False):
    widget=PlaceholderSpin(placeholder=placeholder,zero_is_placeholder=zero_placeholder);widget.setRange(0,maximum);widget.setValue(round(value or 0));widget.setSuffix(suffix);return widget

class ModulePage(QWidget):
    module='life'
    def layout_header(self,title,note):
        layout=QVBoxLayout(self);layout.setContentsMargins(28,24,28,24);layout.setSpacing(16)
        head=QLabel(title);head.setObjectName('title');layout.addWidget(head)
        caption=QLabel(note);caption.setObjectName('muted');caption.setWordWrap(True);layout.addWidget(caption)
        return layout
    def invoke(self,action):
        try:
            result=action();self.hub.changed.emit(self.module);return result
        except Exception as exc:QMessageBox.warning(self,'暂未完成',str(exc))
    def save_dialog(self,dialog,error,action):
        try:action();self.hub.changed.emit(self.module);dialog.accept()
        except Exception as exc:error.setText(str(exc))
