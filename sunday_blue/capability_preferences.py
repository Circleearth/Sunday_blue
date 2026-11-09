"""Configure role grants and loading policies without duplicating plugin editors."""
import copy
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox,
    QTableWidget, QTableWidgetItem, QComboBox, QLineEdit, QPushButton, QPlainTextEdit, QHeaderView)
from .capabilities import BUILTINS, ALWAYS, RESPONSIBILITIES, allowed_catalog


class CapabilityDialog(QDialog):
    def __init__(self, root, config, role, parent=None):
        super().__init__(parent)
        self.root, self.config, self.role = root, copy.deepcopy(config), role
        self.value = self.config['roles'][role]
        self.setWindowTitle('角色能力与按需加载')
        self.resize(800, 580)
        layout = QVBoxLayout(self)
        note = QLabel('能力授权与人格分开。先在插件、Skills、MCP 页面完成绑定，再选择加载方式。'
                      '\n“按需”由 @能力ID、关键词或模型工具申请触发；不能扩大文件权限。')
        note.setWordWrap(True); layout.addWidget(note)
        row = QHBoxLayout(); self.grants = {}
        for key, title in BUILTINS.items():
            box = QCheckBox(title.split('（')[0])
            box.setChecked(self.value.get('capabilities', {}).get(key, True))
            box.setToolTip('还需全局功能开关启用；不会新增任何目录或 MCP 授权。')
            self.grants[key] = box; row.addWidget(box)
            box.toggled.connect(self.reload)
        layout.addLayout(row)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(['能力（稳定 ID）', '加载方式', '关键词，英文逗号分隔（可选）'])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)
        layout.addWidget(QLabel('职责边界（运行规则，不替代身份、性格、说话方式）'))
        self.responsibility = QPlainTextEdit(self.value.get('responsibility', RESPONSIBILITIES.get(role, '')))
        self.responsibility.setMaximumHeight(85); layout.addWidget(self.responsibility)
        row = QHBoxLayout(); row.addStretch()
        cancel = QPushButton('取消'); cancel.clicked.connect(self.reject); row.addWidget(cancel)
        save = QPushButton('应用到设置草稿'); save.clicked.connect(self.save); row.addWidget(save)
        layout.addLayout(row)
        self.rows = {}; self.reload()

    def stash(self):
        policies = self.value.setdefault('capability_loading', {})
        for key, (mode, keywords) in self.rows.items():
            policies[key] = {'mode': mode.currentData(), 'keywords': keywords.text()[:1000]}

    def reload(self):
        self.stash()
        self.value['capabilities'] = {k: b.isChecked() for k, b in self.grants.items()}
        catalog = allowed_catalog(self.root, self.config, self.role)
        self.table.setRowCount(0); self.rows = {}
        for key, label in catalog.items():
            row = self.table.rowCount(); self.table.insertRow(row)
            item = QTableWidgetItem(key); item.setToolTip(label)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable); self.table.setItem(row, 0, item)
            mode = QComboBox(); mode.addItem('每轮加载', 'always'); mode.addItem('按需加载', 'on_demand')
            policy = self.value.get('capability_loading', {}).get(key, {})
            mode.setCurrentIndex(max(0, mode.findData(policy.get('mode', 'always'))))
            keywords = QLineEdit(policy.get('keywords', ''))
            if key in ALWAYS:
                mode.setCurrentIndex(0); mode.setEnabled(False); keywords.setEnabled(False)
                mode.setToolTip('时间与寒暄属于时段判断，启用后由本地规则控制。')
            self.table.setCellWidget(row, 1, mode); self.table.setCellWidget(row, 2, keywords)
            self.rows[key] = (mode, keywords)

    def save(self):
        self.stash()
        self.value['responsibility'] = self.responsibility.toPlainText()[:3000]
        self.accept()
