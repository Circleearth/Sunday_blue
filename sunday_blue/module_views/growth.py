"""Evidence-led learning and immutable challenge UIs, reusing existing domain boundaries."""
from datetime import datetime
from PySide6.QtCore import Qt,QDateTime
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QSplitter,QHeaderView,QTreeWidget,QTreeWidgetItem,QListWidget,QListWidgetItem,QLabel,QLineEdit,QPlainTextEdit,QComboBox,QSpinBox,QDoubleSpinBox,QDateTimeEdit,QTabWidget,QCheckBox,QMessageBox,QInputDialog)
from .module_forms import ModulePage,button,form_dialog,spin
from .life_widgets import label
from ..modules.contracts import METRICS
from ..modules.life_state import ZONE
from ..numeric_inputs import NumberSpin as QSpinBox, DecimalSpin as QDoubleSpinBox

from .learning_notebook import LearningPage

class ContractsPage(ModulePage):
 module='contracts'
 def __init__(self,hub,parent=None):
  super().__init__(parent);self.hub=hub;box=self.layout_header('限时契约','契约积分是独立游戏资源，不兑换金币或现实金额。到期证据不足先核对，休息无需购买。');self.summary=label();box.addWidget(self.summary)
  row=QHBoxLayout();button('签订契约',self.sign,row,True);button('积分与上限设置',self.options,row);box.addLayout(row);self.items=QListWidget();self.items.setWordWrap(True);box.addWidget(self.items,1)
  row=QHBoxLayout();button('记录自主目标进展',self.log,row);button('核对到期结果',lambda:self.resolve(False),row);button('主动解约',lambda:self.resolve(True),row);box.addLayout(row)
  hub.changed.connect(lambda m:self.refresh() if m in ('contracts','learning','focus','modules','life') else None);self.refresh()
 def selected(self):
  i=self.items.currentItem()
  if not i:raise ValueError('请选择契约')
  return i.data(Qt.ItemDataRole.UserRole)
 def refresh(self):
  self.hub.contracts.tick();i=self.items.currentItem();rid=i.data(Qt.ItemDataRole.UserRole)['id'] if i else None;self.items.clear()
  for r in self.hub.contracts.rows():
   status={'active':'进行中','review':'到期待核对','success':'已达成','failed':'已核对未达成','cancelled':'已解约'}[r['status']]
   item=QListWidgetItem(f"{r['title']}　·　{status}\n{METRICS[r['metric']]}：{r['progress']:g} / {r['target']:g}　｜　截止 {datetime.fromisoformat(r['deadline']).astimezone(ZONE):%m-%d %H:%M}\n奖励 {r['reward']} 契约积分 / 最多扣 {r['penalty']} 积分")
   if r['exercise_days']:
    days=r['exercise_days'];item.setText(item.text()+f"\n运动积分账户 · 达标 {sum(d['minutes']>=r['target'] for d in days)}/{len(days)} 天，每天需 {r['target']:g} 分钟");item.setToolTip('\n'.join(f"{d['day']}：{d['minutes']:g} 分钟" for d in days))
   else:item.setToolTip(r['terms'])
   item.setData(Qt.ItemDataRole.UserRole,r);self.items.addItem(item)
   if r['id']==rid:self.items.setCurrentItem(item)
  self.summary.setText(f'学习契约积分 {self.hub.contracts.balance()} · 运动契约积分 {self.hub.contracts.balance("exercise")}　·　签约时锁定规则，余额最低为0，绝不扣现实资源。')
 def sign(self):
  dlg,f,e,buttons=form_dialog(self,'签订新的限时契约');title=QLineEdit();metric=QComboBox()
  for k,v in METRICS.items():metric.addItem(v,k)
  target=spin(30,100000);due=QDateTimeEdit(QDateTime.currentDateTime().addDays(7));due.setCalendarPopup(True);due.setDisplayFormat('yyyy-MM-dd HH:mm');reward=QDoubleSpinBox();penalty=QDoubleSpinBox()
  for w in (reward,penalty):w.setRange(0,3);w.setSingleStep(.5);w.setValue(1)
  notes=QLineEdit();notes.setPlaceholderText('可选：给契约一个仪式感，不会执行现实惩罚')
  for name,w in [('契约标题',title),('目标指标',metric),('目标量',target),('截止时间（本机时间）',due),('奖励倍率',reward),('扣分倍率',penalty),('契约说明',notes)]:f.addRow(name,w)
  f.addRow(label('运动契约：目标量为每天足额分钟；签约日至截止日逐日检查，超额不抵其他日期，未报先核对。'));o=self.hub.contracts.options();f.addRow(label(f"基础 {o['base_reward']} 积分；单次最多扣 {o['single_cap']}，每日最多扣 {o['daily_cap']}。签约后不可修改，电脑和已配置QQ渠道自动提醒。"))
  def save():
   maximum=min(o['single_cap'],round(o['base_reward']*penalty.value()));gain=min(90,round(o['base_reward']*reward.value()))
   if QMessageBox.question(dlg,'确认契约条款',f'签订「{title.text()}」？\n奖励 {gain} 契约积分，失败/解约最多扣 {maximum}；不涉及金币、金钱或身体惩罚。\n截止后仅以期限内证据核对。')!=QMessageBox.StandardButton.Yes:return
   self.save_dialog(dlg,e,lambda:self.hub.contracts.sign(title.text(),metric.currentData(),target.value(),due.dateTime().toPython().astimezone().isoformat(),reward.value(),penalty.value(),notes.text()))
  buttons.accepted.connect(save);dlg.exec()
 def resolve(self,cancel):
  try:r=self.selected()
  except ValueError as exc:QMessageBox.information(self,'选择契约',str(exc));return
  if QMessageBox.question(self,'核对契约',('主动解约' if cancel else '我已核对期限内的学习 / 目标记录，按现有证据结算')+f"「{r['title']}」？未达标最多扣 {r['penalty']} 契约积分。") == QMessageBox.StandardButton.Yes:self.invoke(lambda:self.hub.contracts.resolve(r['id'],cancel))
 def log(self):
  try:r=self.selected()
  except ValueError as exc:QMessageBox.information(self,'选择契约',str(exc));return
  dlg,f,e,b=form_dialog(self,'确认实际进展');amount=spin(1,100000);note=QLineEdit();f.addRow('本次完成量',amount);f.addRow('实际完成的事实',note);b.accepted.connect(lambda:self.save_dialog(dlg,e,lambda:self.hub.contracts.log(r['id'],amount.value(),note.text())));dlg.exec()
 def options(self):
  o=self.hub.contracts.options();dlg,f,e,b=form_dialog(self,'未来契约的规则（已签契约不变）');single=spin(o['single_cap'],50);daily=spin(o['daily_cap'],100);base=spin(o['base_reward'],30)
  for name,w in [('单次扣分上限',single),('每日扣分上限',daily),('基础积分',base)]:f.addRow(name,w)
  b.accepted.connect(lambda:self.save_dialog(dlg,e,lambda:self.hub.contracts.configure(single.value(),daily.value(),base.value())));dlg.exec()

class GrowthPage(QWidget):
 def __init__(self,hub,parent=None):
  super().__init__(parent);box=QVBoxLayout(self);box.setContentsMargins(0,8,0,0);self.tabs=QTabWidget();box.addWidget(self.tabs);self.learning=LearningPage(hub);self.contracts=ContractsPage(hub);self.tabs.addTab(self.learning,'学习笔记');self.tabs.addTab(self.contracts,'限时契约')

class SchedulePage(QWidget):
 def __init__(self,hub,parent=None):
  super().__init__(parent)
  from .planner import CalendarPage,RemindersPage,CheckinsPage
  box=QVBoxLayout(self);box.setContentsMargins(0,8,0,0);self.tabs=QTabWidget();box.addWidget(self.tabs);self.pages={}
  for key,title,cls in [('calendar','日历',CalendarPage),('reminders','提醒',RemindersPage),('checkins','打卡',CheckinsPage)]:
   page=cls(hub);self.pages[key]=page;self.tabs.addTab(page,title)
 def select(self,key):self.tabs.setCurrentWidget(self.pages[key])
