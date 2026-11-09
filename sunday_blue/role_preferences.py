"""Role lifecycle UI; persistence and dependency policy live in role_lifecycle."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QListWidget,
    QListWidgetItem, QLabel, QPushButton, QInputDialog, QMessageBox, QFileDialog)


class RoleManager(QDialog):
    changed = Signal()

    def __init__(self, service, selected=None, parent=None):
        super().__init__(parent)
        self.service = service
        self.setWindowTitle('角色管理')
        self.resize(760, 560)
        layout = QVBoxLayout(self)
        title = QLabel('角色与独立数据'); title.setObjectName('title'); layout.addWidget(title)
        note = QLabel('名称可自由修改，内部 ID 始终不变。新角色不继承其他角色的权限或插件配置。')
        note.setWordWrap(True); layout.addWidget(note)
        self.roles = QListWidget(); layout.addWidget(self.roles, 1)
        self.detail = QLabel(); self.detail.setWordWrap(True); self.detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.detail)
        row = QHBoxLayout()
        for text, callback in [('新建', self.create), ('重命名', self.rename), ('归档', self.archive),
                               ('恢复', self.restore), ('导出', self.export), ('永久删除', self.delete)]:
            b = QPushButton(text); b.clicked.connect(callback); row.addWidget(b)
        layout.addLayout(row)
        row = QHBoxLayout()
        retry = QPushButton('继续未完成的删除'); retry.clicked.connect(self.resume); row.addWidget(retry)
        row.addStretch(); close = QPushButton('关闭'); close.clicked.connect(self.accept); row.addWidget(close)
        layout.addLayout(row)
        self.roles.currentItemChanged.connect(self.describe)
        self.reload(selected)

    def selected(self):
        item = self.roles.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def reload(self, selected=None):
        selected = selected or self.selected()
        self.roles.clear()
        labels = {'active': '启用', 'archived': '已归档', 'deleting': '删除待恢复'}
        for record in self.service.registry.records(tuple(labels)):
            item = QListWidgetItem(f"{record['name']} · {labels[record['state']]}")
            item.setData(Qt.ItemDataRole.UserRole, record['id']); self.roles.addItem(item)
            if record['id'] == selected: self.roles.setCurrentItem(item)
        if self.roles.currentRow() < 0: self.roles.setCurrentRow(0)

    def describe(self, *args):
        if not self.selected(): return
        try:
            info = self.service.inspect(self.selected())
            self.detail.setText(f"ID：{info['role']['id']}\n会话：{info['sessions']} 个\n"
                                + '\n'.join(info['blockers']) + '\n' + info['retained'])
        except Exception as exc:
            self.detail.setText(str(exc))

    def perform(self, fn, selected=None):
        try:
            result = fn()
            self.changed.emit()
            self.reload(selected or (result if isinstance(result, str) else None))
            return result
        except Exception as exc:
            self.changed.emit()  # A failed delete may have safely tombstoned the role.
            self.reload()
            QMessageBox.warning(self, '操作未完成', str(exc))

    def create(self):
        name, ok = QInputDialog.getText(self, '新建角色', '显示名称（人格随后可在设置中编辑）')
        if ok: self.perform(lambda: self.service.create(name))

    def rename(self):
        rid = self.selected()
        if not rid: return
        name, ok = QInputDialog.getText(self, '重命名角色', '显示名称', text=self.service.registry.get(rid)['name'])
        if ok: self.perform(lambda: self.service.rename(rid, name), rid)

    def archive(self):
        rid = self.selected()
        if rid and QMessageBox.question(self, '归档角色', '角色将从聊天与设置列表隐藏，全部记录保留，可随时恢复。继续？') == QMessageBox.StandardButton.Yes:
            self.perform(lambda: self.service.archive(rid))

    def restore(self):
        rid = self.selected()
        if rid: self.perform(lambda: self.service.restore(rid), rid)

    def export(self):
        rid = self.selected()
        if not rid: return
        path, _ = QFileDialog.getSaveFileName(self, '导出角色（可能包含个人资料，请妥善保管）', rid + '.zip', 'ZIP (*.zip)')
        if path: self.perform(lambda: self.service.export(rid, path), rid)

    def delete(self):
        rid = self.selected()
        if not rid: return
        info = self.service.inspect(rid)
        if info['role']['state'] != 'archived' or info['blockers']:
            QMessageBox.information(self, '暂不能删除', '需先归档并解除依赖。\n' + '\n'.join(info['blockers']))
            return
        scope = ('将移除 %s 个会话及其消息、审计、角色设置、MCP 关联和以下目录：\n' % info['sessions']
                 + '\n'.join(info['paths']) + '\n\n' + info['retained']
                 + '\n删除前自动生成离线 ZIP 备份；不再参与聊天或记忆检索。\n请输入角色名称确认：')
        name, ok = QInputDialog.getText(self, '永久删除角色 · 请核对范围', scope)
        if ok and name == info['role']['name']:
            result = self.perform(lambda: self.service.delete(rid, confirmed=True))
            if result: QMessageBox.information(self, '角色已删除', '恢复备份保存在：\n' + str(result))

    def resume(self):
        errors = self.service.resume_pending()
        self.changed.emit(); self.reload()
        if errors: QMessageBox.warning(self, '仍有待处理项', '\n'.join(errors))
