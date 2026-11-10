"""Human review and sharing for the controlled event ledger."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPlainTextEdit, QPushButton, QInputDialog, QMessageBox)
from .role_events import EventLedger, KINDS
from .roles import list_roles


class EventDialog(QDialog):
    def __init__(self, store, role, parent=None):
        super().__init__(parent)
        self.ledger, self.role = EventLedger(store), role
        self.setWindowTitle('协作记录 · 原文、推断与决定')
        self.resize(860, 620)
        layout = QVBoxLayout(self)
        note = QLabel('只显示本角色与明确共享的记录（最近 200 条）。AI 推断不会自动变成事实。'
                      '\n这里的待办不自动发送提醒；需要提醒时仍使用原 QQ 插件。')
        note.setWordWrap(True); layout.addWidget(note)
        body = QHBoxLayout(); self.items = QListWidget()
        self.items.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.items.setTextElideMode(Qt.TextElideMode.ElideRight); body.addWidget(self.items, 1)
        self.detail = QPlainTextEdit(); self.detail.setReadOnly(True); body.addWidget(self.detail, 2); layout.addLayout(body, 1)
        self.items.currentItemChanged.connect(self.describe)
        row = QHBoxLayout()
        for name, callback in [('记录一条', self.add), ('确认为决定', lambda:self.derive('decision')),
                               ('创建待办', lambda:self.derive('task')), ('标记完成', self.complete),
                               ('共享给角色', self.share), ('刷新', self.reload)]:
            b = QPushButton(name); b.clicked.connect(callback); row.addWidget(b)
        layout.addLayout(row)
        close = QPushButton('关闭'); close.clicked.connect(self.accept); layout.addWidget(close)
        self.reload()

    def selected(self):
        item = self.items.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def reload(self):
        old = self.selected(); self.items.clear()
        for event in self.ledger.list(self.role):
            status = '已完成' if event['state']=='completed' else KINDS[event['kind']]
            item = QListWidgetItem(status + ' · ' + event['body'].replace('\n',' ')[:35])
            item.setToolTip(event['body'])
            item.setData(Qt.ItemDataRole.UserRole,event['id']); self.items.addItem(item)
            if old == event['id']: self.items.setCurrentItem(item)
        if self.items.currentRow() < 0: self.items.setCurrentRow(0)
        if not self.items.count(): self.detail.setPlainText('暂无记录。可手工记录，或在角色能力设置中启用“受控协作记录”。')

    def describe(self, *args):
        if not self.selected(): return
        try:
            event = self.ledger.get(self.role,self.selected())
            names = dict((r[0],r[1]) for r in list_roles(self.ledger.root,include_archived=True))
            readers = '、'.join(names.get(r,r) for r in self.ledger.readers(event['id'])) or '未共享'
            state = {'recorded':'已保存原文','unconfirmed':'未确认','confirmed':'已确认','pending':'待完成','completed':'已完成'}[event['state']]
            self.detail.setPlainText(KINDS[event['kind']] + ' · ' + state
                + '\nID：' + event['id'] + '\n来源事件：' + str(event['parent'] or '用户原文')
                + '\n共享：' + readers + '\n\n' + event['body'])
        except Exception as exc: self.detail.setPlainText(str(exc))

    def approve(self, title, subject, detail):
        return QMessageBox.question(self,title,detail) == QMessageBox.StandardButton.Yes

    def perform(self, fn):
        try:
            result = fn(); self.reload()
            if result and result.get('status') == 'already_exists':
                QMessageBox.information(self,'未重复创建','此来源事件已有同类记录，请核对已有决定或待办。')
        except Exception as exc: QMessageBox.warning(self,'操作未完成',str(exc))

    def add(self):
        body, ok = QInputDialog.getMultiLineText(self,'保存原始记录','输入你的记录；默认仅当前角色可读。')
        if ok: self.perform(lambda:self.ledger.user_note(self.role,body))

    def derive(self, kind):
        eid = self.selected()
        if not eid: return
        body, ok = QInputDialog.getMultiLineText(self, KINDS[kind], '请输入确认后的具体内容：')
        if ok: self.perform(lambda:self.ledger.derive(self.role,eid,kind,body,self.approve))

    def complete(self):
        eid = self.selected()
        if eid: self.perform(lambda:self.ledger.complete(self.role,eid,self.approve))

    def share(self):
        eid = self.selected()
        if not eid: return
        dialog = QDialog(self); dialog.setWindowTitle('用户授权共享'); dialog.resize(440,430)
        layout = QVBoxLayout(dialog)
        note = QLabel('选中角色可以读取此记录及其来源链。不会开放私人聊天或长期记忆。'
                      '\n取消勾选只撤销本条；若此前共享了来源，可选中来源记录分别撤销。')
        note.setWordWrap(True); layout.addWidget(note)
        choices = QListWidget(); layout.addWidget(choices)
        readers = self.ledger.readers(eid)
        for rid,name,*_ in list_roles(self.ledger.root,include_archived=True):
            item = QListWidgetItem(name); item.setData(Qt.ItemDataRole.UserRole,rid)
            item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if rid in readers else Qt.CheckState.Unchecked)
            choices.addItem(item)
        save = QPushButton('确认共享范围'); save.clicked.connect(dialog.accept); layout.addWidget(save)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            roles = [choices.item(i).data(Qt.ItemDataRole.UserRole) for i in range(choices.count())
                     if choices.item(i).checkState()==Qt.CheckState.Checked]
            self.perform(lambda:self.ledger.share_by_user(eid,roles))
