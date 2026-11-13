"""Optional state controls and non-blocking high-fatigue guidance."""
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QComboBox,QDoubleSpinBox,QLineEdit,QPushButton,QScrollArea,QWidget
from .module_forms import form_dialog
from .life_widgets import label
from ..modules.attention import MODES
from ..numeric_inputs import NumberSpin as QSpinBox, DecimalSpin as QDoubleSpinBox

def settings(page):
 hub=page.hub;o=hub.attention.options();dlg,f,error,b=form_dialog(page,'状态估算参数');mode=QComboBox()
 for k,v in MODES.items():mode.addItem(v,k)
 mode.setCurrentIndex(mode.findData(o['mode']));intensity=QComboBox()
 for k,v in [('low','低'),('medium','中'),('high','高')]:intensity.addItem(v,k)
 intensity.setCurrentIndex(intensity.findData(o['intensity']));f.addRow('当前模式',mode);f.addRow('用眼强度',intensity);fields={}
 for key,title,lo,hi in [('eye_rate','用眼每分钟累积',.05,2),('focus_eye_bonus','工作 / 学习每分钟额外视疲劳',0,2),('focus_rate','每分钟专注消耗',.01,1),('rest_eye','休息每分钟恢复视疲劳',.05,3),('rest_focus','休息每分钟恢复专注',.01,2),('sleep_eye','睡眠每小时恢复视疲劳',0,20),('sleep_focus','睡眠每小时恢复专注',0,20),('light_threshold','轻提醒阈值 %',10,90),('high_threshold','QQ引导阈值 %',20,99),('cooldown_minutes','重复提醒冷却分钟',15,240)]:
  w=QDoubleSpinBox();w.setRange(lo,hi);w.setDecimals(3 if key=='rest_focus' else 2);w.setValue(o[key]);fields[key]=w;f.addRow(title,w)
 private_limit=QSpinBox();private_limit.setRange(1,99);private_limit.setValue(hub.db.get('private_control_reference',5));f.addRow('私人记录每周控制参考（非医学标准）',private_limit)
 start=QLineEdit(o['night_start']);end=QLineEdit(o['night_end']);f.addRow('夜间开始 HH:mm',start);f.addRow('夜间结束 HH:mm',end);f.addRow(label('仅在软件运行时观察本机输入活跃度，不读屏幕/应用内容。视频、纸面学习请选择明确模式。夜间仍在用眼则继续累积；暂停估算不会自动恢复。'))
 def save():
  def commit():
   hub.attention.configure({k:w.value() for k,w in fields.items()}|{'mode':mode.currentData(),'intensity':intensity.currentData(),'night_start':start.text(),'night_end':end.text()})
   hub.db.set('private_control_reference',private_limit.value())
  page.save_dialog(dlg,error,commit)
 b.accepted.connect(save)
 dlg.layout().removeItem(f);f.setParent(None);content=QWidget();content.setLayout(f);scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(content);dlg.layout().insertWidget(0,scroll,1);dlg.resize(600,min(690,dlg.screen().availableGeometry().height()-40));dlg.exec()

def rest_guide(window):
 if getattr(window,'rest_guide_dialog',None) and window.rest_guide_dialog.isVisible():return
 dlg=QDialog(window);window.rest_guide_dialog=dlg;dlg.setWindowTitle('给眼睛留一点恢复时间');dlg.resize(460,210);box=QVBoxLayout(dlg)
 box.addWidget(label('视疲劳估计已达到高提醒阈值','title'));box.addWidget(label('可以先离屏、远眺或闭目放松。这里只是行为估算，不会强制停止你的工作，也不消耗金币。'))
 row=QHBoxLayout();rest=QPushButton('开始离屏休息');later=QPushButton('稍后再说');row.addWidget(rest);row.addWidget(later);box.addLayout(row)
 def begin():window.module_hub.attention.configure({'mode':'rest'});window.module_hub.changed.emit('attention');window.module_hub.navigate.emit('life');dlg.close()
 rest.clicked.connect(begin);later.clicked.connect(dlg.close);dlg.show()
