from PySide6.QtCore import Qt, QSignalBlocker, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMenu, QMessageBox, QPlainTextEdit, QPushButton,
    QSplitter, QToolButton, QVBoxLayout, QWidget,
)

from ..modules.personal_notes import PersonalNotes


def timestamp(value):
    return (value or "")[:16].replace("T", " ")


class PersonalNotesPage(QWidget):
    def __init__(self, hub, parent=None):
        super().__init__(parent)
        self.hub = hub
        self.service = PersonalNotes(hub.db)
        self.key = None
        self.original = ("", "")
        self.revision = None
        self.trash = False
        root = QVBoxLayout(self)
        header = QHBoxLayout()
        root.addLayout(header)
        heading = QLabel("随手记")
        heading.setObjectName("title")
        header.addWidget(heading)
        header.addStretch()
        self.new_button = QPushButton("＋ 新建笔记")
        self.new_button.clicked.connect(self.new_note)
        header.addWidget(self.new_button)
        more = QToolButton()
        more.setText("更多 ▾")
        more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(more)
        menu.addAction("另存为新笔记", self.save_copy)
        menu.addAction("选择笔记目录…", self.choose)
        menu.addAction("重新读取文件", self.reload)
        more.setMenu(menu)
        header.addWidget(more)

        split = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(split, 1)
        left = QWidget()
        nav = QVBoxLayout(left)
        self.scope = QComboBox()
        self.scope.addItems(["全部笔记", "回收站"])
        self.search = QLineEdit()
        self.search.setPlaceholderText("筛选标题或日期")
        self.search.setClearButtonEnabled(True)
        self.order = QComboBox()
        self.order.addItems(["最近修改在前", "最近创建在前", "按标题排列"])
        self.items = QListWidget()
        for widget in (self.scope, self.search, self.order, self.items):
            nav.addWidget(widget)
        split.addWidget(left)

        right = QWidget()
        editor = QVBoxLayout(right)
        self.title = QLineEdit()
        self.title.setMaxLength(120)
        self.title.setPlaceholderText("笔记标题")
        self.meta = QLabel()
        self.meta.setWordWrap(True)
        self.body = QPlainTextEdit()
        self.body.setPlaceholderText("在这里写下正文…")
        self.body.setTabChangesFocus(False)
        self.body.document().setDocumentMargin(14)
        for widget in (self.title, self.meta, self.body):
            editor.addWidget(widget)
        actions = QHBoxLayout()
        editor.addLayout(actions)
        self.status = QLabel()
        actions.addWidget(self.status, 1)
        self.last_deleted = None
        self.undo_button = QPushButton("撤销刚才的删除")
        self.undo_button.hide()
        self.undo_button.clicked.connect(self.undo_delete)
        actions.addWidget(self.undo_button)
        self.delete_button = QPushButton("删除")
        self.delete_button.clicked.connect(self.toggle_deleted)
        actions.addWidget(self.delete_button)
        self.save_button = QPushButton("保存")
        self.save_button.clicked.connect(self.save)
        actions.addWidget(self.save_button)
        split.addWidget(right)
        split.setChildrenCollapsible(False)
        split.setStretchFactor(1, 1)
        split.setSizes([245, 700])

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(450)
        self.timer.timeout.connect(self.store_draft)
        self.title.textChanged.connect(self.changed)
        self.body.textChanged.connect(self.changed)
        self.scope.currentIndexChanged.connect(self.switch_scope)
        self.search.textChanged.connect(self.refresh)
        self.order.currentIndexChanged.connect(self.refresh)
        self.items.currentItemChanged.connect(self.select)
        for keys, fn in [(QKeySequence.StandardKey.Save, self.save),
                         (QKeySequence.StandardKey.New, self.new_note)]:
            shortcut = QShortcut(QKeySequence(keys), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(fn)
        hub.closed.connect(self.store_draft)
        draft = hub.db.get("personal_notes_draft", {}) or {}
        rows = self.service.rows()
        key = draft.get("id")
        if not any(r["id"] == key for r in rows):
            key = None
        has_draft = bool(draft.get("title") or draft.get("body") or draft.get("id"))
        self.load(key if has_draft else (rows[0]["id"] if rows else None))
        if has_draft:
            self.revision = draft.get("revision", self.revision)
            self.title.setText(draft.get("title", ""))
            self.body.setPlainText(draft.get("body", ""))
            self.status.setText("已恢复草稿")
        self.refresh()

    def fields(self):
        return self.title.text(), self.body.toPlainText()

    def changed(self, *_):
        self.save_button.setEnabled(not self.trash and self.fields() != self.original)
        self.status.setText("有未保存的修改" if self.save_button.isEnabled() else "")
        self.timer.start()

    def store_draft(self):
        self.timer.stop()
        title, body = self.fields()
        draft = {} if self.fields() == self.original or self.trash else dict(
            id=self.key, revision=self.revision, title=title, body=body)
        self.hub.db.set("personal_notes_draft", draft)

    def refresh(self, *_):
        rows = self.service.rows(self.trash)
        if self.order.currentIndex() == 1:
            rows.sort(key=lambda r: r["created"], reverse=True)
        elif self.order.currentIndex() == 2:
            rows.sort(key=lambda r: r["title"].casefold())
        query = self.search.text().casefold().strip()
        with QSignalBlocker(self.items):
            self.items.clear()
            for r in rows:
                modified = timestamp(r["modified"] or r["created"])
                if query not in f"{r['title']} {modified} {r['created'][:10]}".casefold():
                    continue
                item = QListWidgetItem(f"{r['title']}\n{modified}")
                item.setData(Qt.ItemDataRole.UserRole, r["id"])
                item.setToolTip(r["path"])
                self.items.addItem(item)
                if self.key == r["id"]:
                    self.items.setCurrentItem(item)

    def load(self, key):
        try:
            row = self.service.row(key) if key else None
            body, revision = self.service.document(key) if key else ("", None)
        except (ValueError, OSError, UnicodeError) as exc:
            self.status.setText(f"读取失败 · {exc}")
            return False
        self.key, self.revision = key, revision
        self.original = (row["title"] if row else "", body)
        with QSignalBlocker(self.title), QSignalBlocker(self.body):
            self.title.setText(self.original[0])
            self.body.setPlainText(body)
        self.meta.setText(
            f"创建 {timestamp(row['created'])}    修改 {timestamp(row['modified'] or row['created'])}"
            if row else ("回收站为空" if self.trash else "新笔记"))
        self.meta.setToolTip(row["path"] if row else str(self.service.directory()))
        self.body.setReadOnly(self.trash)
        self.title.setReadOnly(self.trash)
        self.delete_button.setEnabled(bool(key))
        self.delete_button.setText("撤销删除" if self.trash else "删除")
        self.save_button.setEnabled(False)
        self.status.clear()
        return True

    def select(self, item, _previous):
        key = item.data(Qt.ItemDataRole.UserRole) if item else None
        if key != self.key:
            if self.can_leave() and self.load(key):
                self.store_draft()
            with QSignalBlocker(self.items):
                for index in range(self.items.count()):
                    if self.items.item(index).data(Qt.ItemDataRole.UserRole) == self.key:
                        self.items.setCurrentRow(index)
                        break
                else:
                    self.items.setCurrentRow(-1)

    def switch_scope(self, index):
        if not self.can_leave():
            with QSignalBlocker(self.scope):
                self.scope.setCurrentIndex(int(self.trash))
            return
        self.trash = bool(index)
        with QSignalBlocker(self.search):
            self.search.clear()
        rows = self.service.rows(self.trash)
        self.load(None)
        if rows:
            self.load(rows[0]["id"])
        self.refresh()

    def new_note(self):
        if self.can_leave():
            self.show_active(None)
            self.title.setFocus()

    def show_active(self, key):
        self.trash = False
        with QSignalBlocker(self.scope), QSignalBlocker(self.search):
            self.scope.setCurrentIndex(0)
            self.search.clear()
        self.load(key)
        self.refresh()
        self.store_draft()

    def save_copy(self):
        if not self.trash:
            return self.save(copy=True)

    def save(self, checked=False, *, copy=False):
        if self.trash:
            return False
        if self.key and self.fields() == self.original and not copy:
            return True
        try:
            if self.key and not copy:
                self.service.update(self.key, *self.fields(), self.revision)
                key = self.key
            else:
                key = self.service.create(*self.fields())["id"]
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "未保存", str(exc))
            return False
        self.show_active(key)
        self.status.setText("已保存")
        return True

    def toggle_deleted(self):
        if not self.key or not self.can_leave():
            return
        key = self.key
        if self.trash:
            if key == self.last_deleted:
                self.undo_button.hide()
                self.last_deleted = None
            self.service.set_deleted(key, False)
            self.show_active(key)
            self.status.setText("已恢复到全部笔记")
        else:
            self.service.set_deleted(key, True)
            self.last_deleted = key
            self.undo_button.show()
            self.load(None)
            self.refresh()
            self.store_draft()
            self.status.setText("已移入回收站，可撤销删除")

    def undo_delete(self):
        if self.last_deleted and self.can_leave():
            key = self.last_deleted
            self.service.set_deleted(key, False)
            self.last_deleted = None
            self.undo_button.hide()
            self.show_active(key)
            self.status.setText("已撤销删除")

    def reload(self):
        if self.can_leave():
            self.load(self.key)
            self.refresh()

    def choose(self):
        path = QFileDialog.getExistingDirectory(self, "新笔记保存目录", str(self.service.directory()))
        if path:
            self.hub.db.set("personal_notes_dir", path)
            self.status.setText("已更新新笔记保存目录")

    def can_leave(self, *_):
        if self.fields() == self.original:
            return True
        buttons = QMessageBox.StandardButton
        answer = QMessageBox.question(self, "尚未保存", "保存当前笔记的修改？",
                                      buttons.Save | buttons.Discard | buttons.Cancel, buttons.Save)
        if answer == buttons.Save:
            return self.save()
        if answer == buttons.Discard:
            self.load(self.key)
            self.store_draft()
            return True
        return False
