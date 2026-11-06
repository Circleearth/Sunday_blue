"""Manual local-model controls and the original LivingMemory dashboard."""
from pathlib import Path
from PySide6.QtCore import QThread, Signal, QUrl, QTimer, Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                              QComboBox, QDialog, QApplication, QCheckBox, QGridLayout)
from .storage import ROLES
from .living_memory import (ollama_status, start_ollama, stop_ollama, get_brain, pending_count)

_jobs = set()
_windows = []


class MemoryJob(QThread):
    result = Signal(object)
    def __init__(self, action):
        super().__init__(QApplication.instance())
        self.action = action
    def run(self):
        try:
            self.result.emit({'value': self.action()})
        except Exception as exc:
            self.result.emit({'error': str(exc)})


class MemoryPanel(QWidget):
    _settings_extra_title = '独立记忆大脑 · 本地模型'

    def __init__(self, root, role='rui', parent=None, config=None):
        super().__init__(parent)
        self.root = Path(root)
        self.busy = False
        self.config = config
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        info = QLabel('独立 Ollama · 端口 11435 · bge-m3\n启动软件不会启动 Ollama。启用插件后，完整对话会进入本地待整理队列；\n记忆整理使用当前聊天 API，产生少量用量。退出软件时停止本次启动的服务。')
        info.setWordWrap(True)
        info.setObjectName('muted')
        layout.addWidget(info)
        self.state = QLabel('正在检测…')
        self.state.setWordWrap(True)
        self.state.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.state)
        role_row = QHBoxLayout()
        self.roles = QComboBox()
        for rid, name, *_ in ROLES:
            self.roles.addItem(name, rid)
        self.roles.setCurrentIndex(max(0, self.roles.findData(role)))
        role_row.addWidget(self.roles)
        if config is not None:
            from .native_plugins import enabled
            self.enable_memory = QCheckBox('为此角色启用自动记忆（立即保存）')
            def refresh_enabled():
                self.enable_memory.blockSignals(True)
                self.enable_memory.setChecked(enabled(config.snapshot(), self.roles.currentData(), 'livingmemory'))
                self.enable_memory.blockSignals(False)
            def set_enabled(checked):
                config.value['roles'][self.roles.currentData()].setdefault('native_plugins', {})['livingmemory'] = checked
                config.save()
            self.enable_memory.toggled.connect(set_enabled)
            self.roles.currentIndexChanged.connect(refresh_enabled)
            refresh_enabled()
            role_row.addWidget(self.enable_memory)
        layout.addLayout(role_row)
        row = QGridLayout()
        layout.addLayout(row)
        self.buttons = []
        for index, (label, action) in enumerate((
            ('检测状态', self.refresh), ('启动 Ollama', lambda: self.run(lambda: start_ollama(self.root))),
            ('停止 Ollama', lambda: self.run(stop_ollama)),
            ('打开记忆图谱', self.open_dashboard), ('立即整理待处理对话', self.reflect))):
            button = QPushButton(label)
            button.clicked.connect(action)
            row.addWidget(button, index // 3, index % 3)
            self.buttons.append(button)
        self.timer = QTimer(self)
        self.timer.setInterval(10000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        QTimer.singleShot(0, self.refresh)

    def run(self, action, callback=None):
        if self.busy:
            return
        self.busy = True
        for button in self.buttons:
            button.setEnabled(False)
        self.roles.setEnabled(False)
        job = MemoryJob(action)
        _jobs.add(job)
        def finished():
            _jobs.discard(job)
            job.deleteLater()
        job.finished.connect(finished)
        self._callback = callback
        job.result.connect(self.completed)
        job.start()

    def completed(self, result):
        self.busy = False
        for button in self.buttons:
            button.setEnabled(True)
        self.roles.setEnabled(True)
        if result.get('error'):
            self.state.setText(result['error'])
        elif self._callback:
            self._callback(result['value'])
        else:
            self.state.setText('操作完成。点击检测状态查看结果。')

    def refresh(self):
        if self.busy or not self.isVisible():
            return
        role = self.roles.currentData()
        def inspect():
            state = ollama_status()
            state['pending'] = pending_count(self.root, role)
            # Monitoring never starts either Ollama or a brain.
            from .living_memory import _brains
            brain = _brains.get((str(self.root.resolve()), role))
            if brain and brain.process.poll() is None:
                state['brain'] = brain.call('/status', timeout=3)
            return state
        def show(state):
            model = '模型已就绪' if state['model_ready'] else '缺少 bge-m3'
            label = ('Ollama 运行中 · ' + model) if state['online'] else 'Ollama 已停止（聊天可正常使用）'
            label += '\n当前角色待整理：%s 轮' % state['pending']
            if state.get('brain', {}).get('error'):
                label += '\n最近整理失败：' + state['brain']['error']
            self.state.setText(label)
        self.run(inspect, show)

    def open_dashboard(self):
        role = self.roles.currentData()
        def show(brain):
            from PySide6.QtWebEngineWidgets import QWebEngineView
            dialog = QDialog(self.window())
            dialog.setWindowTitle(role + ' · LivingMemory')
            dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
            dialog.resize(1200, 820)
            layout = QVBoxLayout(dialog)
            layout.setContentsMargins(0, 0, 0, 0)
            view = QWebEngineView(dialog)
            # Each role gets an off-the-record cookie store: loopback ports share
            # cookie scope, so the default global profile must never be used.
            from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage
            profile = QWebEngineProfile(dialog)
            view.setPage(QWebEnginePage(profile, view))
            layout.addWidget(view)
            view.setUrl(QUrl(brain.url + '/dashboard/?token=' + brain.token))
            _windows.append(dialog)
            dialog.finished.connect(lambda: _windows.remove(dialog) if dialog in _windows else None)
            dialog.show()
            self.state.setText('已打开 ' + role + ' 的独立记忆图谱。')
        self.run(lambda: get_brain(self.root, role), show)

    def reflect(self):
        role = self.roles.currentData()
        self.run(lambda: get_brain(self.root, role).call('/reflect', {}, timeout=300),
                 lambda value: self.state.setText('已整理 %s 轮对话。' % value.get('processed', 0)))


def show_memory_panel(root, role, parent):
    dialog = QDialog(parent)
    dialog.setWindowTitle('记忆大脑 · Ollama')
    dialog.resize(900, 300)
    QVBoxLayout(dialog).addWidget(MemoryPanel(root, role, dialog, config=parent.config))
    dialog.exec()
