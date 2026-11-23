"""Describe measured outcomes separately from missing evidence or unverified plans."""

import json
from collections import Counter, defaultdict
from datetime import datetime

from .weekly_evidence import facts, metric


def trends(service, pid, topic=""):
    with service.db.connect() as c:
        current = c.execute("SELECT start,end FROM weekly_periods WHERE id=?", (pid,)).fetchone()
        periods = c.execute(
            "SELECT * FROM weekly_periods WHERE start<=? ORDER BY start DESC LIMIT 8",
            (current["start"],),
        ).fetchall()
        result = []
        strategies = defaultdict(Counter)
        runs = defaultdict(list)
        pauses = []
        for p in reversed(periods):
            f = json.loads(p["snapshot"]) if p["snapshot"] else facts(c, p["start"], p["end"])
            plans = c.execute(
                """SELECT a.*,k.result,k.reasons,k.note,k.created AS checked,i.title,
                EXISTS(SELECT 1 FROM weekly_triggers t WHERE t.action=a.id AND t.day<=?) AS triggered
                FROM weekly_actions a JOIN weekly_issues i ON i.id=a.issue
                LEFT JOIN weekly_checks k ON k.id=(SELECT v.id FROM weekly_checks v JOIN weekly_periods w ON v.period=w.id
                WHERE v.action=a.id AND v.stage='验收' AND w.start<=? ORDER BY w.start DESC,v.rowid DESC LIMIT 1) WHERE a.period=?""",
                (current["end"], current["start"], p["id"]),
            ).fetchall()
            counts = Counter()
            for a in plans:
                status = a["result"] or "待核实"
                counts[status] += 1
                counts["triggered"] += int(a["triggered"])
                strategies[a["trigger_kind"]][status] += 1
                runs[a["issue"]].append(dict(a))
                gap = None
                for entry in c.execute(
                    """SELECT h.body,h.created FROM weekly_history h JOIN weekly_periods w ON h.period=w.id
                    WHERE h.action=? AND h.kind IN ('验收','周中') AND w.start<=? ORDER BY h.seq""",
                    (a["id"], current["start"]),
                ):
                    obs = json.loads(entry["body"])["result"]
                    when = datetime.fromisoformat(entry["created"])
                    if obs == "未达成" and gap is None:
                        gap = when
                    if obs in ("部分达成", "已达成") and gap:
                        pauses.append((when - gap).total_seconds() / 86400)
                        gap = None
            result.append(
                dict(
                    start=p["start"],
                    study=metric(f, "study_days", topic),
                    exercise=metric(f, "exercise"),
                    total=len(plans),
                    triggered=counts["triggered"],
                    done=counts["已达成"],
                    partial=counts["部分达成"],
                    unknown=counts["待核实"],
                )
            )
    notes = []
    for series in runs.values():
        tail = series[-3:]
        if len(tail) == 3 and all(a["result"] == "未达成" for a in tail):
            same = len({(a["minimum"], a["trigger"]) for a in tail}) == 1
            reasons = Counter(r for a in tail for r in json.loads(a["reasons"] or "[]"))
            reason = reasons.most_common(1)[0][0] if reasons else "原因待核对"
            notes.append(
                f"「{tail[-1]['title']}」最近三次验收均未达成（{reason}）。"
                + (
                    "最小动作与触发条件一直相同，建议先换一种启动方式。"
                    if same
                    else "方案已经调整过，可比较哪一步最难开始。"
                )
            )
        elif len(tail) >= 2 and all(a["result"] == "已达成" for a in tail):
            notes.append(f"「{tail[-1]['title']}」连续 {len(tail)} 次验收达成，可以考虑转入观察。")
    if pauses:
        notes.append(
            f"从明确记录未达成到再次有进展，平均间隔 {sum(pauses) / len(pauses):.1f} 天（{len(pauses)} 次有前后记录）。"
        )
    for mode, cnt in strategies.items():
        verified = sum(cnt.values()) - cnt["待核实"]
        if verified:
            notes.append(
                f"{mode} · 已验收 {verified} 项，其中 {cnt['已达成']} 项达成、{cnt['部分达成']} 项有部分进展。"
            )
    return result, notes


def questions(summary, prior):
    questions = []
    if prior:
        questions.append(("barrier", "上一期哪些行动最难开始？触发条件、精力或环境有什么变化？"))
    if summary["facts"]["focus"] or summary["facts"]["tasks"]:
        questions.append(("yield", "哪些投入带来了值得保留的具体成果？"))
    if any(r["phone_fun"] is not None for r in summary["facts"]["life"]):
        questions.append(("boundary", "娱乐安排和自己认可的时间边界相符吗？"))
    questions += [
        ("restart", "什么时候察觉了偏离？什么帮助你重新开始？"),
        ("next", "下次状态不好时，什么最小动作仍然做得到？"),
    ]
    return questions
