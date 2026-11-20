from datetime import date

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QHBoxLayout, QHeaderView, QLabel,
    QListWidget, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from ..modules.day_plan import default_rows, time_range


class WeeklyPlanPage(QWidget):
    def __init__(self, hub, parent=None):
        super().__init__(parent)
        self.hub = hub
        self.current = None
        self.reference_day = date.today()
        self.dirty = False
        box = QVBoxLayout(self)
        title = QLabel('每周计划')
        title.setObjectName('title')
        box.addWidget(title)
        split = QSplitter()
        box.addWidget(split, 1)
        self.days = QListWidget()
        self.days.addItems(['周一 · 学习主攻','周二 · 副业攻坚','周三 · 学习与兴趣',
                            '周四 · 学习强化','周五 · 自由创造','周六 · 自主安排',
                            '周日 · 休息与复盘','晚归日','晚归次日'])
        self.days.setStyleSheet('QListWidget::item:selected {background:#d9efe6;color:#214b40;}')
        split.addWidget(self.days)
        pane = QWidget()
        layout = QVBoxLayout(pane)
        self.heading = QLabel()
        self.heading.setObjectName('cardTitle')
        layout.addWidget(self.heading)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(['时间', '计划'])
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(True)
        self.table.setStyleSheet('QTableWidget {gridline-color: palette(mid);} QTableWidget::item {padding: 6px;} QTableWidget::item:selected {background:#dceefb;color:#203c50;}')
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setMinimumSectionSize(38)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 170)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setToolTip('双击时间或计划即可编辑')
        layout.addWidget(self.table, 1)
        actions = QHBoxLayout()
        layout.addLayout(actions)
        add = QPushButton('添加一行')
        add.clicked.connect(self.add_row)
        actions.addWidget(add)
        remove = QPushButton('移除所选行')
        remove.clicked.connect(self.remove_row)
        actions.addWidget(remove)
        self.status = QLabel()
        actions.addWidget(self.status, 1)
        save = QPushButton('保存安排')
        save.clicked.connect(self.save)
        actions.addWidget(save)
        split.addWidget(pane)
        split.setStretchFactor(1, 1)
        split.setSizes([180, 680])
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(600)
        self.timer.timeout.connect(self.save)
        self.table.itemChanged.connect(self.changed)
        self.days.currentRowChanged.connect(self.select)
        self.days.setCurrentRow(date.today().weekday())
        hub.closed.connect(self.can_leave)

    def defaults(self, i):
        return '\n'.join(t+' · '+v for t,v in default_rows(i,self.reference_day.weekday()))

    def insert(self, row, when, what):
        self.table.insertRow(row)
        time_cell = QTableWidgetItem(when)
        time_cell.setToolTip("例如 9:00–10:30、9点到10点、23:00以后。自由文字只在表内展示。")
        time_cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, 0, time_cell)
        self.table.setItem(row, 1, QTableWidgetItem(what))

    def select(self, index):
        if index < 0:
            return
        self.can_leave()
        self.current = index
        self.heading.setText(self.days.item(index).text())
        raw = self.hub.db.get('weekly_plan:'+str(index), self.defaults(index))
        self.table.blockSignals(True)
        try:
            self.table.setRowCount(0)
            for line in raw.splitlines():
                when, sep, what = line.partition(' · ')
                self.insert(self.table.rowCount(), when if sep else '', what if sep else line)
        finally:
            self.table.blockSignals(False)
        self.status.setText('' if raw else '这一天还没有安排')

    def reveal(self, slot, row, reference_day=None):
        self.reference_day = reference_day or date.today()
        if self.days.currentRow()==slot:self.select(slot)
        self.days.setCurrentRow(slot)
        if row is not None and row < self.table.rowCount():
            self.table.setCurrentCell(row, 0)
            self.table.scrollToItem(self.table.item(row,0))

    def add_row(self):
        current = self.table.currentRow()
        row = current + 1 if current >= 0 else self.table.rowCount()
        self.insert(row, '', '')
        self.table.setCurrentCell(row, 0)
        self.table.editItem(self.table.item(row, 0))

    def remove_row(self):
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)
            self.changed()

    def changed(self, *args):
        self.dirty = True
        self.status.setText('待保存')
        self.timer.start()

    def save(self):
        if self.dirty and self.current is not None:
            lines = []
            for row in range(self.table.rowCount()):
                when, what = [self.table.item(row, col).text() for col in (0, 1)]
                lines.append(when+' · '+what if when else what)
            self.hub.db.set('weekly_plan:'+str(self.current), '\n'.join(lines))
            self.dirty = False
            invalid = any(self.table.item(r,0).text().strip() and not time_range(self.table.item(r,0).text()) for r in range(self.table.rowCount()))
            self.status.setText('已保存 · 自由文字时间仅在计划表展示，可填 9:00–10:30' if invalid else '已保存')
            self.hub.changed.emit('weekly_plan')

    def can_leave(self, *args):
        editor = QApplication.focusWidget()
        if editor and self.table.viewport().isAncestorOf(editor):
            editor.clearFocus()
        self.timer.stop()
        self.save()
        return True
