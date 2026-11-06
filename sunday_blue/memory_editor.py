"""User editor for the explicitly confirmed, role-local memory file."""
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                              QPlainTextEdit, QPushButton, QMessageBox, QDialogButtonBox)
from .files import FileTools, no_links
from .change_review import ChangeReview


class MemoryEditor(QDialog):
    def __init__(self, root, role, store, parent=None):
        super().__init__(parent)
        self.root, self.role, self.store = root, role, store
        self.path = root / 'data/memory' / role / 'long_term.md'
        no_links(self.path)
        self.original = self.path.read_text(encoding='utf-8-sig')
        self.setWindowTitle(role + ' · 已确认记忆')
        self.resize(850, 650)
        layout = QVBoxLayout(self)
        note = QLabel('由你确认的事实、偏好与长期约定。可直接编辑；自动整理的历史记忆请在 LivingMemory 图谱中管理。')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.editor = QPlainTextEdit(self.original)
        layout.addWidget(self.editor)
        path = QLabel(str(self.path))
        path.setWordWrap(True)
        path.setObjectName('muted')
        layout.addWidget(path)
        row = QHBoxLayout()
        row.addStretch()
        close = QPushButton('关闭')
        close.clicked.connect(self.reject)
        row.addWidget(close)
        save = QPushButton('审阅并保存')
        save.setObjectName('primary')
        save.clicked.connect(self.save)
        row.addWidget(save)
        layout.addLayout(row)

    def review(self, title, path, detail):
        dialog = QDialog(self)
        dialog.setWindowTitle('确认记忆修改')
        dialog.resize(1100, 700)
        layout = QVBoxLayout(dialog)
        layout.addWidget(ChangeReview(detail['before'], detail['after']))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('确认保存')
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        return dialog.exec() == QDialog.DialogCode.Accepted

    def save(self):
        try:
            no_links(self.path)
            if self.path.read_text(encoding='utf-8-sig') != self.original:
                raise RuntimeError('记忆已被其他窗口修改。请关闭并重新打开，避免覆盖新内容。')
            tools = FileTools(self.root, self.role, [], self.review,
                              lambda action, detail: self.store.audit(self.role, None, 'manual_memory_' + action, detail))
            result = tools.write('', content=self.editor.toPlainText(), memory=True)
            if result['status'] in ('written', 'unchanged'):
                self.original = self.editor.toPlainText()
                self.accept()
        except Exception as exc:
            QMessageBox.warning(self, '未保存', str(exc))

    def reject(self):
        if self.editor.toPlainText() != self.original and QMessageBox.question(
                self, '尚未保存', '放弃未保存的记忆修改？',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        super().reject()

    def closeEvent(self, event):
        self.reject()
        event.setAccepted(self.result() == QDialog.DialogCode.Rejected and not self.isVisible())
