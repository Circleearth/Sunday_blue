"""Read-only, inclusive living-day evidence from the modules that own each fact."""

import json
from datetime import date, timedelta

METRICS = {
    "manual": "本人记录的执行次数",
    "study": "学习分钟",
    "study_days": "有学习记录的天数",
    "work": "工作分钟",
    "exercise": "运动次数",
    "exercise_minutes": "运动分钟",
    "checkins": "打卡次数",
    "reviews": "知识复习次数",
    "task": "指定工作任务完成",
}


def rows(c, sql, args):
    return [dict(r) for r in c.execute(sql, args)]


def facts(c, start, end):
    span = (start, end)
    focus = rows(
        c,
        """SELECT a.id,a.day,a.category,a.label,a.seconds,coalesce(course.title,'') AS course
        FROM activity_by_day a LEFT JOIN learning_focus_links l ON l.run_id=a.id
        LEFT JOIN learning_nodes u ON u.id=l.unit LEFT JOIN learning_nodes ch ON ch.id=u.parent
        LEFT JOIN learning_nodes course ON course.id=ch.parent WHERE a.day BETWEEN ? AND ? ORDER BY a.day""",
        span,
    )
    tasks = rows(
        c,
        """SELECT h.task_id,t.title,h.kind,h.payload,date(h.created,'+4 hours') AS day
        FROM work_history h JOIN work_tasks t ON t.id=h.task_id
        WHERE date(h.created,'+4 hours') BETWEEN ? AND ? ORDER BY h.created,h.rowid""",
        span,
    )
    events = []
    for task in tasks:
        payload = json.loads(task.pop("payload"))
        before = payload.get("before", {})
        after = payload.get("after", {})
        kind = task["kind"]
        if kind == "created":
            events.append(dict(task, event="新建"))
        if after.get("status") == "done":
            events.append(dict(task, event="完成"))
        if before.get("due") and after.get("due", "") > before["due"]:
            events.append(dict(task, event="延期"))
    life = rows(
        c,
        """SELECT l.day,l.sleep_hours,d.sleep_end,l.energy,l.phone_total,l.phone_fun
        FROM daily_life l LEFT JOIN daily_life_details d ON l.day=d.day WHERE l.day BETWEEN ? AND ? ORDER BY l.day""",
        span,
    )
    sessions = c.execute(
        """SELECT count(*) FROM activity_records WHERE day BETWEEN ? AND ?
        AND id NOT LIKE 'manual:%'""",
        span,
    ).fetchone()[0]
    exercise = rows(
        c,
        "SELECT id,day,kind,minutes FROM exercise_records WHERE day BETWEEN ? AND ? ORDER BY day",
        span,
    )
    checkins = rows(
        c,
        "SELECT h.day,c.title FROM checkin_history h JOIN checkins c ON c.id=h.checkin_id WHERE day BETWEEN ? AND ?",
        span,
    )
    reviews = rows(c, "SELECT day, rating FROM review_attempts WHERE day BETWEEN ? AND ?", span)
    coins = rows(
        c,
        "SELECT amount,reason,date(created,'+4 hours') AS day FROM coin_ledger WHERE date(created,'+4 hours') BETWEEN ? AND ?",
        span,
    )
    buys = rows(
        c, "SELECT title,cost FROM redemptions WHERE date(created,'+4 hours') BETWEEN ? AND ?", span
    )
    leisure = c.execute(
        """SELECT sum(d.effective)/60 FROM life_timer_days d JOIN life_timers t ON d.run_id=t.id
        WHERE d.day BETWEEN ? AND ? AND t.finished IS NOT NULL AND (t.title LIKE '%娱乐%' OR t.title LIKE '%游戏%')""",
        span,
    ).fetchone()[0]
    return dict(
        focus=focus,
        tasks=events,
        life=life,
        sessions=sessions,
        exercise=exercise,
        checkins=checkins,
        reviews=reviews,
        coins=coins,
        buys=buys,
        leisure=leisure,
    )


def metric(data, key, scope=""):
    if key == "manual":
        return None
    if key in ("study", "work", "study_days"):
        subset = [
            r
            for r in data["focus"]
            if r["category"] == ("工作" if key == "work" else "学习")
            and scope.casefold() in (r["label"] + " " + r.get("course", "")).casefold()
        ]
        if not subset:
            return None
        return (
            len({r["day"] for r in subset})
            if key == "study_days"
            else round(sum(r["seconds"] for r in subset) / 60, 1)
        )
    if key == "task":
        return 1 if any(r["task_id"] == scope and r["event"] == "完成" for r in data["tasks"]) else None
    if key.startswith("exercise"):
        subset = [r for r in data["exercise"] if scope.casefold() in r["kind"].casefold()]
        if not subset:
            return None
        return len(subset) if key == "exercise" else sum(r["minutes"] for r in subset)
    if key == "checkins":
        return sum(scope.casefold() in r["title"].casefold() for r in data[key]) or None
    return len(data["reviews"]) or None


def overview(data):
    def fmt(value, unit=""):
        return "未记录" if value is None else f"{value:g}{unit}"

    def avg(key):
        values = [r[key] for r in data["life"] if r[key] is not None]
        return sum(values) / len(values) if values else None

    days = sorted({r["day"] for r in data["focus"] if r["category"] == "学习"})
    streak = best = 0
    prev = None
    for d in map(date.fromisoformat, days):
        streak = streak + 1 if prev and d - prev == timedelta(days=1) else 1
        best = max(best, streak)
        prev = d
    events = data["tasks"]
    wakes = [r["sleep_end"] for r in data["life"] if r["sleep_end"]]
    earned = sum(r["amount"] for r in data["coins"] if r["amount"] > 0) if data["coins"] else None
    return [
        (
            "专注",
            "有效计时 "
            + fmt(data["sessions"] or None, " 次")
            + " · 学习 "
            + fmt(metric(data, "study"), " 分钟")
            + " · 工作 "
            + fmt(metric(data, "work"), " 分钟"),
            "番茄钟与补报 · 跨日分钟按生活日拆分，次数归结算日",
        ),
        (
            "学习节奏",
            "最长连续 "
            + fmt(best or None, " 天")
            + " · 知识复习 "
            + fmt(metric(data, "reviews"), " 次"),
            "学习计时、知识复习回执",
        ),
        (
            "工作进展",
            " · ".join(
                k + " " + fmt(len({r["task_id"] for r in events if r["event"] == k}) if events else None)
                for k in ("新建", "完成", "延期")
            ),
            "任务历史 · 延期按明确推迟截止日期计",
        ),
        (
            "作息与精力",
            "平均睡眠 "
            + fmt(round(avg("sleep_hours"), 1) if avg("sleep_hours") is not None else None, " 小时")
            + " · 最近起床 "
            + (wakes[-1] if wakes else "未记录")
            + " · 平均自报精力 "
            + fmt(avg("energy")),
            "生活上报 · 均值仅含实际填写日",
        ),
        (
            "运动与打卡",
            "运动 "
            + fmt(metric(data, "exercise"), " 次")
            + " / "
            + fmt(metric(data, "exercise_minutes"), " 分钟")
            + " · 打卡 "
            + fmt(metric(data, "checkins"), " 次"),
            "运动上报、本地打卡",
        ),
        (
            "娱乐时间",
            "手机日均 "
            + fmt(avg("phone_fun"), " 分钟")
            + " · 已标记娱乐计时 "
            + fmt(data["leisure"], " 分钟"),
            "手机上报、标题含娱乐或游戏的生活计时",
        ),
        (
            "金币与兑换",
            "入账 "
            + fmt(earned, " 金币")
            + " · 兑换 "
            + fmt(len(data["buys"]) if data["buys"] else None, " 次"),
            "金币流水、商城回执 · 按实际发生日期统计",
        ),
    ]
