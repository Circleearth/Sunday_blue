"""Weekly reviews, durable issues and evidence-backed action verification."""

import json
import math
import unicodedata
import uuid
from datetime import date, timedelta

from .database import day, stamp
from .review_plan import ReviewPlan
from .weekly_evidence import METRICS, facts, metric, overview, rows

STATES = ("活跃", "观察", "归档", "复发")
OUTCOMES = ("已达成", "部分达成", "未达成", "待核实")
REASONS = (
    "忘记执行",
    "缺少开始时间",
    "启动成本高",
    "超出当前精力",
    "被其他事务挤占",
    "提醒失效",
    "临时因素",
    "其他",
)
KINDS = ("经历", "有效行为", "新问题", "补充证据", "复发", "修正说明")
FIELDS = ("goal", "trigger", "minimum", "standard", "recovery")


def shifted(d, n):
    return (date.fromisoformat(d) + timedelta(days=n)).isoformat()


def keyname(text):
    return "".join(unicodedata.normalize("NFKC", text).casefold().split())


def uid():
    return uuid.uuid4().hex


def one(c, table, identifier):
    row = c.execute(f"SELECT * FROM {table} WHERE id=?", (identifier,)).fetchone()
    if not row:
        raise ValueError("这条记录不存在，请重新选择。")
    return dict(row)


def event(c, period, issue, action, kind, body):
    c.execute(
        "INSERT INTO weekly_history(period,issue,action,kind,body,created) VALUES(?,?,?,?,?,?)",
        (period, issue, action, kind, json.dumps(body, ensure_ascii=False), stamp()),
    )


class WeeklyReview:
    def __init__(self, db):
        self.db = db
        ReviewPlan(db)
        with db.connect() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS weekly_periods(id TEXT PRIMARY KEY,start TEXT UNIQUE,end TEXT,
                status TEXT NOT NULL DEFAULT '进行中',finished TEXT,snapshot TEXT);
            CREATE TABLE IF NOT EXISTS weekly_issues(id TEXT PRIMARY KEY,title TEXT,domain TEXT,canonical TEXT UNIQUE,
                state TEXT,priority INTEGER,impact INTEGER,description TEXT,cause TEXT,evidence TEXT,
                first_day TEXT,last_day TEXT,relapses INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS weekly_history(seq INTEGER PRIMARY KEY,period TEXT,issue TEXT,
                action TEXT,kind TEXT,body TEXT,created TEXT);
            CREATE INDEX IF NOT EXISTS weekly_issue_timeline ON weekly_history(issue,seq);
            CREATE TABLE IF NOT EXISTS weekly_answers(period TEXT,prompt TEXT,answer TEXT,PRIMARY KEY(period,prompt));
            CREATE TABLE IF NOT EXISTS weekly_actions(id TEXT PRIMARY KEY,period TEXT,issue TEXT,goal TEXT,
                trigger TEXT,minimum TEXT,standard TEXT,recovery TEXT,metric TEXT,scope TEXT,target REAL,
                start TEXT,end TEXT,trigger_kind TEXT, UNIQUE(period,issue));
            CREATE TABLE IF NOT EXISTS weekly_triggers(action TEXT,source TEXT,day TEXT,created TEXT,
                PRIMARY KEY(action,source));
            CREATE TABLE IF NOT EXISTS weekly_checks(id TEXT PRIMARY KEY,action TEXT,period TEXT,stage TEXT,
                result TEXT,reasons TEXT,note TEXT,tracking INTEGER,evidence TEXT,created TEXT,
                UNIQUE(action,period,stage));
            """)

    def options(self):
        return self.db.get("weekly_settings", {"first": 0, "check": 2})

    def configure(self, first, check):
        if first not in range(7) or check not in range(7):
            raise ValueError("无效的星期")
        self.db.set("weekly_settings", {"first": first, "check": check})

    def window(self, today=None):
        d = date.fromisoformat(today or day())
        start = d - timedelta(days=(d.weekday() - self.options()["first"]) % 7)
        return start.isoformat(), (start + timedelta(days=6)).isoformat()

    def periods(self):
        with self.db.connect() as c:
            return rows(
                c, "SELECT id,start,end,status,finished FROM weekly_periods ORDER BY start DESC", ()
            )

    def create(self, start, end):
        length = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
        if not 1 <= length <= 31:
            raise ValueError("周期可选 1 至 31 天")
        with self.db.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            existing = c.execute(
                "SELECT * FROM weekly_periods WHERE start<=? AND end>=?", (end, start)
            ).fetchone()
            if existing:
                if (existing["start"], existing["end"]) == (start, end):
                    return existing["id"]
                raise ValueError(
                    f"与 {existing['start']} 至 {existing['end']} 重合，请打开原周期或调整日期。"
                )
            pid = uid()
            c.execute("INSERT INTO weekly_periods(id,start,end) VALUES(?,?,?)", (pid, start, end))
            return pid

    def details(self, pid):
        with self.db.connect() as c:
            p = one(c, "weekly_periods", pid)
            p["answers"] = dict(
                c.execute("SELECT prompt,answer FROM weekly_answers WHERE period=?", (pid,))
            )
            p["facts"] = json.loads(p["snapshot"]) if p["snapshot"] else self._facts(c, p)
            p["summary"] = overview(p["facts"])
            p["entries"] = rows(
                c,
                "SELECT * FROM weekly_history WHERE period=? AND kind IN ('经历','有效行为','新问题','补充证据','复发','修正说明') ORDER BY seq DESC",
                (pid,),
            )
            return p

    @staticmethod
    def _facts(c, p):
        data = facts(c, p["start"], p["end"])
        corrections = {}
        for r in c.execute(
            "SELECT body,created FROM weekly_history WHERE period=? AND kind='修正说明' ORDER BY seq",
            (p["id"],),
        ):
            b = json.loads(r["body"])
            if b.get("field"):
                corrections[b["field"]] = {"note": b["detail"], "at": r["created"]}
        data["corrections"] = corrections
        return data

    def correct(self, pid, field, note):
        if not note.strip():
            raise ValueError("请填写更正内容和依据。")
        with self.db.connect() as c:
            p = self._draft(c, pid)
            evidence = {key: value for key, value, _ in overview(facts(c, p["start"], p["end"]))}
            if field not in evidence:
                raise ValueError("未知的汇总领域。")
            event(
                c,
                pid,
                None,
                None,
                "修正说明",
                {
                    "field": field,
                    "original": evidence[field],
                    "detail": note.strip(),
                    "source": "本人核对",
                },
            )

    def answer(self, pid, prompt, answer):
        with self.db.connect() as c:
            self._draft(c, pid)
            c.execute(
                "INSERT INTO weekly_answers VALUES(?,?,?) ON CONFLICT(period,prompt) DO UPDATE SET answer=excluded.answer",
                (pid, prompt, answer),
            )

    @staticmethod
    def _draft(c, pid):
        p = one(c, "weekly_periods", pid)
        if p["status"] == "已完成":
            raise ValueError("请先重新打开这份复盘再编辑。")
        return p

    def finish(self, pid):
        with self.db.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            p = one(c, "weekly_periods", pid)
            if p["status"] == "已完成":
                return
            if p["start"] > day():
                raise ValueError("未来的周期可以准备草稿，开始后才能完成复盘。")
            snapshot = self._facts(c, p)
            c.execute(
                "UPDATE weekly_periods SET status='已完成',finished=?,snapshot=? WHERE id=?",
                (stamp(), json.dumps(snapshot, ensure_ascii=False), pid),
            )
            event(
                c,
                pid,
                None,
                None,
                "完成复盘",
                {
                    "facts": overview(snapshot),
                    "snapshot": snapshot,
                    "answers": dict(
                        c.execute("SELECT prompt,answer FROM weekly_answers WHERE period=?", (pid,))
                    ),
                },
            )

    def reopen(self, pid):
        with self.db.connect() as c:
            p = one(c, "weekly_periods", pid)
            if p["status"] == "已完成":
                c.execute("UPDATE weekly_periods SET status='进行中',snapshot=NULL WHERE id=?", (pid,))
                event(c, pid, None, None, "重新打开", {"finished": p["finished"]})

    def issues(self, search="", state=""):
        with self.db.connect() as c:
            data = rows(c, "SELECT * FROM weekly_issues ORDER BY priority DESC,last_day DESC,title", ())
        return [
            r
            for r in data
            if (not state or r["state"] == state or (state == "在跟踪" and r["state"] != "归档"))
            and keyname(search)
            in keyname(r["domain"] + r["title"] + r["description"] + r["evidence"] + r["cause"])
        ]

    def issue(
        self,
        pid,
        title,
        domain="生活",
        state="活跃",
        priority=2,
        impact=2,
        description="",
        cause="",
        evidence="",
        identifier=None,
    ):
        title, domain = title.strip(), domain.strip()
        if (
            not title
            or not domain
            or state not in STATES
            or priority not in range(1, 4)
            or impact not in range(1, 4)
        ):
            raise ValueError("请填写名称、领域及有效的状态与优先级。")
        canonical = keyname(domain) + "/" + keyname(title)
        with self.db.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            p = self._draft(c, pid)
            observed = min(p["end"], max(day(), p["start"]))
            match = c.execute("SELECT id FROM weekly_issues WHERE canonical=?", (canonical,)).fetchone()
            if match and match[0] != identifier:
                raise ValueError("同领域已有同名问题。请在问题库选择原记录，补充证据或标记复发。")
            old = one(c, "weekly_issues", identifier) if identifier else None
            if old and old["state"] in ("观察", "归档") and state == "活跃":
                state = "复发"
            if state == "复发" and (not old or old["state"] not in ("观察", "归档", "复发")):
                raise ValueError("观察或归档的问题再次出现时才能标记复发。")
            if old and old["state"] != state and not evidence.strip():
                raise ValueError("请填写状态变化的依据。")
            if old and observed < old["last_day"] and old["state"] != state:
                raise ValueError("较早周期可补充历史证据。请在最近周期变更当前状态。")
            identifier = identifier or uid()
            relapse = int(bool(old and state == "复发" and old["state"] != state))
            last = (
                max(observed, old["last_day"])
                if old and state in ("活跃", "复发")
                else old["last_day"]
                if old
                else observed
            )
            first = min(observed, old["first_day"]) if old else observed
            c.execute(
                """INSERT INTO weekly_issues VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                title=excluded.title,domain=excluded.domain,canonical=excluded.canonical,state=excluded.state,
                priority=excluded.priority,impact=excluded.impact,description=excluded.description,cause=excluded.cause,
                evidence=excluded.evidence,first_day=excluded.first_day,last_day=excluded.last_day,relapses=excluded.relapses""",
                (
                    identifier,
                    title,
                    domain,
                    canonical,
                    state,
                    priority,
                    impact,
                    description,
                    cause,
                    evidence,
                    first,
                    last,
                    (old["relapses"] if old else 0) + relapse,
                ),
            )
            kind = "新问题" if not old else "复发" if relapse else "补充证据"
            event(
                c,
                pid,
                identifier,
                None,
                kind,
                {
                    "title": title,
                    "from": old["state"] if old else "",
                    "to": state,
                    "detail": description,
                    "cause": cause,
                    "evidence": evidence,
                },
            )
            return identifier

    def entry(self, pid, kind, text, issue=None):
        if kind not in ("有效行为", "经历", "补充证据", "修正说明") or not text.strip():
            raise ValueError("请选择记录类别并填写内容。")
        with self.db.connect() as c:
            p = self._draft(c, pid)
            if issue:
                one(c, "weekly_issues", issue)
                if kind == "补充证据":
                    c.execute(
                        "UPDATE weekly_issues SET last_day=max(last_day,?),first_day=min(first_day,?) WHERE id=?",
                        (min(day(), p["end"]), min(day(), p["end"]), issue),
                    )
            event(c, pid, issue, None, kind, {"detail": text.strip(), "source": "本人补充"})

    def timeline(self, issue):
        with self.db.connect() as c:
            return rows(
                c,
                "SELECT h.*,p.start FROM weekly_history h JOIN weekly_periods p ON p.id=h.period WHERE issue=? ORDER BY h.seq DESC",
                (issue,),
            )

    def plan(self, pid, issue, values, identifier=None, midweek=False):
        fields = [str(values.get(k, "")).strip() for k in FIELDS]
        if not all(fields):
            raise ValueError("请补齐目标、触发条件、最小动作、验收标准和重启办法。")
        key = values.get("metric", "manual")
        scope = values.get("scope", "").strip()
        target = float(values.get("target", 1))
        trigger = values.get("trigger_kind", "自定义")
        if (
            key not in METRICS
            or target <= 0
            or not math.isfinite(target)
            or trigger not in ("自定义", "学习专注结束", "工作专注结束")
        ):
            raise ValueError("无效的指标、目标量或触发方式。")
        with self.db.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            p = one(c, "weekly_periods", pid)
            one(c, "weekly_issues", issue)
            old = one(c, "weekly_actions", identifier) if identifier else None
            if old and (old["issue"] != issue or old["period"] != pid):
                raise ValueError("行动归属不一致")
            if midweek:
                if not old or not old["start"] <= day() <= old["end"]:
                    raise ValueError("只能调整当前执行周期的行动。")
            else:
                self._draft(c, pid)
            if key == "task":
                one(c, "work_tasks", scope)
            if not old:
                if (
                    c.execute("SELECT count(*) FROM weekly_actions WHERE period=?", (pid,)).fetchone()[0]
                    >= 3
                ):
                    raise ValueError("每期最多三项重点，可以先把其他问题留在问题库。")
                if c.execute(
                    "SELECT 1 FROM weekly_actions WHERE period=? AND issue=?", (pid, issue)
                ).fetchone():
                    raise ValueError("本期已有该问题的行动，请编辑原行动。")
            identifier = identifier or uid()
            begin, end = shifted(p["end"], 1), shifted(p["end"], 7)
            if c.execute(
                "SELECT 1 FROM weekly_actions WHERE issue=? AND period<>? AND start<=? AND end>=?",
                (issue, pid, end, begin),
            ).fetchone():
                raise ValueError("该问题已有覆盖这些执行日的行动，请调整原行动或选择下一周期。")
            c.execute(
                """INSERT INTO weekly_actions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET goal=excluded.goal,trigger=excluded.trigger,minimum=excluded.minimum,
                standard=excluded.standard,recovery=excluded.recovery,metric=excluded.metric,scope=excluded.scope,
                target=excluded.target,trigger_kind=excluded.trigger_kind""",
                (identifier, pid, issue, *fields, key, scope, target, begin, end, trigger),
            )
            event(
                c,
                pid,
                issue,
                identifier,
                "调整行动" if old else "安排重点",
                {
                    "before": old,
                    "after": dict(zip(FIELDS, fields))
                    | {"metric": key, "target": target, "scope": scope, "trigger_kind": trigger},
                },
            )
            return identifier

    def remove_plan(self, pid, aid):
        with self.db.connect() as c:
            self._draft(c, pid)
            a = one(c, "weekly_actions", aid)
            if (
                a["period"] != pid
                or c.execute("SELECT 1 FROM weekly_checks WHERE action=?", (aid,)).fetchone()
            ):
                raise ValueError("已执行的行动保留在历史中。")
            if c.execute(
                "SELECT 1 FROM weekly_history WHERE period=? AND kind='完成复盘'", (pid,)
            ).fetchone():
                raise ValueError("已发布过的行动可调整，不能移除。")
            c.execute("DELETE FROM weekly_actions WHERE id=?", (aid,))
            event(c, pid, a["issue"], aid, "撤下重点", a)

    def actions(self, pid, incoming=False, backlog=False):
        with self.db.connect() as c:
            p = one(c, "weekly_periods", pid)
            if incoming:
                where = """w.end < ? AND w.finished IS NOT NULL AND (
                    EXISTS(SELECT 1 FROM weekly_checks k WHERE k.action=a.id AND k.period=?)
                    OR ((a.end>=? OR w.id=(SELECT id FROM weekly_periods WHERE end<? AND finished IS NOT NULL ORDER BY end DESC LIMIT 1) OR ?)
                    AND NOT EXISTS(SELECT 1 FROM weekly_checks k WHERE k.action=a.id AND k.stage='验收' AND k.result<>'待核实')))"""
                params = (p["start"], pid, p["start"], p["start"], int(backlog))
            else:
                where = "a.period=?"
                params = (pid,)
            return rows(
                c,
                "SELECT a.*,i.title FROM weekly_actions a JOIN weekly_issues i ON i.id=a.issue JOIN weekly_periods w ON w.id=a.period WHERE "
                + where
                + " ORDER BY a.start DESC,a.rowid",
                params,
            )

    @staticmethod
    def _actual(c, a, upto):
        if a["metric"] == "manual":
            return (
                c.execute(
                    """SELECT count(*) FROM weekly_history WHERE action=? AND kind='执行记录'
                AND json_extract(body,'$.day') BETWEEN ? AND ?""",
                    (a["id"], a["start"], upto),
                ).fetchone()[0]
                or None
            )
        return metric(facts(c, a["start"], upto), a["metric"], a["scope"])

    def record_execution(self, pid, aid, observed, note):
        if not note.strip():
            raise ValueError("请写下实际完成的动作。")
        with self.db.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            self._draft(c, pid)
            a = one(c, "weekly_actions", aid)
            if not a["start"] <= observed <= min(a["end"], day()):
                raise ValueError("请选择执行期内已经发生的日期。")
            if c.execute(
                """SELECT 1 FROM weekly_history WHERE action=? AND kind='执行记录'
                    AND json_extract(body,'$.day')=? AND json_extract(body,'$.detail')=?""",
                (aid, observed, note.strip()),
            ).fetchone():
                return
            event(
                c,
                pid,
                a["issue"],
                aid,
                "执行记录",
                {"day": observed, "detail": note.strip(), "source": "本人确认"},
            )
            c.execute(
                "INSERT OR IGNORE INTO weekly_triggers VALUES(?,?,?,?)",
                (aid, "本人:" + observed, observed, stamp()),
            )

    def actual(self, a, asof=None):
        with self.db.connect() as c:
            return self._actual(c, a, min(a["end"], asof or day(), day()))

    def check(self, pid, aid, stage, result, reasons=(), note="", tracking=True):
        if (
            stage not in ("周中", "验收")
            or result not in OUTCOMES
            or any(x not in REASONS for x in reasons)
        ):
            raise ValueError("无效的核验记录")
        with self.db.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            p = self._draft(c, pid)
            a = one(c, "weekly_actions", aid)
            if (
                a["start"] > min(p["end"], day())
                or a["period"] == pid
                or a["period"]
                not in {
                    r["id"]
                    for r in rows(c, "SELECT id FROM weekly_periods WHERE finished IS NOT NULL", ())
                }
            ):
                raise ValueError("行动还未进入执行期。")
            if stage == "周中" and p["start"] > a["end"]:
                raise ValueError("执行期已结束，请使用验收结果。")
            if (
                stage == "验收"
                and c.execute(
                    "SELECT 1 FROM weekly_checks WHERE action=? AND stage='验收' AND result<>'待核实' AND period<>?",
                    (aid, pid),
                ).fetchone()
            ):
                raise ValueError("此行动已在其他周期验收。")
            upto = min(day(), a["end"], p["end"])
            value = self._actual(c, a, upto)
            if result != "待核实" and value is None and not note.strip():
                raise ValueError("缺少客观记录，请补充亲自观察到的情况或选择待核实。")
            evidence = {
                "value": value,
                "metric": a["metric"],
                "target": a["target"],
                "through": upto,
                "standard": a["standard"],
            }
            c.execute(
                """INSERT INTO weekly_checks VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(action,period,stage) DO UPDATE SET result=excluded.result,reasons=excluded.reasons,note=excluded.note,
                tracking=excluded.tracking,evidence=excluded.evidence,created=excluded.created""",
                (
                    uid(),
                    aid,
                    pid,
                    stage,
                    result,
                    json.dumps(list(reasons), ensure_ascii=False),
                    note,
                    int(tracking),
                    json.dumps(evidence, ensure_ascii=False),
                    stamp(),
                ),
            )
            event(
                c,
                pid,
                a["issue"],
                aid,
                stage,
                dict(
                    result=result,
                    reasons=list(reasons),
                    note=note,
                    tracking=bool(tracking),
                    evidence=evidence,
                ),
            )

    def checks(self, aid):
        with self.db.connect() as c:
            return rows(
                c, "SELECT * FROM weekly_checks WHERE action=? ORDER BY created DESC,rowid DESC", (aid,)
            )

    def active(self, today=None):
        today = today or day()
        with self.db.connect() as c:
            return rows(
                c,
                """SELECT a.* FROM weekly_actions a JOIN weekly_periods p ON a.period=p.id
                WHERE p.finished IS NOT NULL AND ? BETWEEN a.start AND a.end
                AND NOT EXISTS(SELECT 1 FROM weekly_checks k WHERE k.action=a.id AND k.stage='验收'
                AND k.result<>'待核实') ORDER BY a.start,a.rowid""",
                (today,),
            )

    def started(self, aid, source):
        with self.db.connect() as c:
            a = one(c, "weekly_actions", aid)
            if not a["start"] <= day() <= a["end"]:
                raise ValueError("当前不在行动执行期。")
            c.execute(
                "INSERT OR IGNORE INTO weekly_triggers VALUES(?,?,?,?)", (aid, source, day(), stamp())
            )

    def notify(self, today=None):
        today = today or day()
        weekday = self.options()["check"]
        active = self.active(today)
        wanted = set()
        mid = {}
        with self.db.connect() as c:
            for a in active:
                offset = (weekday - date.fromisoformat(a["start"]).weekday()) % 7
                checked = c.execute(
                    "SELECT result FROM weekly_checks WHERE action=? AND stage='周中' ORDER BY created DESC LIMIT 1",
                    (a["id"],),
                ).fetchone()
                triggered = False
                if a["trigger_kind"] != "自定义":
                    runs = c.execute(
                        """SELECT id,day,finished FROM activity_records WHERE day BETWEEN ? AND ?
                        AND category=? AND id NOT LIKE 'manual:%'""",
                        (a["start"], today, a["trigger_kind"][:2]),
                    ).fetchall()
                    for r in runs:
                        c.execute(
                            "INSERT OR IGNORE INTO weekly_triggers VALUES(?,?,?,?)",
                            (a["id"], r["id"], r["day"], r["finished"]),
                        )
                        triggered |= r["day"] == today
                if today >= shifted(a["start"], offset) and not checked:
                    mid.setdefault(a["period"], []).append(a)
                    continue
                value = self._actual(c, a, today)
                if value is not None and value >= a["target"]:
                    continue
                if checked and checked[0] == "未达成" and today == a["end"]:
                    suffix, title = "restart", "重新开始 · " + a["recovery"]
                elif triggered:
                    suffix, title = "trigger:" + today, "专注结束 · " + a["minimum"]
                else:
                    continue
                rid = "weekly:" + a["id"] + ":" + suffix
                wanted.add(rid)
                c.execute(
                    "INSERT OR IGNORE INTO reminder_occurrences VALUES(?,?,?,?,'pending','off')",
                    (rid, rid, stamp(), title),
                )
            for pid, actions in mid.items():
                rid = "weekly:" + pid + ":mid"
                title = (
                    "周中检查 · "
                    + "、".join(a["goal"] for a in actions)
                    + "。从「此刻」打开本周行动，核对进展或调整最小动作。"
                )
                wanted.add(rid)
                c.execute(
                    "INSERT OR IGNORE INTO reminder_occurrences VALUES(?,?,?,?,'pending','off')",
                    (rid, rid, stamp(), title),
                )

            pending = c.execute(
                "SELECT id FROM reminder_occurrences WHERE local_status='pending' AND id GLOB 'weekly:*'"
            ).fetchall()
            c.executemany(
                "UPDATE reminder_occurrences SET local_status='missed' WHERE id=? AND local_status='pending'",
                [(r["id"],) for r in pending if r["id"] not in wanted],
            )
