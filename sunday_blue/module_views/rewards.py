import uuid
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QListWidget,QListWidgetItem,QPushButton,
    QDialog,QFormLayout,QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox,QMessageBox,QInputDialog)
from ..roles import list_roles


class RewardsPage(QWidget):
    def __init__(self,hub,parent=None):
        super().__init__(parent);self.hub=hub
        layout=QVBoxLayout(self);layout.setContentsMargins(32,24,32,24)
        title=QLabel('努力可以兑换，休息不需要许可。');title.setObjectName('title');layout.addWidget(title)
        self.balance=QLabel();layout.addWidget(self.balance)
        note=QLabel('金币是虚拟激励，与真实预算分开。预算奖励只有在你确认实际消费后，才记入预算。');note.setWordWrap(True);layout.addWidget(note)
        self.items=QListWidget();layout.addWidget(self.items,1)
        row=QHBoxLayout()
        for label,callback in [('添加奖励',self.add),('兑换所选',self.redeem),('调整现实预算',self.budget)]:
            button=QPushButton(label);button.clicked.connect(callback);row.addWidget(button)
        layout.addLayout(row);layout.addWidget(QLabel('最近兑换'));self.history=QListWidget();layout.addWidget(self.history,1)
        confirm=QPushButton('确认所选奖励已实际消费');confirm.clicked.connect(self.confirm);layout.addWidget(confirm)
        hub.changed.connect(lambda *_:self.refresh());self.refresh()
    def refresh(self):
        values=self.hub.rewards.balances();self.balance.setText(f"{values['coins']} 金币  ·  现实预算 ¥{values['budget_cents']/100:.2f}")
        previous=self.items.currentRow();self.items.clear()
        for r in self.hub.rewards.list():
            suffix=f" · ¥{r['cents']/100:.2f}（实际消费需确认）" if r['kind']=='budget' else ' · 角色礼物' if r['kind']=='gift' else f" · {r['minutes']} 分钟"
            item=QListWidgetItem(f"{r['title']} · {r['cost']} 金币"+suffix);item.setData(Qt.ItemDataRole.UserRole,r);self.items.addItem(item)
        self.items.setCurrentRow(max(0,previous));self.history.clear()
        for r in self.hub.rewards.history():
            status='待确认实际消费' if r['status']=='pending' else '已确认消费' if r['status']=='confirmed' else '已兑换'
            item=QListWidgetItem(f"{r['title']} · {status} · {r['cost']} 金币");item.setData(Qt.ItemDataRole.UserRole,r);self.history.addItem(item)
    def invoke(self,fn):
        try:result=fn();self.hub.relations.project();self.refresh();self.hub.changed.emit('rewards');return result
        except Exception as exc:QMessageBox.warning(self,'未完成',str(exc))
    def add(self):
        dialog=QDialog(self);dialog.setWindowTitle('添加现实奖励或心意');form=QFormLayout(dialog)
        title=QLineEdit();cost=QSpinBox();cost.setRange(1,100000);cost.setValue(20)
        kind=QComboBox()
        for text,key in [('娱乐 / 兴趣时间','leisure'),('现实预算奖励','budget'),('送给角色的心意','gift')]:kind.addItem(text,key)
        minutes=QSpinBox();minutes.setRange(0,10000);minutes.setValue(20)
        money=QDoubleSpinBox();money.setRange(0,100000);money.setPrefix('¥ ')
        roles=QComboBox()
        for rid,name,*_ in list_roles(self.hub.root):roles.addItem(name,rid)
        for label,widget in [('名称',title),('金币价格',cost),('类别',kind),('分钟（时间奖励）',minutes),('金额（预算奖励）',money),('角色（心意）',roles)]:form.addRow(label,widget)
        save=QPushButton('保存奖励');save.clicked.connect(dialog.accept);form.addRow(save)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            self.invoke(lambda:self.hub.rewards.add(title.text(),cost.value(),kind.currentData(),minutes.value(),round(money.value()*100),roles.currentData() if kind.currentData()=='gift' else None))
    def redeem(self):
        item=self.items.currentItem()
        if not item:return
        r=item.data(Qt.ItemDataRole.UserRole)
        if QMessageBox.question(self,'确认兑换',f"花费 {r['cost']} 金币兑换「{r['title']}」？\n金币不是现实金钱，休息不受这个商店限制。")==QMessageBox.StandardButton.Yes:
            self.invoke(lambda:self.hub.rewards.redeem(r['id'],uuid.uuid4().hex))
    def budget(self):
        amount,ok=QInputDialog.getDouble(self,'调整现实预算','增减金额（元，负数表示减少）：',0,-100000,100000,2)
        if not ok or amount==0:return
        note,ok=QInputDialog.getText(self,'预算来源','调整原因：')
        if ok and QMessageBox.question(self,'确认实际预算变动',f'预算调整 ¥{amount:.2f}，原因：{note}。确认？')==QMessageBox.StandardButton.Yes:
            self.invoke(lambda:self.hub.rewards.adjust_budget(round(amount*100),note,uuid.uuid4().hex))
    def confirm(self):
        item=self.history.currentItem()
        if not item:return
        r=item.data(Qt.ItemDataRole.UserRole)
        if r['kind']!='budget' or r['status']!='pending':return
        if QMessageBox.question(self,'确认真实消费',f"确实已为「{r['title']}」消费 ¥{r['cents']/100:.2f}？确认后记入现实预算。")==QMessageBox.StandardButton.Yes:
            self.invoke(lambda:self.hub.rewards.confirm_budget(r['id']))
