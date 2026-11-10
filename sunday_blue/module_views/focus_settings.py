"""Small form for timer lengths and per-phase audio, using the existing Qt stack."""
from pathlib import Path
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QHBoxLayout, QLabel,
    QSpinBox, QCheckBox, QPushButton, QFileDialog, QMessageBox, QDialogButtonBox, QWidget)
from ..modules.focus_preferences import PHASES, import_sound
from ..modules.focus_alarm import FocusAlarm


class FocusSettings(QDialog):
    def __init__(self, hub, parent=None):
        super().__init__(parent)
        self.hub = hub
        self.draft = hub.focus.options()
        self.sounds = dict(self.draft['sounds'])
        self.preview = FocusAlarm(hub.root, self)
        self.setWindowTitle('番茄钟设置'); self.setMinimumWidth(520)
        layout = QVBoxLayout(self); layout.setSpacing(16)
        title = QLabel('找到自己的专注节奏'); title.setObjectName('title'); layout.addWidget(title)
        note = QLabel('时长修改从下一轮开始生效；正在进行的倒计时保持不变。')
        note.setObjectName('muted'); note.setWordWrap(True); layout.addWidget(note)
        form = QFormLayout(); self.fields = {}
        for key, title, maximum, suffix in (
            ('focus_minutes', '专注', 240, ' 分钟'), ('short_break_minutes', '短休息', 60, ' 分钟'),
            ('long_break_minutes', '长休息', 120, ' 分钟'), ('long_every', '长休息间隔', 12, ' 个番茄')):
            field = QSpinBox(); field.setRange(2 if key == 'long_every' else 1, maximum)
            field.setValue(self.draft[key]); field.setSuffix(suffix)
            self.fields[key] = field; form.addRow(title, field)
        self.enabled = QCheckBox('阶段结束时播放声音'); self.enabled.setChecked(self.draft['sound_enabled'])
        form.addRow(self.enabled)
        self.volume = QSpinBox(); self.volume.setRange(0, 100); self.volume.setSuffix(' %')
        self.volume.setValue(self.draft['volume']); form.addRow('提醒音量', self.volume)
        layout.addLayout(form); self.sound_labels = {}
        for phase, title in PHASES.items():
            row = QHBoxLayout(); label = QLabel(); self.sound_labels[phase] = label
            row.addWidget(QLabel(title + '结束')); row.addWidget(label, 1)
            for text, callback in (('选择 MP3 / WAV', lambda _, p=phase: self.choose(p)),
                                   ('默认', lambda _, p=phase: self.reset(p)),
                                   ('试听', lambda _, p=phase: self.listen(p))):
                button = QPushButton(text); button.clicked.connect(callback); row.addWidget(button)
            layout.addLayout(row)
        self.notice = QLabel('音频导入到 Sunday_Blue 内；一次播放最长 30 秒，不循环。')
        self.notice.setWordWrap(True); self.notice.setObjectName('muted'); layout.addWidget(self.notice)
        self.preview.problem.connect(self.notice.setText)
        stop = QPushButton('停止试听'); stop.clicked.connect(self.preview.stop); layout.addWidget(stop)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save); buttons.rejected.connect(self.reject); layout.addWidget(buttons)
        self.update_labels()

    def update_labels(self):
        for phase, label in self.sound_labels.items():
            label.setText('自选音频' if self.sounds[phase] else '柔和提示音')
            label.setToolTip(self.sounds[phase] or '内置三音提示')

    def choose(self, phase):
        path, _ = QFileDialog.getOpenFileName(self, '选择结束提示音', '', '音频 (*.mp3 *.wav)')
        if not path: return
        try:
            self.sounds[phase] = import_sound(self.hub.root, path)
            self.update_labels(); self.notice.setText(f'已导入 {Path(path).name}；点击保存后生效。')
        except Exception as exc: QMessageBox.warning(self, '未能导入', str(exc))

    def reset(self, phase):
        self.sounds[phase] = ''; self.update_labels()

    def values(self):
        return {k: field.value() for k, field in self.fields.items()} | {
            'sound_enabled': self.enabled.isChecked(), 'volume': self.volume.value(), 'sounds': dict(self.sounds)}

    def listen(self, phase):
        self.preview.play(phase, self.values())

    def save(self):
        try: self.hub.focus.set_options(self.values())
        except Exception as exc:
            QMessageBox.warning(self, '未能保存', str(exc)); return
        self.accept()

    def done(self, result):
        self.preview.stop(); super().done(result)
