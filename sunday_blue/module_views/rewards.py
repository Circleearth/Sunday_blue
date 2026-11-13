import uuid
from PySide6.QtCore import Qt,QSize
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QListWidget,QListWidgetItem,QPushButton,
    QFrame,QDialog,QFormLayout,QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox,QMessageBox,QInputDialog)
from PySide6.QtGui import QPixmap
from ..roles import list_roles
from ..image_layouts import EditableImage
from ..numeric_inputs import NumberSpin as QSpinBox, DecimalSpin as QDoubleSpinBox


class RewardsPage(QWidget):
    def __init__(self,hub,parent=None):
        super().__init__(parent);self.hub=hub
        layout=QVBoxLayout(self);layout.setContentsMargins(32,24,32,24)
        title=QLabel('努力可以兑换，休息不需要许可。');title.setObjectName('title');layout.addWidget(title)
        self.balance=QLabel();layout.addWidget(self.balance)
        note=QLabel('金币是虚拟激励，与真实预算分开。预算奖励只有在你确认实际消费后，才记入预算。');note.setWordWrap(True);layout.addWidget(note)
        banner=EditableImage(hub.root,'shop_background',hub.root/'assets/shop/background.png',ratio=1600/300);banner.setFixedHeight(100);layout.addWidget(banner)
        body=QHBoxLayout();layout.addLayout(body,3)
        self.items=QListWidget();self.items.setViewMode(QListWidget.ViewMode.IconMode);self.items.setResizeMode(QListWidget.ResizeMode.Adjust);self.items.setMovement(QListWidget.Movement.Static);self.items.setGridSize(QSize(270,245));self.items.setSpacing(12);body.addWidget(self.items,1)
        self.mascot=EditableImage(hub.root,'shop_mascot',hub.root/'assets/shop/mascot.png',ratio=.6);self.mascot.setMinimumWidth(180);body.addWidget(self.mascot)
        row=QHBoxLayout()
        for label,callback in [('兑换所选',self.redeem),('商店设置',self.settings)]:
            button=QPushButton(label);button.clicked.connect(callback);row.addWidget(button)
        layout.addLayout(row);layout.addWidget(QLabel('最近兑换'));self.history=QListWidget();layout.addWidget(self.history,1)
        confirm=QPushButton('确认所选奖励已实际消费');confirm.clicked.connect(self.confirm);layout.addWidget(confirm)
        hub.changed.connect(lambda *_:self.refresh());self.refresh()
    def refresh(self):
        values=self.hub.rewards.balances();self.balance.setText(f"{values['coins']} 金币  ·  现实预算 ¥{values['budget_cents']/100:.2f}")
        quota=self.hub.rewards.allowance.status()
        self.balance.setText(self.balance.text()+f"  ·  现实奖励可兑换 ¥{quota['available_cents']/100:.2f}（含结转）")
        names=dict((r[0],r[1]) for r in list_roles(self.hub.root))
        previous=self.items.currentRow();self.items.clear()
        for r in self.hub.rewards.list():
            if r['kind']=='gift':
                suffix=f" · 送给 {names.get(r['role_id'],'未知角色')}"
            elif r['kind']=='budget':
                suffix=f" · ¥{r['cents']/100:.2f}（实际消费需确认）"
            else:
                suffix=f" · {r['minutes']} 分钟"
            item=QListWidgetItem(f"{r['title']} · {r['cost']} 金币{suffix}");item.setData(Qt.ItemDataRole.UserRole,r);item.setSizeHint(QSize(250,225));self.items.addItem(item)
            card=QFrame();card.setObjectName('card');box=QVBoxLayout(card);box.setSpacing(10)
            art=EditableImage(self.hub.root,'shop_item:'+r['id'],self.hub.root/'assets/shop'/(r['id']+'.png'),ratio=2.5);art.setFixedHeight(92)
            box.addWidget(art);name=QLabel(r['title']);name.setWordWrap(True);name.setObjectName('cardTitle');box.addWidget(name)
            price=QLabel(str(r['cost'])+' 金币'+suffix);price.setWordWrap(True);box.addWidget(price)
            buy=QPushButton('兑换');buy.clicked.connect(lambda checked=False,i=item:self.buy_item(i));box.addWidget(buy);self.items.setItemWidget(item,card)
        self.items.setCurrentRow(max(0,previous));self.history.clear()
        for r in self.hub.rewards.history():
            status='待确认实际消费' if r['status']=='pending' else '已确认消费' if r['status']=='confirmed' else '已兑换'
            detail=''
            if r['kind']=='gift':detail=f" · 送给 {names.get(r['role_id'],'未知角色')}"
            elif r['kind']=='budget':detail=f" · ¥{r['cents']/100:.2f}"
            item=QListWidgetItem(f"{r['title']} · {status} · {r['cost']} 金币{detail}");item.setData(Qt.ItemDataRole.UserRole,r);self.history.addItem(item)
    def buy_item(self,item):
        self.items.setCurrentItem(item);self.redeem()
    def settings(self):
        dialog=QDialog(self);dialog.setWindowTitle('商店设置');layout=QVBoxLayout(dialog)
        for label,action in [('添加商品',self.add),('调整现实预算',self.budget),('月度额度与调整条件',self.allowance)]:
            button=QPushButton(label);button.clicked.connect(action);layout.addWidget(button)
        note=QLabel('背景：assets/shop/background.png（建议1600×300）\n立绘：assets/shop/mascot.png（建议600×1000）\n商品图：assets/shop/商品ID.png（建议600×240）\n缺少图片时显示白色占位。');note.setWordWrap(True);layout.addWidget(note);dialog.exec()
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
    def allowance(self):
        service=self.hub.rewards.allowance;state=service.status()
        text=(f"本月额度 ¥{state['cents']/100:.2f} · 含结转剩余 ¥{state['available_cents']/100:.2f}\n"
              f"上月 {state['last_hours']:.1f} 小时 / {state['last_days']} 天（共 {state['last_total']} 天）\n"
              f"修改需 ≥{state['hours']} 小时、活跃比例 >{state['ratio']:.0%}，每月一次；修改次月生效。")
        if not state['can_change']:QMessageBox.information(self,'月度额度',text);return
        amount,ok=QInputDialog.getDouble(self,'月度额度',text+'\n新的月额度（元）：',state['next_cents']/100,1,100000,2)
        if not ok:return
        hours,ok=QInputDialog.getDouble(self,'修改条件','以后修改所需的上月专注小时：',state['hours'],1,744,1)
        if ok and QMessageBox.question(self,'确认额度与条件',f'次月起 ¥{amount:.2f}；时长门槛 {hours} 小时。确认？')==QMessageBox.StandardButton.Yes:
            self.invoke(lambda:service.change(round(amount*100),hours,state['ratio']))

    def confirm(self):
        item=self.history.currentItem()
        if not item:return
        r=item.data(Qt.ItemDataRole.UserRole)
        if r['kind']!='budget' or r['status']!='pending':return
        if QMessageBox.question(self,'确认真实消费',f"确实已为「{r['title']}」消费 ¥{r['cents']/100:.2f}？确认后记入现实预算。")==QMessageBox.StandardButton.Yes:
            self.invoke(lambda:self.hub.rewards.confirm_budget(r['id']))
