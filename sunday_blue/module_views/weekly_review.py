"""Weekly review workspace. Drafts, evidence and verification share a single week selector."""

import json
from datetime import date, datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QAbstractItemView,
    QVBoxLayout,
    QWidget,
)
from ..modules.database import day
from ..modules.weekly_review import STATES, shifted
from ..modules.weekly_evidence import METRICS, facts, overview
from ..modules.weekly_insights import trends, questions
from . import weekly_forms as forms


def text(value="", style=""):
    label = QLabel(value)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    if style:
        label.setObjectName(style)
    return label


def button(row, title, fn):
    b = QPushButton(title)
    b.clicked.connect(fn)
    row.addWidget(b)
    return b


def listing():
    w = QListWidget()
    w.setWordWrap(True)
    w.setAlternatingRowColors(True)
    w.setStyleSheet(
        "QListWidget::item {padding:6px} QListWidget::item:selected {background:#d6e9e6;color:#223c41}"
    )
    return w


def item(lst, title, data):
    i = QListWidgetItem(title)
    i.setData(Qt.ItemDataRole.UserRole, data)
    lst.addItem(i)


def selected(lst):
    i = lst.currentItem()
    return i.data(Qt.ItemDataRole.UserRole) if i else None


def table(headers):
    w = QTableWidget(0, len(headers))
    w.setHorizontalHeaderLabels(headers)
    w.verticalHeader().hide()
    w.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    w.setAlternatingRowColors(True)
    w.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    return w


def cells(widget, values):
    widget.setRowCount(len(values))
    for i, row in enumerate(values):
        for j, value in enumerate(row):
            cell = QTableWidgetItem(str(value))
            cell.setToolTip(str(value))
            widget.setItem(i, j, cell)
    widget.resizeRowsToContents()


class WeeklyPage(QWidget):
    def __init__(self, hub):
        super().__init__()
        self.hub = hub
        self.svc = hub.weekly
        self.pid = None
        self.bounds = self.svc.window()
        self.selected_issue = self.selected_action = None
        self.loading = False
        self.loaded = False
        self.data = None
        self.question = None
        self.unsaved = False
        self.follow_today = True
        self.last_day = day()
        self.calendar_timer = QTimer(self)
        self.calendar_timer.setInterval(30000)
        self.calendar_timer.timeout.connect(self.rollover)
        hub.closed.connect(self.calendar_timer.stop)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(400)
        self.timer.timeout.connect(self.flush)
        hub.closed.connect(self.flush)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        nav = QHBoxLayout()
        layout.addLayout(nav)
        nav.addWidget(text("每周复盘", "title"))
        nav.addStretch()
        button(nav, "‹", lambda: self.step(-1))
        self.weeks = QComboBox()
        nav.addWidget(self.weeks)
        self.weeks.activated.connect(self.pick)
        button(nav, "›", lambda: self.step(1))
        button(nav, "本周", self.today)
        button(nav, "选择日期", self.custom)
        button(nav, "周期设置", self.settings)
        self.wins = text("", "muted")
        layout.addWidget(self.wins)
        self.cards = []
        strip = QHBoxLayout()
        layout.addLayout(strip)
        for caption in ("复盘进度", "本周目标验收", "持续改善"):
            card = QFrame()
            card.setObjectName("card")
            box = QVBoxLayout(card)
            box.addWidget(text(caption, "muted"))
            label = text("—", "cardTitle")
            box.addWidget(label)
            strip.addWidget(card, 1)
            self.cards.append(label)
        row = QHBoxLayout()
        layout.addLayout(row)
        self.status = text("")
        row.addWidget(self.status, 1)
        self.primary = button(row, "开始本周复盘", self.transition)
        self.primary.setObjectName("primary")
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self.overview_tab = self.pane("本周与手记")
        self.facts = table(["领域", "本期事实 · 双击查看依据"])
        self.facts.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.facts.setMinimumHeight(156)
        self.facts.cellDoubleClicked.connect(self.read_facts)
        self.overview_tab.addWidget(self.facts, 2)
        self.notes = listing()
        self.notes.itemDoubleClicked.connect(self.read_entry)
        self.overview_tab.addWidget(self.notes, 1)
        actions = QHBoxLayout()
        self.overview_tab.addLayout(actions)
        self.add_note = button(actions, "记一件事 / 补充说明", self.entry)
        self.versions = button(actions, "历次定稿", self.snapshots)
        self.ai = button(actions, "带到总负责人聊天", self.to_chat)
        actions.addStretch()
        self.prompts = QComboBox()
        self.overview_tab.addWidget(self.prompts)
        self.prompts.activated.connect(self.pick_question)
        self.answer = QPlainTextEdit()
        self.answer.setPlaceholderText("可跳过，也可分几次填写。")
        self.answer.setMaximumHeight(96)
        self.overview_tab.addWidget(self.answer)
        self.answer.textChanged.connect(self.changed)
        act = self.pane("行动与验收")
        self.backlog = QCheckBox("同时查看更早尚待核验的行动")
        act.addWidget(self.backlog)
        self.backlog.toggled.connect(self.reload)
        self.action_list = listing()
        act.addWidget(self.action_list, 2)
        self.action_detail = QPlainTextEdit()
        self.action_detail.setReadOnly(True)
        act.addWidget(self.action_detail, 2)
        self.action_list.currentRowChanged.connect(self.inspect_action)
        row = QHBoxLayout()
        act.addLayout(row)
        self.new_action = button(row, "安排下周行动", lambda: self.edit_action("new"))
        self.edit_action_btn = button(row, "调整行动", lambda: self.edit_action("edit"))
        self.drop = button(row, "撤下重点", self.remove)
        self.carry = button(row, "带入下周", lambda: self.edit_action("carry"))
        row.addStretch()
        row = QHBoxLayout()
        act.addLayout(row)
        self.record = button(row, "记一次已做的行动", self.execution)
        self.mid = button(row, "周中检查", lambda: self.verify("周中"))
        self.accept = button(row, "验收结果", lambda: self.verify("验收"))
        self.launch = button(row, "开始关联专注", self.start_focus)
        row.addStretch()
        lib = self.pane("滚动问题库")
        row = QHBoxLayout()
        lib.addLayout(row)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索领域、问题或描述")
        row.addWidget(self.search, 1)
        self.filter = forms.combo([("在跟踪", "正在跟踪"), ("", "全部状态")] + [(s, s) for s in STATES])
        row.addWidget(self.filter)
        self.new_issue = button(row, "新问题", lambda: self.edit_issue("new"))
        self.update_issue = button(row, "编辑 / 转换状态", lambda: self.edit_issue("edit"))
        self.relapse = button(row, "标记复发", lambda: self.edit_issue("relapse"))
        split = QSplitter()
        lib.addWidget(split, 1)
        self.issue_list = listing()
        split.addWidget(self.issue_list)
        self.more = button(row, "展开全部历史", self.expand_history)
        self.expanded = False
        self.history = QPlainTextEdit()
        self.history.setReadOnly(True)
        split.addWidget(self.history)
        split.setSizes([260, 540])
        self.issue_list.currentRowChanged.connect(self.inspect_issue)
        self.search.textChanged.connect(self.populate_issues)
        self.filter.activated.connect(self.populate_issues)
        analytics = self.pane("八期趋势")
        self.topic = QLineEdit()
        self.topic.setPlaceholderText("按学习主题或课程筛选学习天数，例如 CPA，按回车应用")
        analytics.addWidget(self.topic)
        self.topic.returnPressed.connect(lambda: self.section(3))
        self.trend = table(
            ["周期起点", "学习天数", "运动次数", "行动数", "已见触发", "已达成", "部分达成", "待核实"]
        )
        analytics.addWidget(self.trend, 1)
        self.insights = QPlainTextEdit()
        self.insights.setReadOnly(True)
        analytics.addWidget(self.insights, 1)
        self.tabs.currentChanged.connect(self.section)

    def pane(self, name):
        page = QWidget()
        box = QVBoxLayout(page)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(page)
        self.tabs.addTab(scroll, name)
        return box

    def rollover(self):
        now = day()
        if now != self.last_day and self.follow_today:
            self.today()
        self.last_day = now

    def showEvent(self, e):
        super().showEvent(e)
        self.calendar_timer.start()
        if not self.loaded or (self.follow_today and self.last_day != day()):
            self.today()
        else:
            self.reload()
        self.last_day = day()

    def hideEvent(self, e):
        self.calendar_timer.stop()
        self.flush()
        super().hideEvent(e)

    def choose(self, bounds, pid=None):
        self.follow_today = bounds[0] <= day() <= bounds[1]
        self.flush()
        self.bounds = bounds
        self.pid = pid
        self.question = None
        self.reload()

    def today(self):
        target = day()
        existing = next((p for p in self.svc.periods() if p["start"] <= target <= p["end"]), None)
        self.choose(
            (existing["start"], existing["end"]) if existing else self.svc.window(target),
            existing["id"] if existing else None,
        )

    def step(self, n):
        pivot = shifted(self.bounds[1], 1) if n > 0 else shifted(self.bounds[0], -1)
        p = next((r for r in self.svc.periods() if r["start"] <= pivot <= r["end"]), None)
        self.choose(
            (p["start"], p["end"])
            if p
            else ((pivot, shifted(pivot, 6)) if n > 0 else (shifted(pivot, -6), pivot)),
            p["id"] if p else None,
        )

    def pick(self, i):
        choice = self.weeks.itemData(i)
        if choice:
            self.choose((choice["start"], choice["end"]), choice["id"])

    def custom(self):
        self.flush()
        if forms.dates(self):
            p = next(r for r in self.svc.periods() if r["id"] == self.pid)
            self.choose((p["start"], p["end"]), p["id"])

    def settings(self):
        if forms.dates(self, True):
            self.today()

    def transition(self):
        self.flush()
        try:
            if not self.pid:
                self.pid = self.svc.create(*self.bounds)
            elif self.data["status"] == "已完成":
                self.svc.reopen(self.pid)
            else:
                if (
                    QMessageBox.question(
                        self, "完成本期复盘", "保存本期事实快照并发布下周行动？之后仍可重新打开补充。"
                    )
                    != QMessageBox.StandardButton.Yes
                ):
                    return
                self.svc.finish(self.pid)
            self.reload()
        except ValueError as exc:
            self.status.setText(str(exc))

    def changed(self):
        if not self.loading and self.pid and self.question:
            self.unsaved = True
            self.timer.start()

    def flush(self):
        if not self.unsaved:
            return
        self.timer.stop()
        if (
            self.pid
            and self.question
            and not self.loading
            and self.data
            and self.data["status"] != "已完成"
        ):
            self.svc.answer(self.pid, self.question, self.answer.toPlainText())
            self.data["answers"][self.question] = self.answer.toPlainText()
            self.unsaved = False
            self.answer.document().setModified(False)
            self.status.setText("手记草稿已保存")

    def pick_question(self, i):
        self.flush()
        self.question = self.prompts.itemData(i)
        self.loading = True
        self.answer.setPlainText(self.data["answers"].get(self.question, "") if self.data else "")
        self.loading = False

    def reload(self):
        self.flush()
        self.loaded = True
        self.loading = True
        periods = self.svc.periods()
        p = next(
            (r for r in periods if r["id"] == self.pid or (r["start"], r["end"]) == self.bounds), None
        )
        self.pid = p["id"] if p else None
        self.data = self.svc.details(self.pid) if p else None
        self.weeks.clear()
        if not p:
            self.weeks.addItem(" 至 ".join(self.bounds) + " · 未开始", None)
        for r in periods:
            self.weeks.addItem(" 至 ".join((r["start"], r["end"])) + " · " + r["status"], r)
            if p and r["id"] == p["id"]:
                self.weeks.setCurrentIndex(self.weeks.count() - 1)
        self.tabs.setEnabled(True)
        for idx in range(1, 4):
            self.tabs.setTabEnabled(idx, bool(p))
        draft = bool(p and p["status"] != "已完成")
        self.primary.setText("开始本期复盘" if not p else "完成并发布行动" if draft else "重新打开复盘")
        self.cards[0].setText(p["status"] if p else "未开始")
        self.cards[1].setText("—")
        self.cards[2].setText("—")
        for w in (
            self.new_action,
            self.new_issue,
            self.add_note,
            self.update_issue,
            self.answer,
            self.relapse,
        ):
            w.setEnabled(draft)
        self.earlier = self.svc.actions(self.pid, True, self.backlog.isChecked()) if p else []
        self.next_actions = self.svc.actions(self.pid) if p else []
        self.notes.clear()
        self.prompts.clear()
        self.action_list.clear()
        self.answer.clear()
        self.ai.setEnabled(bool(p))
        self.versions.setEnabled(bool(p and p["finished"]))
        if not p:
            self.status.setText("选择本期日期后即可开始；历史周次可从上方切换。")
            self.tabs.setCurrentIndex(0)
            with self.svc.db.connect() as c:
                preview = facts(c, *self.bounds)
            self.show_facts(preview)
            self.wins.setText("本期已记录的事实，开始后可补充经历、解释或修正。")
            cells(self.trend, [])
            self.issue_list.clear()
            self.insights.clear()
            self.question = None
            self.loading = False
            return
        data = self.data
        self.show_facts(data["facts"])
        for entry in data["entries"]:
            body = json.loads(entry["body"])
            item(
                self.notes, entry["kind"] + "  ·  " + (body.get("title") or body.get("detail", "")), body
            )
        if not self.notes.count():
            item(self.notes, "这里可以留下值得肯定的进展、普通经历或对记录的解释。", None)
        for key, name in questions(data, self.earlier):
            self.prompts.addItem(name, key)
        idx = self.prompts.findData(self.question)
        self.prompts.setCurrentIndex(max(0, idx))
        self.question = self.prompts.currentData()
        self.answer.setPlainText(data["answers"].get(self.question, ""))
        done = 0
        for a in self.earlier:
            check = next(
                (
                    x
                    for x in self.svc.checks(a["id"])
                    if x["stage"] == "验收" and x["period"] == self.pid
                ),
                None,
            )
            done += int(bool(check and check["result"] == "已达成"))
            item(
                self.action_list,
                "本期验收  ·  " + a["goal"] + "  ｜  " + (check["result"] if check else "待核对"),
                (a, True),
            )
        for a in self.next_actions:
            item(self.action_list, "下期重点  ·  " + a["goal"], (a, False))
        positives = [json.loads(e["body"])["detail"] for e in data["entries"] if e["kind"] == "有效行为"]
        completed = [r["title"] for r in data["facts"]["tasks"] if r["event"] == "完成"]
        if positives or completed:
            self.wins.setText("值得保留    " + (positives or completed)[0][:120])
        elif data["facts"]["focus"]:
            self.wins.setText("本期投入    " + data["summary"][0][1])
        else:
            self.wins.setText("本期可以只记录一件有价值的经历。")
        self.cards[1].setText(f"{done} / {len(self.earlier)} 项达成")
        issues = self.svc.issues()
        self.cards[2].setText(
            f"{sum(i['state'] == '观察' for i in issues)} 观察 · {sum(e['kind'] == '复发' for e in data['entries'])} 本期复发"
        )
        last = next((r for r in periods if r["start"] < p["start"] and r["finished"]), None)
        gap = (
            (
                date.fromisoformat(day())
                - date.fromisoformat(day(datetime.fromisoformat(last["finished"])))
            ).days
            if last
            else None
        )
        self.status.setText(
            (f"上次复盘距今 {gap} 天  ·  " if gap is not None else "首期复盘  ·  ")
            + f"下期重点 {len(self.next_actions)} / 3"
            + ("  ·  已保存事实快照" if not draft else "  ·  手记自动保存")
        )
        self.loading = False
        self.section(self.tabs.currentIndex())

    def show_facts(self, data):
        self.display_facts = data
        summary = overview(data)
        corrections = data.get("corrections", {})
        cells(
            self.facts, [(k, v + (" · 已附个人校正" if k in corrections else "")) for k, v, _ in summary]
        )
        for i, (_, _, source) in enumerate(summary):
            self.facts.item(i, 1).setToolTip(source)

    def read_facts(self, row, _column):
        from PySide6.QtWidgets import QDialog

        f = self.display_facts
        title, summary, source = overview(f)[row]
        if row in (0, 1):
            details = [
                f"{r['day']}  {r['category']}  {r['seconds'] / 60:.1f} 分钟  {r['label']}"
                for r in f["focus"]
                if row == 0 or r["category"] == "学习"
            ]
            if row == 1:
                details += [r["day"] + "  " + r["rating"] for r in f["reviews"]]
        elif row == 2:
            details = [r["day"] + "  " + r["event"] + "  " + r["title"] for r in f["tasks"]]
        elif row == 3:
            details = [
                f"{r['day']}  睡眠 {r['sleep_hours'] if r['sleep_hours'] is not None else '未记录'} 小时   起床 {r['sleep_end'] or '未记录'}"
                for r in f["life"]
            ]
        elif row == 4:
            details = [f"{r['day']}  {r['kind']}  {r['minutes']:g} 分钟" for r in f["exercise"]] + [
                r["day"] + "  " + r["title"] for r in f["checkins"]
            ]
        elif row == 5:
            details = [
                f"{r['day']}  手机娱乐 {r['phone_fun']:g} 分钟"
                for r in f["life"]
                if r["phone_fun"] is not None
            ]
        else:
            details = [f"{r['title']}  兑换 {r['cost']} 金币" for r in f["buys"]] + [
                f"{r.get('day', '')}  {r['amount']:+d} 金币  {r.get('reason', '')}" for r in f["coins"]
            ]
        dlg = QDialog(self)
        dlg.setWindowTitle(title + " · 本期依据")
        dlg.resize(580, 390)
        box = QVBoxLayout(dlg)
        box.addWidget(text(source, "muted"))
        box.addWidget(text(summary, "cardTitle"))
        correction = f.get("corrections", {}).get(title)
        if correction:
            box.addWidget(text("本人校正    " + correction["note"]))
        body = QPlainTextEdit()
        body.setReadOnly(True)
        body.setPlainText("\n".join(details) or "本期暂无逐条记录。")
        box.addWidget(body)

        def correct():
            from PySide6.QtWidgets import QInputDialog

            value, ok = QInputDialog.getMultiLineText(
                dlg,
                "校正本期解读",
                "填写实际情况及依据；原始记录会保留。",
                (correction or {}).get("note", ""),
            )
            if ok and value.strip():
                self.svc.correct(self.pid, title, value)
                dlg.accept()
                self.reload()

        if self.data and self.data["status"] != "已完成":
            button(box, "补充 / 校正这项事实", correct)
        dlg.exec()

    def read_entry(self, i):
        body = i.data(Qt.ItemDataRole.UserRole)
        if body:
            QMessageBox.information(self, "本周记录", "\n".join(str(v) for v in body.values() if v))

    def section(self, i):
        if not self.data:
            return
        if i == 1:
            idx = next(
                (
                    n
                    for n in range(self.action_list.count())
                    if self.action_list.item(n).data(Qt.ItemDataRole.UserRole)[0]["id"]
                    == self.selected_action
                ),
                0,
            )
            self.action_list.setCurrentRow(idx)
            self.inspect_action()
        elif i == 2:
            self.populate_issues()
        elif i == 3:
            series, notes = trends(self.svc, self.pid, self.topic.text().strip())
            cells(
                self.trend,
                [
                    [
                        r[k] if r[k] is not None else "未记录"
                        for k in (
                            "start",
                            "study",
                            "exercise",
                            "total",
                            "triggered",
                            "done",
                            "partial",
                            "unknown",
                        )
                    ]
                    for r in series
                ],
            )
            self.insights.setPlainText(
                "\n\n".join(notes) or "完成行动验收后，这里会显示哪些触发方式有效、哪些方案值得调整。"
            )

    def inspect_action(self, *_):
        selection = selected(self.action_list)
        draft = bool(self.data and self.data["status"] != "已完成")
        a, incoming = selection or ({}, False)
        for w in (self.record, self.mid, self.accept, self.carry):
            w.setEnabled(bool(selection and incoming and draft))
        active = bool(a and a["start"] <= day() <= a["end"])
        self.edit_action_btn.setEnabled(bool(selection and draft and (not incoming or active)))
        self.drop.setEnabled(bool(selection and not incoming and draft))
        self.launch.setEnabled(
            bool(selection and active and a["metric"] in ("study", "study_days", "work", "task"))
        )
        if not a:
            self.action_detail.setPlainText("先选择一个问题，安排下周的一项小行动。")
            return
        if incoming:
            self.mid.setEnabled(draft and self.bounds[0] <= a["end"])
        self.selected_action = a["id"]
        actual = self.svc.actual(a, self.bounds[1]) if incoming else None
        self.action_detail.setPlainText(
            "\n".join(
                [
                    a["title"] + "  ·  执行期 " + " 至 ".join((a["start"], a["end"])),
                    "目标    " + a["goal"],
                    "触发    " + a["trigger"],
                    "最小动作    " + a["minimum"],
                    "验收    " + a["standard"],
                    "重新开始    " + a["recovery"],
                    (
                        "本期证据    "
                        + ("未记录" if actual is None else f"{actual:g} / {a['target']:g}")
                        + " · "
                        + METRICS[a["metric"]]
                    )
                    if incoming
                    else "发布复盘后生效",
                    *[
                        r["stage"]
                        + " · "
                        + r["result"]
                        + "  "
                        + r["note"]
                        + (" · 继续追踪" if r["tracking"] else " · 停止追踪")
                        for r in self.svc.checks(a["id"])
                    ],
                ]
            )
        )

    def populate_issues(self, *_):
        keep = self.selected_issue
        self.issue_list.clear()
        rs = self.svc.issues(self.search.text(), self.filter.currentData())
        for r in rs:
            item(
                self.issue_list,
                f"{r['state']}  ·  {r['title']}\n{r['domain']}  ·  优先级 {r['priority']}  ·  复发 {r['relapses']} 次",
                r,
            )
        idx = next((i for i, r in enumerate(rs) if r["id"] == keep), 0)
        self.issue_list.setCurrentRow(idx)
        self.inspect_issue()

    def inspect_issue(self, *_):
        r = selected(self.issue_list)
        if not r:
            self.history.setPlainText("新建一个具体问题，或切换状态筛选查看历史记录。")
            return
        self.selected_issue = r["id"]
        hist = self.svc.timeline(r["id"])
        self.more.setVisible(len(hist) > 8)
        self.more.setText("收起历史" if self.expanded else "展开全部历史")
        if not self.expanded:
            hist = hist[:8]
        lines = [
            r["title"] + " · " + r["state"],
            f"首次 {r['first_day']}    最近 {r['last_day']}    影响 {r['impact']}/3",
            r["description"],
            "原因    " + (r["cause"] or "待探索"),
            "证据    " + (r["evidence"] or "待补充"),
            "",
            "历次记录",
        ]
        for e in hist:
            b = json.loads(e["body"])
            after = b.get("after", {})
            info = b.get("result") or b.get("to") or after.get("goal", "")
            lines.append(
                f"{e['start']}  {e['kind']}  {info}  "
                + " ".join(
                    str(x)
                    for x in (
                        b.get("evidence") if isinstance(b.get("evidence"), str) else "",
                        b.get("note"),
                        b.get("detail"),
                        after.get("minimum"),
                        "、".join(b.get("reasons", [])),
                    )
                    if x
                )
            )
        self.history.setPlainText("\n".join(lines))

    def expand_history(self):
        self.expanded = not self.expanded
        self.inspect_issue()

    def snapshots(self):
        if not self.pid:
            return
        with self.svc.db.connect() as c:
            records = c.execute(
                "SELECT created,body FROM weekly_history WHERE period=? AND kind='完成复盘' ORDER BY seq DESC",
                (self.pid,),
            ).fetchall()
        from PySide6.QtWidgets import QDialog

        dlg = QDialog(self)
        dlg.setWindowTitle("历次定稿")
        dlg.resize(600, 410)
        box = QVBoxLayout(dlg)
        versions = QComboBox()
        box.addWidget(versions)
        report = QPlainTextEdit()
        report.setReadOnly(True)
        box.addWidget(report)
        for r in records:
            versions.addItem(
                datetime.fromisoformat(r["created"]).astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                json.loads(r["body"]),
            )

        def show():
            data = versions.currentData() or {}
            report.setPlainText(
                "\\n".join(k + "  ·  " + v for k, v, _ in data.get("facts", []))
                + "\\n\\n"
                + "\\n".join(data.get("answers", {}).values())
                if data
                else "尚未发布复盘。"
            )

        versions.currentIndexChanged.connect(show)
        show()
        dlg.exec()

    def edit_issue(self, mode):
        r = selected(self.issue_list) if mode != "new" else None
        if mode != "new" and not r:
            return
        if forms.issue_editor(self, r, mode == "relapse"):
            self.reload()

    def entry(self):
        if forms.add_entry(self):
            self.reload()

    def edit_action(self, mode):
        a, incoming = selected(self.action_list) or ({}, False)
        if not self.svc.issues():
            if not forms.issue_editor(self):
                return
        if forms.action_editor(
            self,
            a if mode == "edit" else None,
            incoming and mode == "edit",
            a if mode == "carry" else None,
        ):
            self.reload()

    def remove(self):
        a, _ = selected(self.action_list)
        if (
            QMessageBox.question(self, "撤下下期重点", "保留问题及历史，撤下这次尚未发布的安排？")
            == QMessageBox.StandardButton.Yes
        ):
            try:
                self.svc.remove_plan(self.pid, a["id"])
                self.reload()
            except ValueError as exc:
                self.status.setText(str(exc))

    def execution(self):
        a, _ = selected(self.action_list)
        if forms.execution_editor(self, a):
            self.reload()

    def verify(self, stage):
        a, _ = selected(self.action_list)
        if forms.check_editor(self, a, stage):
            self.reload()

    def start_focus(self):
        a, _ = selected(self.action_list)
        role = next(
            (s["role_id"] for s in self.hub.duties.slots() if s["id"] == "director" and s["role_id"]),
            None,
        )
        try:
            category = "学习" if a["metric"] in ("study", "study_days") else "工作"
            run = self.hub.start_focus(
                category,
                a["scope"] if a["scope"] and a["metric"] != "task" else a["minimum"],
                role or "rui",
                duration=self.hub.focus.options()["focus_minutes"] * 60,
                task_id=a["scope"] if a["metric"] == "task" else None,
            )
            self.svc.started(a["id"], run["id"])
            self.hub.navigate.emit("focus")
        except ValueError as exc:
            self.status.setText(str(exc))

    def to_chat(self):
        self.flush()
        window = self.window()
        director = next(
            (s["role_id"] for s in self.hub.duties.slots() if s["id"] == "director" and s["role_id"]),
            None,
        )
        if not director or not hasattr(window, "switch_role"):
            self.status.setText("请先配置总负责人。")
            return
        self.hub.navigate.emit("chat")
        if window.page_stack.currentWidget() != window.chat_page:
            return
        window.switch_role(director)
        content = [
            "请依据本期已记录的事实，帮我找出一个值得继续的行动和一个可以降低的启动门槛。",
            " 至 ".join(self.bounds),
        ]
        content.extend(k + " · " + v for k, v, _ in self.data["summary"])
        content.extend(a["goal"] + " · 最小动作 " + a["minimum"] for a in self.next_actions)
        existing = window.input.toPlainText()
        window.input.setPlainText((existing + "\n\n" if existing else "") + "\n".join(content))
        window.input.setFocus()
