from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QListWidget,QListWidgetItem,QPushButton,QInputDialog,QMessageBox
from PySide6.QtCore import Qt


class RelationsPage(QWidget):
    def __init__(self,hub,parent=None):
        super().__init__(parent);self.hub=hub
        layout=QVBoxLayout(self);layout.setContentsMargins(32,24,32,24)
        title=QLabel('相处不是一张成绩单。');title.setObjectName('title');layout.addWidget(title)
        note=QLabel('长期关系、短期情绪和共同经历分别保存。情绪会随时间平复；休息和没记录都不是过错，恢复关系不需要送礼。');note.setWordWrap(True);layout.addWidget(note)
        self.items=QListWidget();layout.addWidget(self.items,1)
        self.setback=QPushButton('主动记录一次未达成（可选）');self.setback.clicked.connect(self.report);layout.addWidget(self.setback)
        hub.changed.connect(lambda *_:self.refresh());self.refresh()
    def refresh(self):
        selected=self.items.currentRow();self.items.clear()
        for r in self.hub.relations.list():
            item=QListWidgetItem(f"{r['name']}\n长期关系 {r['affinity']:.0f} · 短期情绪 {r['mood_label']}\n{r['last_event']}")
            item.setData(Qt.ItemDataRole.UserRole,r['role_id']);self.items.addItem(item)
        self.items.setCurrentRow(max(0,selected))
    def report(self):
        item=self.items.currentItem()
        if not item:return
        text,ok=QInputDialog.getText(self,'只记录已知情况','发生了什么？不因缺少记录推断未完成。')
        if ok and text.strip() and QMessageBox.question(self,'确认记录','这会产生轻微、有限的情绪反馈，每天至多降低 1 点关系。可以不记录；休息不应算失败。继续？')==QMessageBox.StandardButton.Yes:
            try:self.hub.relations.report_setback(item.data(Qt.ItemDataRole.UserRole),text);self.refresh()
            except Exception as exc:QMessageBox.warning(self,'无法记录',str(exc))
