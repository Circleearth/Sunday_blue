"""Short, validated editors for the weekly review notebook."""

import json
from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QWidget,
)
from .module_forms import form_dialog
from ..modules.weekly_review import FIELDS, OUTCOMES, REASONS, STATES
from ..modules.weekly_evidence import METRICS

WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
ACTION_LABELS = ("改进目标", "何时 / 什么事件后", "最小动作", "怎样算真正完成", "遗漏后如何重启")


def combo(items, selected=None):
    widget = QComboBox()
    for key, name in items:
        widget.addItem(name, key)
    if selected is not None:
        widget.setCurrentIndex(max(0, widget.findData(selected)))
    return widget


def choices(items, selected=None):
    return combo([(k, k) for k in items], selected)


def editline(value="", hint=""):
    field = QLineEdit(value or "")
    field.setPlaceholderText(hint)
    return field


def memo(value="", hint=""):
    field = QPlainTextEdit(value or "")
    field.setPlaceholderText(hint)
    field.setMaximumHeight(68)
    return field


def submit(dialog, error, buttons, fn):
    def save():
        try:
            fn()
        except ValueError as exc:
            error.setText(str(exc))
            return
        dialog.accept()

    buttons.accepted.connect(save)
    return dialog.exec() == QDialog.DialogCode.Accepted


def dates(page, settings=False):
    title = "周期与周中检查" if settings else "创建复盘周期"
    dlg, form, error, buttons = form_dialog(page, title)
    opt = page.svc.options()
    if settings:
        first = combo(enumerate(WEEKDAYS), opt["first"])
        check = combo(enumerate(WEEKDAYS), opt["check"])
        form.addRow("每周起点", first)
        form.addRow("周中检查日", check)
        form.addRow(QLabel("新周期使用新的周起点，历史周期保留。"))
        return submit(
            dlg, error, buttons, lambda: page.svc.configure(first.currentData(), check.currentData())
        )
    start, end = page.bounds
    inputs = []
    for name, value in [("首日", start), ("末日（包含）", end)]:
        field = QDateEdit(QDate.fromString(value, "yyyy-MM-dd"))
        field.setCalendarPopup(True)
        field.setDisplayFormat("yyyy-MM-dd")
        form.addRow(name, field)
        inputs.append(field)

    def save():
        page.pid = page.svc.create(*(w.date().toString("yyyy-MM-dd") for w in inputs))

    return submit(dlg, error, buttons, save)


def issue_editor(page, record=None, relapse=False):
    r = record or {}
    dlg, form, error, buttons = form_dialog(page, "问题记录")
    title = editline(r.get("title"), "例如：学习结束后忘记归档错题")
    domain = choices(["学习", "工作", "作息", "运动", "生活", "其他"], r.get("domain", "生活"))
    domain.setEditable(True)
    state = choices(STATES, "复发" if relapse else r.get("state", "活跃"))
    priority = combo([(1, "低"), (2, "中"), (3, "高")], r.get("priority", 2))
    impact = combo([(1, "局部"), (2, "明显"), (3, "持续影响多个领域")], r.get("impact", 2))
    description = memo(r.get("description"), "发生了什么？")
    cause = memo(r.get("cause"), "哪些是观察，哪些还只是推测？")
    evidence = memo("" if r else r.get("evidence"), "记录、日期或这次状态变化的依据")
    for name, field in [
        ("名称", title),
        ("领域", domain),
        ("状态", state),
        ("优先级", priority),
        ("影响", impact),
        ("相关事实", description),
        ("原因分析", cause),
        ("本次证据", evidence),
    ]:
        form.addRow(name, field)

    def save():
        if r and state.currentData() != r["state"] and not evidence.toPlainText().strip():
            raise ValueError("请填写本次状态变化的依据。")
        page.selected_issue = page.svc.issue(
            page.pid,
            title.text(),
            domain.currentText(),
            state.currentData(),
            priority.currentData(),
            impact.currentData(),
            description.toPlainText(),
            cause.toPlainText(),
            evidence.toPlainText() or r.get("evidence", ""),
            r.get("id"),
        )

    return submit(dlg, error, buttons, save)


def add_entry(page):
    dlg, form, error, b = form_dialog(page, "补充这周的一件事")
    kind = choices(("经历", "有效行为", "修正说明", "补充证据"))
    issue = combo([("", "不关联问题")] + [(r["id"], r["title"]) for r in page.svc.issues()])
    body = memo(hint="保留事实、个人感受，或写明哪条数据需要怎样理解。")
    form.addRow("记录为", kind)
    form.addRow("相关问题", issue)
    form.addRow("内容", body)
    return submit(
        dlg,
        error,
        b,
        lambda: page.svc.entry(
            page.pid, kind.currentData(), body.toPlainText(), issue.currentData() or None
        ),
    )


def action_editor(page, record=None, midweek=False, carry=None):
    r = record or carry or {}
    dlg, form, error, b = form_dialog(page, "周中调整行动" if midweek else "下周行动")
    issues = page.svc.issues()
    issue = combo([(i["id"], i["title"]) for i in issues], r.get("issue") or page.selected_issue)
    issue.setEnabled(not record)
    fields = [
        editline(r.get(k), hint)
        for k, hint in zip(
            FIELDS,
            [
                "提高错题复习质量",
                "学习专注结束",
                "记录一道没弄懂的题",
                "留下至少一条可复习记录",
                "下次学习前先补一条",
            ],
        )
    ]
    form.addRow("持续追踪的问题", issue)
    for label, w in zip(ACTION_LABELS, fields):
        form.addRow(label, w)
    trigger = choices(("自定义", "学习专注结束", "工作专注结束"), r.get("trigger_kind"))
    key = combo(METRICS.items(), r.get("metric"))
    scope = editline(r.get("scope"), "可选：记录标题、运动类型或打卡名称")
    tasks = combo(
        [("", "请选择任务")] + [(t["id"], t["title"]) for t in page.hub.work.tasks()], r.get("scope")
    )
    if r.get("metric") == "task" and tasks.findData(r["scope"]) < 0:
        tasks.addItem("历史关联任务", r["scope"])
        tasks.setCurrentIndex(tasks.count() - 1)
    target = QDoubleSpinBox()
    target.setRange(0.1, 100000)
    target.setValue(r.get("target", 1))
    for name, w in [
        ("自动触发提醒", trigger),
        ("验收数据源", key),
        ("限定范围", scope),
        ("关联工作任务", tasks),
        ("目标量", target),
    ]:
        form.addRow(name, w)

    def sync():
        metric = key.currentData()
        form.setRowVisible(tasks, metric == "task")
        form.setRowVisible(scope, metric not in ("task", "manual", "reviews"))
        form.setRowVisible(target, metric != "task")

    key.currentIndexChanged.connect(sync)
    sync()

    def save():
        if not issue.currentData():
            raise ValueError("请先在问题库建立要跟踪的问题。")
        vals = dict(zip(FIELDS, [w.text() for w in fields]))
        vals.update(
            trigger_kind=trigger.currentData(),
            metric=key.currentData(),
            target=1 if key.currentData() == "task" else target.value(),
            scope=tasks.currentData()
            if key.currentData() == "task"
            else scope.text()
            if scope.isVisible()
            else "",
        )
        page.selected_action = page.svc.plan(
            record["period"] if record else page.pid,
            issue.currentData(),
            vals,
            record["id"] if record else None,
            midweek,
        )

    return submit(dlg, error, b, save)


def check_editor(page, a, stage):
    dlg, form, error, b = form_dialog(page, stage + " · " + a["goal"])
    prior = next(
        (x for x in page.svc.checks(a["id"]) if x["period"] == page.pid and x["stage"] == stage), {}
    )
    actual = page.svc.actual(a, page.bounds[1])
    label = QLabel(
        a["standard"]
        + "\n"
        + (
            "尚无匹配记录"
            if actual is None
            else f"实际 {actual:g} / 目标 {a['target']:g} · {METRICS[a['metric']]}"
        )
    )
    label.setWordWrap(True)
    form.addRow("证据", label)
    result = choices(OUTCOMES, prior.get("result", "待核实"))
    form.addRow("这次结果", result)
    panel = QWidget()
    layout = QFormLayout(panel)
    boxes = []
    for i in range(0, len(REASONS), 2):
        pair = [QCheckBox(x) for x in REASONS[i : i + 2]]
        for cb in pair:
            cb.setChecked(cb.text() in json.loads(prior.get("reasons", "[]")))
        layout.addRow(*pair)
        boxes.extend(pair)
    form.addRow("偏离原因（可多选）", panel)
    note = memo(prior.get("note"), "实际做到了什么？下次从哪里重新开始？")
    track = QCheckBox("下周期继续追踪")
    track.setChecked(bool(prior.get("tracking", 1)))
    form.addRow("个人核对", note)
    form.addRow(track)
    return submit(
        dlg,
        error,
        b,
        lambda: page.svc.check(
            page.pid,
            a["id"],
            stage,
            result.currentData(),
            [cb.text() for cb in boxes if cb.isChecked()],
            note.toPlainText(),
            track.isChecked(),
        ),
    )


def execution_editor(page, a):
    from ..modules.database import day

    dlg, form, error, b = form_dialog(page, "记录已做的动作")
    observed = QDateEdit()
    observed.setCalendarPopup(True)
    observed.setDisplayFormat("yyyy-MM-dd")
    start = QDate.fromString(a["start"], "yyyy-MM-dd")
    end = QDate.fromString(min(a["end"], day()), "yyyy-MM-dd")
    observed.setDateRange(start, end)
    observed.setDate(end)
    note = memo(hint="例如：回忆了一道错题，并写下了关键步骤。")
    form.addRow("实际执行日期", observed)
    form.addRow("做了什么", note)
    return submit(
        dlg,
        error,
        b,
        lambda: page.svc.record_execution(
            page.pid, a["id"], observed.date().toString("yyyy-MM-dd"), note.toPlainText()
        ),
    )
