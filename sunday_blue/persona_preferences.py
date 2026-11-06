"""User-owned personality editor, separate from role tools and automatic memory."""
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
                              QListWidget, QPlainTextEdit, QPushButton, QMessageBox,
                              QDialogButtonBox, QSplitter, QWidget)
from PySide6.QtCore import Qt
from .storage import ROLES
from .personas import SECTIONS, read_persona, save_persona, previous_persona
from .change_review import ChangeReview


class PersonaDialog(QDialog):
    def __init__(self, root, role='rui', parent=None):
        super().__init__(parent)
        self.root, self.role = root, role
        self.setWindowTitle('人格设定')
        self.resize(1000, 740)
        layout = QVBoxLayout(self)
        heading = QLabel('让每个角色保持自己的样子')
        heading.setObjectName('title')
        layout.addWidget(heading)
        note = QLabel('这里由你编辑人格，模型不能自行改写。工具能力由插件管理。\n保存后下一次对话生效；已开始的回复沿用原人格。每次保存保留完整版本。')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.roles = QComboBox()
        for rid, name, *_ in ROLES:
            self.roles.addItem(name, rid)
        self.roles.setCurrentIndex(self.roles.findData(role))
        layout.addWidget(self.roles)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.sections = QListWidget()
        self.sections.setFixedWidth(160)
        for _, title, _ in SECTIONS:
            self.sections.addItem(title)
        split.addWidget(self.sections)
        content = QWidget()
        column = QVBoxLayout(content)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        column.addWidget(self.hint)
        self.editor = QPlainTextEdit()
        column.addWidget(self.editor)
        split.addWidget(content)
        layout.addWidget(split, 1)
        self.notice = QLabel('')
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        row = QHBoxLayout()
        restore = QPushButton('载入上一版（待审阅）')
        restore.clicked.connect(self.restore)
        row.addWidget(restore)
        row.addStretch()
        close = QPushButton('关闭')
        close.clicked.connect(self.reject)
        row.addWidget(close)
        save = QPushButton('审阅并保存人格')
        save.setObjectName('primary')
        save.clicked.connect(self.review_save)
        row.addWidget(save)
        layout.addLayout(row)
        self.baseline = read_persona(root, role)
        self.draft = self.baseline.copy()
        self.section = None
        self.sections.currentRowChanged.connect(self.select_section)
        self.roles.currentIndexChanged.connect(self.select_role)
        self.sections.setCurrentRow(0)

    def stash(self):
        if self.section is not None:
            self.draft[SECTIONS[self.section][0]] = self.editor.toPlainText()

    def select_section(self, index):
        self.stash()
        self.section = index
        filename, title, hint = SECTIONS[index]
        self.hint.setText(title + ' · ' + hint)
        self.editor.setPlainText(self.draft[filename])

    def can_discard(self):
        self.stash()
        return self.draft == self.baseline or QMessageBox.question(
            self, '尚未保存', '放弃当前未保存的人格修改？',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes

    def select_role(self):
        if not self.can_discard():
            self.roles.blockSignals(True)
            self.roles.setCurrentIndex(self.roles.findData(self.role))
            self.roles.blockSignals(False)
            return
        self.role = self.roles.currentData()
        self.baseline = read_persona(self.root, self.role)
        self.draft = self.baseline.copy()
        index = self.sections.currentRow()
        self.section = None
        self.select_section(index)
        self.notice.clear()

    def restore(self):
        try:
            self.draft = previous_persona(self.root, self.role)
            self.editor.setPlainText(self.draft[SECTIONS[self.section][0]])
            self.notice.setText('已载入上一版。点击“审阅并保存人格”才会恢复。')
        except Exception as exc:
            QMessageBox.information(self, '无法载入', str(exc))

    def review_save(self):
        self.stash()
        if self.draft == self.baseline:
            self.notice.setText('没有需要保存的修改。')
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(self.role + ' · 审阅人格修改')
        dialog.resize(1100, 740)
        layout = QVBoxLayout(dialog)
        render = lambda value: '\n\n'.join('【'+title+'】\n'+value[name] for name,title,_ in SECTIONS)
        layout.addWidget(ChangeReview(render(self.baseline), render(self.draft)))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('确认保存')
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            save_persona(self.root, self.role, self.baseline, self.draft)
            self.baseline = self.draft.copy()
            self.notice.setText('人格已保存，下一次对话生效；旧版本可恢复。')
        except Exception as exc:
            QMessageBox.warning(self, '保存失败', str(exc))

    def reject(self):
        if self.can_discard():
            super().reject()

    def closeEvent(self, event):
        if self.can_discard():
            event.accept()
        else:
            event.ignore()
