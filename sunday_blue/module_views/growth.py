"""Evidence-led learning and immutable challenge UIs, reusing existing domain boundaries."""
from datetime import datetime
from PySide6.QtCore import Qt,QDateTime
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QSplitter,QHeaderView,QTreeWidget,QTreeWidgetItem,QListWidget,QListWidgetItem,QLabel,QLineEdit,QPlainTextEdit,QComboBox,QSpinBox,QDoubleSpinBox,QDateTimeEdit,QTabWidget,QCheckBox,QMessageBox,QInputDialog)
from .module_forms import ModulePage,button,form_dialog,spin
from .life_widgets import label
from ..modules.contracts import METRICS
from ..modules.life_state import ZONE

class LearningPage(ModulePage):
 module='learning'
 def __init__(self,hub,parent=None):
  super().__init__(parent);self.hub=hub;box=self.layout_header('学习档案','时间是投入，掌握需要做题与复习证据。知识点归属于课程与章节，不归属于人格。')
  self.summary=label();box.addWidget(self.summary);row=QHBoxLayout()
  for text,kind in [('新建课程','subject'),('添加章节','chapter'),('添加知识点','unit')]:button(text,lambda checked=False,k=kind:self.add(k),row)
  button('掌握标准',self.options,row);self.due_only=QCheckBox('只看待复习');self.due_only.toggled.connect(self.refresh);row.addWidget(self.due_only);row.addStretch();box.addLayout(row)
  split=QSplitter();self.tree=QTreeWidget();self.tree.setHeaderLabels(['课程 / 章节 / 知识点','掌握 / 进度','学习分钟']);self.tree.header().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch);self.tree.header().setSectionResizeMode(1,QHeaderView.ResizeMode.ResizeToContents);self.tree.header().setSectionResizeMode(2,QHeaderView.ResizeMode.ResizeToContents);split.addWidget(self.tree)
  pane=QWidget();p=QVBoxLayout(pane);self.detail=label('选择知识点，查看证据与复习安排。');p.addWidget(self.detail);self.errors=QListWidget();self.errors.setWordWrap(True);p.addWidget(self.errors);button('重做所选错题',self.redo,p);split.addWidget(pane);split.setSizes([600,320]);box.addWidget(split,1)
  row=QHBoxLayout();button('学习此知识点',self.start,row,True);button('更新自评',self.assess,row);button('记录练习',self.practice,row);button('复习检验',self.review,row);button('章节读完 / 撤销',self.chapter,row);box.addLayout(row)
  self.tree.currentItemChanged.connect(lambda *_:self.inspect());hub.changed.connect(lambda m:self.refresh() if m in ('learning','focus','modules') else None);self.refresh()
 def selected(self,unit=False):
  item=self.tree.currentItem();r=item.data(0,Qt.ItemDataRole.UserRole) if item else None
  if not r or unit and r['kind']!='unit':raise ValueError('请先选择一个知识点' if unit else '请先选择项目')
  return r
 def add(self,kind):
  try:parent=None if kind=='subject' else self.selected()['id']
  except ValueError as exc:QMessageBox.information(self,'选择位置',str(exc));return
  title,ok=QInputDialog.getText(self,'新增'+{'subject':'课程','chapter':'章节','unit':'知识点'}[kind],'名称')
  if ok:self.invoke(lambda:self.hub.learning.add(kind,title,parent))
 def refresh(self):
  current=self.tree.currentItem();selected=current.data(0,Qt.ItemDataRole.UserRole)['id'] if current else None;self.tree.clear();rows=self.hub.learning.rows();items={};e={r['id']:self.hub.learning.evidence(r['id']) for r in rows if r['kind']=='unit'}
  for r in rows:
   result=e.get(r['id']);status=('已掌握' if result['mastered'] else f"证据分 {result['score']:.0f}") if result else ('已读完' if r['done'] else '进行中') if r['kind']=='chapter' else ''
   descendants=[n for n in rows if n['parent']==r['id']]
   if r['kind']=='subject':descendants=[n for n in rows if n['parent'] in {v['id'] for v in descendants}]
   if result is None and descendants:status+=f" · 掌握 {sum(e.get(v['id'],{}).get('mastered',False) for v in descendants)}/{len(descendants)}"
   item=QTreeWidgetItem([r['title'],status,f"{result['minutes']:.1f}" if result else '']);item.setData(0,Qt.ItemDataRole.UserRole,r);items[r['id']]=item
  for r in rows:
   item=items[r['id']];parent=items.get(r['parent']);parent.addChild(item) if parent else self.tree.addTopLevelItem(item)
   if r['id']==selected:self.tree.setCurrentItem(item)
   if r['kind']=='unit' and self.due_only.isChecked():item.setHidden(e[r['id']]['due']>datetime.now(ZONE).date().isoformat())
  self.tree.expandAll();s=self.hub.learning.summary();accuracy=100*s['correct']/s['questions'] if s['questions'] else 0
  self.summary.setText(f"累计有效学习 {s['minutes']:.1f} 分钟 · 掌握 {s['mastered']}/{s['units']} 个知识点 · 各点近50批练习正确率 {accuracy:.0f}%")
  self.inspect()
 def inspect(self):
  self.errors.clear()
  try:r=self.selected(True)
  except ValueError:self.detail.setText('选择知识点以查看证据；章节读完不等于知识点掌握。');return
  e=self.hub.learning.evidence(r['id']);self.detail.setText(f"{r['title']}\n自评 {r['self_score']:g} / 证据分 {e['score']:.0f}\n最近50批练习：{e['correct']}/{e['total']} 题正确\n未解决错题 {e['errors']} 条 · 复习 {e['reviews']} 次\n下次复习 {e['due']}\n学习 {e['minutes']:.1f} 分钟（仅绑定本点的已结算专注）")
  for wrong in self.hub.learning.errors():
   if wrong['unit']==r['id']:
    item=QListWidgetItem(('✓ 已解决' if wrong['resolved'] else '待重做')+' · '+wrong['note']);item.setData(Qt.ItemDataRole.UserRole,wrong);self.errors.addItem(item)
 def start(self):
  def action():
   r=self.selected(True);slots=self.hub.duties.slots();role=next((s['role_id'] for s in slots if s['id']=='study' and s['role_id']),None)
   if not role:
    from ..roles import list_roles
    role=next((x[0] for x in list_roles(self.hub.root) if x[0]=='loluns'),list_roles(self.hub.root)[0][0])
   self.hub.start_focus('学习',r['title'],role,duration=self.hub.focus.options()['focus_minutes']*60)
   self.hub.learning.bind(self.hub.focus.status()['id'],r['id']);self.hub.db.set('focus_loop',self.hub.db.get('focus_loop',{})|{'learning_unit':r['id']});self.hub.navigate.emit('focus')
  self.invoke(action)
 def assess(self):
  try:r=self.selected(True)
  except ValueError as exc:QMessageBox.information(self,'选择知识点',str(exc));return
  value,ok=QInputDialog.getInt(self,'掌握自评','能否脱离答案解释、应用？自评不能替代练习与复习证据。',int(r['self_score']),0,100)
  if ok:self.invoke(lambda:self.hub.learning.assess(r['id'],value))
 def practice(self,error=None):
  if isinstance(error,bool):error=None
  try:r=self.selected(True)
  except ValueError as exc:QMessageBox.information(self,'选择知识点',str(exc));return
  dlg,form,err,buttons=form_dialog(self,'重做错题' if error else '记录练习');total=spin(1,10000);correct=spin(0,10000);note=QPlainTextEdit(error['note'] if error else '');note.setPlaceholderText('有错题时填写题目要点、错因与下次检查方法')
  form.addRow('总题数',total);form.addRow('正确数',correct);form.addRow('错题 / 复盘',note)
  buttons.accepted.connect(lambda:self.save_dialog(dlg,err,lambda:self.hub.learning.practice(r['id'],total.value(),correct.value(),note.toPlainText(),error_id=error['id'] if error else None)));dlg.exec()
 def redo(self):
  item=self.errors.currentItem()
  if item:self.practice(item.data(Qt.ItemDataRole.UserRole))
 def review(self):
  try:r=self.selected(True)
  except ValueError as exc:QMessageBox.information(self,'选择知识点',str(exc));return
  text,ok=QInputDialog.getItem(self,'复习检验','先合上资料复述或独立解题，再记录结果（每天一次）',['通过：可独立回忆并应用','未通过：需要再学'],0,False)
  if ok:self.invoke(lambda:self.hub.learning.review(r['id'],text.startswith('通过'),text))
 def chapter(self):
  def action():
   r=self.selected()
   if r['kind']!='chapter':raise ValueError('请选择章节')
   self.hub.learning.chapter_done(r['id'],not r['done'])
  self.invoke(action)
 def options(self):
  o=self.hub.learning.options();dlg,form,error,buttons=form_dialog(self,'掌握标准');threshold=spin(o['mastery_threshold'],100);minimum=spin(o['minimum_questions'],100);form.addRow('证据分阈值（60–100）',threshold);form.addRow('最低题量（5–100）',minimum);form.addRow(label('还需最近复习通过，且无待解决错题。调整标准不改写已有练习。'))
  buttons.accepted.connect(lambda:self.save_dialog(dlg,error,lambda:self.hub.learning.configure(threshold.value(),minimum.value())));dlg.exec()

class ContractsPage(ModulePage):
 module='contracts'
 def __init__(self,hub,parent=None):
  super().__init__(parent);self.hub=hub;box=self.layout_header('限时契约','契约积分是独立游戏资源，不兑换金币或现实金额。到期证据不足先核对，休息无需购买。');self.summary=label();box.addWidget(self.summary)
  row=QHBoxLayout();button('签订契约',self.sign,row,True);button('积分与上限设置',self.options,row);box.addLayout(row);self.items=QListWidget();self.items.setWordWrap(True);box.addWidget(self.items,1)
  row=QHBoxLayout();button('记录自主目标进展',self.log,row);button('核对到期结果',lambda:self.resolve(False),row);button('主动解约',lambda:self.resolve(True),row);box.addLayout(row)
  hub.changed.connect(lambda m:self.refresh() if m in ('contracts','learning','focus','modules') else None);self.refresh()
 def selected(self):
  i=self.items.currentItem()
  if not i:raise ValueError('请选择契约')
  return i.data(Qt.ItemDataRole.UserRole)
 def refresh(self):
  self.hub.contracts.tick();i=self.items.currentItem();rid=i.data(Qt.ItemDataRole.UserRole)['id'] if i else None;self.items.clear()
  for r in self.hub.contracts.rows():
   status={'active':'进行中','review':'到期待核对','success':'已达成','failed':'已核对未达成','cancelled':'已解约'}[r['status']]
   item=QListWidgetItem(f"{r['title']}　·　{status}\n{METRICS[r['metric']]}：{r['progress']:g} / {r['target']:g}　｜　截止 {datetime.fromisoformat(r['deadline']).astimezone(ZONE):%m-%d %H:%M}\n奖励 {r['reward']} 契约积分 / 最多扣 {r['penalty']} 积分")
   item.setData(Qt.ItemDataRole.UserRole,r);item.setToolTip(r['terms']);self.items.addItem(item)
   if r['id']==rid:self.items.setCurrentItem(item)
  self.summary.setText(f'契约积分 {self.hub.contracts.balance()}　·　签约时锁定规则，余额最低为0，绝不扣现实资源。')
 def sign(self):
  dlg,f,e,buttons=form_dialog(self,'签订新的限时契约');title=QLineEdit();metric=QComboBox()
  for k,v in METRICS.items():metric.addItem(v,k)
  target=spin(30,100000);due=QDateTimeEdit(QDateTime.currentDateTime().addDays(7));due.setCalendarPopup(True);due.setDisplayFormat('yyyy-MM-dd HH:mm');reward=QDoubleSpinBox();penalty=QDoubleSpinBox()
  for w in (reward,penalty):w.setRange(0,3);w.setSingleStep(.5);w.setValue(1)
  notes=QLineEdit();notes.setPlaceholderText('可选：给契约一个仪式感，不会执行现实惩罚')
  for name,w in [('契约标题',title),('目标指标',metric),('目标量',target),('截止时间（本机时间）',due),('奖励倍率',reward),('扣分倍率',penalty),('契约说明',notes)]:f.addRow(name,w)
  o=self.hub.contracts.options();f.addRow(label(f"基础 {o['base_reward']} 积分；单次最多扣 {o['single_cap']}，每日最多扣 {o['daily_cap']}。签约后不可修改，电脑和已配置QQ渠道自动提醒。"))
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
  super().__init__(parent);box=QVBoxLayout(self);box.setContentsMargins(0,8,0,0);self.tabs=QTabWidget();box.addWidget(self.tabs);self.learning=LearningPage(hub);self.contracts=ContractsPage(hub);self.tabs.addTab(self.learning,'学习与复习');self.tabs.addTab(self.contracts,'限时契约')

class SchedulePage(QWidget):
 def __init__(self,hub,parent=None):
  super().__init__(parent)
  from .planner import CalendarPage,RemindersPage,CheckinsPage
  box=QVBoxLayout(self);box.setContentsMargins(0,8,0,0);self.tabs=QTabWidget();box.addWidget(self.tabs);self.pages={}
  for key,title,cls in [('calendar','日历',CalendarPage),('reminders','提醒',RemindersPage),('checkins','打卡',CheckinsPage)]:
   page=cls(hub);self.pages[key]=page;self.tabs.addTab(page,title)
 def select(self,key):self.tabs.setCurrentWidget(self.pages[key])
