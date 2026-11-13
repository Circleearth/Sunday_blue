"""Pomodoro workspace: display state only; Focus owns time and settlement."""
import math
from datetime import datetime
from PySide6.QtCore import QTimer, Qt, QRectF
from PySide6.QtGui import QPixmap, QPainter, QColor, QPen
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QBoxLayout, QLabel,
    QComboBox, QLineEdit, QPushButton, QListWidget, QListWidgetItem, QMessageBox,
    QSpinBox, QFrame, QScrollArea, QButtonGroup)
from ..roles import list_roles
from ..design_system import tokens
from ..modules.focus_preferences import PHASES
from .focus_settings import FocusSettings
from ..numeric_inputs import NumberSpin as QSpinBox, DecimalSpin as QDoubleSpinBox


def _hm(iso):
    try: return datetime.fromisoformat(iso).astimezone().strftime('%m-%d %H:%M')
    except (ValueError, TypeError): return ''


class TimerRing(QWidget):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config; self.fraction = 0
        self.setMinimumSize(260, 260)
        self.setStyleSheet('background:transparent;')

    def paintEvent(self, event):
        t = tokens(self.config.value.get('ui_theme', 'dark'))
        painter = QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        diameter = min(self.width(), self.height()) - 20
        rect = QRectF((self.width()-diameter)/2, (self.height()-diameter)/2, diameter, diameter)
        painter.setPen(QPen(QColor(t['border']), 7)); painter.drawEllipse(rect)
        pen = QPen(QColor(t['accent']), 7); pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen); painter.drawArc(rect, 90*16, -round(360*16*self.fraction))


def _card():
    frame = QFrame(); frame.setObjectName('card')
    layout = QVBoxLayout(frame); layout.setContentsMargins(22, 20, 22, 20); layout.setSpacing(14)
    return frame, layout


class FocusPage(QWidget):
    def __init__(self, hub, parent=None):
        super().__init__(parent); self.hub = hub; self.phase = hub.focus.cycle()['next_phase']
        self._settled_id = None; self._records_key = None; self._art_role = None
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); outer.addWidget(scroll)
        content = QWidget(); scroll.setWidget(content)
        layout = QVBoxLayout(content); layout.setContentsMargins(28, 22, 28, 22); layout.setSpacing(18)
        head = QHBoxLayout(); titles = QVBoxLayout()
        eyebrow = QLabel('FOCUS / 专注空间'); eyebrow.setObjectName('eyebrow'); titles.addWidget(eyebrow)
        title = QLabel('一件事，一小段时间。'); title.setObjectName('title'); titles.addWidget(title)
        head.addLayout(titles, 1)
        settings = QPushButton('节奏与提示音'); settings.clicked.connect(self.configure); head.addWidget(settings)
        layout.addLayout(head)
        self.banner = QLabel(); self.banner.setWordWrap(True); self.banner.setObjectName('cardTitle'); self.banner.hide()
        layout.addWidget(self.banner)
        self.columns = QBoxLayout(QBoxLayout.Direction.LeftToRight); self.columns.setSpacing(18); layout.addLayout(self.columns)
        timer_card, timer_layout = _card(); self.columns.addWidget(timer_card, 3)
        modes = QHBoxLayout(); self.mode_buttons = {}; group = QButtonGroup(self); group.setExclusive(True)
        for phase, name in PHASES.items():
            button = QPushButton(name); button.setCheckable(True); group.addButton(button)
            button.clicked.connect(lambda checked=False, p=phase: self.select_phase(p))
            self.mode_buttons[phase] = button; modes.addWidget(button)
        timer_layout.addLayout(modes)
        self.ring = TimerRing(hub.config); ring_layout = QVBoxLayout(self.ring); ring_layout.setSpacing(5)
        ring_layout.addStretch()
        self.phase_label = QLabel(); self.phase_label.setAlignment(Qt.AlignmentFlag.AlignCenter); self.phase_label.setObjectName('muted')
        ring_layout.addWidget(self.phase_label)
        self.clock = QLabel(); self.clock.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.clock.setStyleSheet('font-size:58px; font-weight:600; background:transparent;')
        ring_layout.addWidget(self.clock)
        self.cycle_label = QLabel(); self.cycle_label.setAlignment(Qt.AlignmentFlag.AlignCenter); self.cycle_label.setObjectName('muted')
        ring_layout.addWidget(self.cycle_label); ring_layout.addStretch()
        timer_layout.addWidget(self.ring)
        duration_row = QHBoxLayout(); duration_row.addStretch(); duration_row.addWidget(QLabel('本轮时长'))
        self.target = QSpinBox(); self.target.setRange(1, 240); self.target.setSuffix(' 分钟')
        self.target.valueChanged.connect(self.duration_changed); duration_row.addWidget(self.target); duration_row.addStretch()
        timer_layout.addLayout(duration_row)
        controls = QHBoxLayout(); self.start = QPushButton('开始专注'); self.start.setObjectName('primary')
        self.start.clicked.connect(self.begin); controls.addWidget(self.start)
        self.pause = QPushButton('暂停'); self.pause.clicked.connect(self.toggle); controls.addWidget(self.pause)
        self.finish = QPushButton('提前结束'); self.finish.clicked.connect(self.settle); controls.addWidget(self.finish)
        timer_layout.addLayout(controls)
        self.hint = QLabel('到点自动结算并提醒。下一阶段由你开始，不自动连跑。')
        self.hint.setObjectName('muted'); self.hint.setWordWrap(True); timer_layout.addWidget(self.hint)
        self.silence = QPushButton('停止提醒声音'); self.silence.setObjectName('ghost')
        self.silence.clicked.connect(hub.focus_alarm.stop); self.silence.clicked.connect(self.silence.hide); self.silence.hide()
        timer_layout.addWidget(self.silence)
        companion, side = _card(); self.columns.addWidget(companion, 2)
        heading = QLabel('这一轮，专心做什么'); heading.setObjectName('cardTitle'); side.addWidget(heading)
        side.addWidget(QLabel('活动类别')); self.category = QComboBox(); self.category.setEditable(True)
        self.category.addItems([c for c in hub.focus.categories() if c!='运动']); side.addWidget(self.category)
        self.task_caption=QLabel('绑定工作任务（可选）');side.addWidget(self.task_caption)
        self.task=QComboBox();self.task.addItem('不绑定任务',None);side.addWidget(self.task)
        self.category.currentTextChanged.connect(self.task_visibility)
        self.label = QLineEdit(); self.label.setPlaceholderText('给这段专注一个小目标（可选）'); side.addWidget(self.label)
        side.addSpacing(8); side.addWidget(QLabel('陪伴角色'))
        self.roles = QComboBox()
        for rid, name, *_ in list_roles(hub.root): self.roles.addItem(name, rid)
        self.roles.setCurrentIndex(max(0, self.roles.findData('rui'))); side.addWidget(self.roles)
        self.avatar = QLabel(); self.avatar.setAlignment(Qt.AlignmentFlag.AlignCenter); self.avatar.setFixedHeight(90)
        side.addWidget(self.avatar)
        self.companion_note = QLabel('把注意力交给眼前。暂停和休息都不会扣分。')
        self.companion_note.setWordWrap(True); self.companion_note.setObjectName('muted'); side.addWidget(self.companion_note)
        self.feed = QListWidget(); self.feed.setWordWrap(True); self.feed.setMaximumHeight(130); side.addWidget(self.feed)
        self.reply_source=QLabel();self.reply_source.setObjectName("muted");side.addWidget(self.reply_source)
        side.addStretch()
        summary, stats_layout = _card(); self.stats = QLabel(); self.stats.setWordWrap(True)
        self.stats.setObjectName('cardTitle'); stats_layout.addWidget(self.stats); layout.addWidget(summary)
        history, history_layout = _card(); caption = QLabel('最近的专注 · 保留真实努力'); caption.setObjectName('cardTitle')
        history_layout.addWidget(caption)
        note = QLabel('严格超过 2 分钟才计有效记录。学习每天累计有效 10 分钟额外奖励 3 金币；工作每有效分钟 1 积分，不兑换商城。家务每 5 分钟 1 金币，每日最多 12 金币；休息不奖励。以下为最近 30 条。')
        note.setWordWrap(True); note.setObjectName('muted'); history_layout.addWidget(note)
        self.records = QListWidget(); self.records.setWordWrap(True); self.records.setMinimumHeight(130)
        self.records.setMaximumHeight(220); history_layout.addWidget(self.records); layout.addWidget(history)
        hub.feedback.connect(self.feedback); hub.changed.connect(lambda *_: self.refresh(True))
        hub.focus_completed.connect(self.completed); self.roles.currentIndexChanged.connect(self.art)
        self.timer = QTimer(self); self.timer.setInterval(1000); self.timer.timeout.connect(self.refresh)
        hub.closed.connect(self.timer.stop); self.timer.start(); self.refresh(True)

    def task_visibility(self,*args):
        show=self.category.currentText()=='工作' and self.phase=='focus'
        self.task_caption.setVisible(show);self.task.setVisible(show)
        self.task.setEnabled(show and self.hub.focus.status()['state']=='idle')

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'columns'):
            self.columns.setDirection(QBoxLayout.Direction.TopToBottom if self.width() < 780 else QBoxLayout.Direction.LeftToRight)

    def configure(self):
        dialog = FocusSettings(self.hub, self); dialog.exec(); dialog.deleteLater(); self.refresh(True)

    def select_phase(self, phase):
        if self.hub.focus.status()['state'] != 'idle': return
        self.phase = phase; self.refresh()

    def duration_changed(self, value):
        if self.hub.focus.status()['state'] == 'idle':
            self.invoke(lambda: self.hub.focus.set_options({self.phase+'_minutes': value}))

    def art(self):
        role = str(self.roles.currentData())
        if role == self._art_role: return
        self._art_role = role; self.avatar.clear()
        pix = QPixmap(str(self.hub.root/'assets/roles'/role/'avatar.png'))
        if pix.isNull(): self.avatar.setText(self.roles.currentText())
        else: self.avatar.setPixmap(pix.scaled(80, 80, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def invoke(self, fn):
        try: return fn()
        except Exception as exc: QMessageBox.warning(self, '暂未完成', str(exc))

    def begin(self):
        if self.hub.focus.status()['state'] == 'idle':
            for i in range(self.feed.count()):
                item=self.feed.item(i)
                if not item.text().startswith('【上一轮】'):item.setText('【上一轮】'+item.text())
        result = self.invoke(lambda: self.hub.start_focus(self.category.currentText(), self.label.text(),
            self.roles.currentData(), self.phase, self.target.value()*60,
            task_id=self.task.currentData() if self.category.currentText()=='工作' and self.phase=='focus' else None))
        if result: self.banner.hide(); self.silence.hide(); self.hub.focus_alarm.stop()
        self.refresh(True)

    def toggle(self):
        self.invoke(self.hub.focus.pause if self.hub.focus.status()['state']=='running' else self.hub.focus.resume)
        self.refresh()

    def settle(self):
        result = self.invoke(self.hub.focus.finish)
        if result and result['run_id'] != self._settled_id:
            self._settled_id = result['run_id']; self.phase = self.hub.focus.cycle()['next_phase']
            text = self.result_text(result)
            self.banner.setText(text); self.banner.show()
            QMessageBox.information(self, '本轮已结束', text)
        self.refresh(True)

    def result_text(self, result):
        reward=(f"本次 +{result.get('work_points',0)} 工作积分" if (result.get('record') or {}).get('category')=='工作' else f"本次 +{result['coins_earned']} 金币")
        task=('\n任务：'+result['task_title']+f" · 实际进度 {result.get('task_progress',0)}%" if result.get('task_title') else '')
        return PHASES[result['phase']]+'已结束 · '+reward+f" · 今日 {int(result['today_seconds']//60)} 分钟\n"+result['feedback']+task

    def completed(self, result):
        self._settled_id = result['run_id']; self.phase = self.hub.focus.cycle()['next_phase']
        self.banner.setText(self.result_text(result)); self.banner.show(); self.silence.show(); self.refresh(True)

    def feedback(self, role, text):
        source=self.hub.db.get("focus_dialogue_status",{}).get("source")
        self.reply_source.setText("本次陪伴：模型生成" if source=="llm" else "本次陪伴：本地备用短句")
        names = {r[0]: r[1] for r in list_roles(self.hub.root)}
        item = QListWidgetItem(names.get(role, '伙伴')+'：'+text); self.feed.addItem(item)
        while self.feed.count()>20: self.feed.takeItem(0)
        self.feed.scrollToBottom()

    def refresh(self, full=False):
        state = self.hub.focus.status(); active = state['state'] != 'idle'
        if full:
            selected_task=state.get('task_id') if active else self.task.currentData()
            choices=[(None,'不绑定任务')]+[(r['id'],r['title']) for r in self.hub.work.tasks(True) if (not r['archived'] and r['status'] not in ('done','paused')) or active and r['id']==selected_task]
            if [(self.task.itemData(i),self.task.itemText(i)) for i in range(self.task.count())]!=choices:
                self.task.blockSignals(True);self.task.clear()
                for task_id,title in choices:self.task.addItem(title,task_id)
                self.task.setCurrentIndex(max(0,self.task.findData(selected_task)));self.task.blockSignals(False)
            if active:self.task.setCurrentIndex(max(0,self.task.findData(selected_task)))
            roles = list_roles(self.hub.root)
            choices = [(self.roles.itemData(i), self.roles.itemText(i)) for i in range(self.roles.count())]
            if choices != [(r[0], r[1]) for r in roles]:
                selected = self.roles.currentData(); self.roles.blockSignals(True); self.roles.clear()
                for rid, name, *_ in roles: self.roles.addItem(name, rid)
                self.roles.setCurrentIndex(max(0, self.roles.findData(selected))); self.roles.blockSignals(False); self._art_role = None
        if active:
            self.phase = state['phase']; self.category.setEditText(state['category']); self.label.setText(state['label'])
            self.roles.setCurrentIndex(max(0, self.roles.findData(state['role_id'])))
        options = self.hub.focus.options()
        duration = state['duration'] if active else options[self.phase+'_minutes']*60
        seconds = math.ceil(max(0, duration-state['elapsed'])) if duration else int(state['elapsed'])
        self.clock.setText(f'{seconds//60:02d}:{seconds%60:02d}')
        self.phase_label.setText(PHASES[self.phase] + (' · 已暂停' if state['state']=='paused' else ' · 进行中' if active else ' · 准备好再开始'))
        self.ring.fraction = min(1, state['elapsed']/duration) if duration else 0; self.ring.update()
        self.target.blockSignals(True)
        self.target.setRange(1, {'focus':240, 'short_break':60, 'long_break':120}[self.phase])
        self.target.setValue(max(1, int(duration//60))); self.target.blockSignals(False)
        self.target.setVisible(not active or bool(duration)); self.target.setEnabled(not active)
        for phase, button in self.mode_buttons.items():
            button.setChecked(phase == self.phase); button.setEnabled(not active)
        theme = self.hub.config.value.get('ui_theme','dark')
        if getattr(self,'_mode_theme',None) != theme:
            self._mode_theme = theme; t = tokens(theme)
            for button in self.mode_buttons.values():
                button.setStyleSheet(f"QPushButton:checked {{ background:{t['accent_soft']}; color:{t['text']}; border-color:{t['accent']}; }}")
        self.start.setText('开始'+PHASES[self.phase]); self.start.setEnabled(not active)
        self.pause.setEnabled(active); self.pause.setText('继续' if state['state']=='paused' else '暂停')
        self.finish.setEnabled(active); self.finish.setText('结束休息' if self.phase!='focus' else '提前结束')
        for widget in (self.category, self.label, self.roles): widget.setEnabled(not active)
        cycle = self.hub.focus.cycle(); position = cycle['completed'] % options['long_every']
        self.cycle_label.setText(f"本组已完成 {position} / {options['long_every']} 个番茄")
        self.hint.setText('旧版正计时已保留，请手动结束本轮。' if active and not duration else '到点自动结算并提醒。下一阶段由你开始，不自动连跑。')
        if options['auto_loop']:
            self.hint.setText(f"自动循环最多 {options['max_rounds']} 轮专注；手动结束即停止。")
        self.art();self.task_visibility()
        if full:
            stats = self.hub.focus.stats()
            self.stats.setText(f"今日专注  {int(stats['today_seconds']//60)} 分钟     ·     完成 {stats['today_count']} 次     ·     连续 {stats['streak']} 天     ·     余额 {stats['balance']} 金币")
            records = self.hub.focus.records(); key = [(r['id'], r['seconds'], r['coins'],r.get('work_points',0)) for r in records]
            if key != self._records_key:
                self._records_key = key; self.records.clear()
                for r in records:
                    coins = (f' · +{r.get("work_points",0)} 工作积分' if r['category']=='工作' else f' · +{r["coins"]} 金币' if r['coins'] else ' · 已记录，本次无金币')
                    self.records.addItem(f"{r['category']}  ·  {int(r['seconds']//60)} 分钟{coins}  ·  {r['label'] or '认真生活的一小段'}\n{_hm(r['started'])} — {_hm(r['finished'])}")
                if not records: self.records.addItem('今天的第一段专注，从现在开始。')
