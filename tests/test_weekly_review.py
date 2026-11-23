import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QDialogButtonBox,
    QLineEdit,
    QComboBox,
    QPlainTextEdit,
    QMessageBox,
)

from sunday_blue.modules.database import day
from sunday_blue.modules.hub import ModuleHub
from sunday_blue.modules.weekly_review import shifted
from sunday_blue.modules.weekly_insights import trends
from sunday_blue.module_views.weekly_review import WeeklyPage
from sunday_blue.storage import Config, Store

ROOT = Path(__file__).resolve().parents[1]
APP = QApplication.instance() or QApplication([])
PLAN = dict(
    goal="复习错题",
    trigger="学完一轮",
    minimum="复习一道题",
    standard="产生一次回忆记录",
    recovery="下次学习前先做一道",
    metric="reviews",
    target=1,
    trigger_kind="学习专注结束",
)


class WeeklyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / "tests", prefix="sunday-test-")
        cfg = Config(self.tmp.name)
        self.h = ModuleHub(cfg, Store(cfg.data), start_timer=False)
        self.s = self.h.weekly
        self.start, self.end = self.s.window()
        self.previous = self.s.create(shifted(self.start, -7), shifted(self.start, -1))
        self.p = self.s.create(self.start, self.end)

    def tearDown(self):
        self.h.close()
        self.tmp.cleanup()

    def test_living_boundaries_missing_zero_and_snapshot(self):
        self.h.life.save_daily(self.start, phone_total=0, phone_fun=0)
        with self.h.db.connect() as c:
            for at in ("03:59:59", "04:00:00"):
                c.execute(
                    "INSERT INTO coin_ledger VALUES(?,?,?,?)",
                    (at, 7, "test", self.start + "T" + at + "+08:00"),
                )
            c.execute(
                "INSERT INTO activity_records VALUES('f','学习','CPA','rui',600,?,'start','end')",
                (self.start,),
            )
            c.executemany(
                "INSERT INTO focus_day_slices VALUES('f',?,?)",
                [(shifted(self.start, -1), 120), (self.start, 480)],
            )
        f = self.s.details(self.p)["facts"]
        self.assertEqual(
            (
                sum(r["amount"] == 7 for r in f["coins"]),
                f["life"][0]["phone_fun"],
                f["life"][0]["sleep_hours"],
            ),
            (1, 0, None),
        )
        self.assertEqual(sum(r["seconds"] for r in f["focus"]), 480)
        self.assertEqual(self.s.details(self.previous)["facts"]["sessions"], 0)
        self.s.finish(self.p)
        self.h.life.save_daily(self.start, phone_total=50, phone_fun=20)
        self.assertEqual(self.s.details(self.p)["facts"]["life"][0]["phone_fun"], 0)
        self.s.reopen(self.p)
        self.assertEqual(self.s.details(self.p)["facts"]["life"][0]["phone_fun"], 20)
        with self.assertRaises(ValueError):
            self.s.create(shifted(self.start, -2), self.start)

    def test_issue_and_actions_across_weeks(self):
        issue = self.s.issue(self.previous, " 归 档 ", "学习")
        with self.assertRaises(ValueError):
            self.s.issue(self.previous, "归档", "学习")
        a = self.s.plan(self.previous, issue, PLAN)
        for i in range(2):
            self.s.plan(self.previous, self.s.issue(self.previous, str(i)), PLAN)
        with self.assertRaises(ValueError):
            self.s.plan(self.previous, self.s.issue(self.previous, "第四项"), PLAN)
        self.s.finish(self.previous)
        incoming = self.s.actions(self.p, True)
        self.assertEqual(len(incoming), 3)
        self.assertIsNone(self.s.actual(incoming[0]))
        self.s.check(self.p, a, "周中", "未达成", ["忘记执行"], "本人确认没有执行")
        self.s.plan(self.previous, issue, PLAN | {"minimum": "只打开昨天的错题"}, a, midweek=True)
        self.s.check(self.p, a, "验收", "部分达成", [], "已打开并回想，尚未提交回忆记录")
        for state in ("观察", "归档", "复发", "复发"):
            self.s.issue(self.p, "归档", "学习", state, evidence="本次核对", identifier=issue)
        row = self.s.issues("归档")[0]
        self.assertEqual((row["id"], row["relapses"]), (issue, 1))
        self.assertIn("调整行动", [r["kind"] for r in self.s.timeline(issue)])
        history, _ = trends(self.s, self.p)
        self.assertEqual(history[0]["partial"], 1)
        self.s.answer(self.p, "restart", "先做一小步")
        self.assertEqual(type(self.s)(self.h.db).details(self.p)["answers"]["restart"], "先做一小步")

    def test_recurring_checks_are_deduplicated(self):
        self.s.configure(0, date.fromisoformat(day()).weekday())
        a = self.s.plan(
            self.previous,
            self.s.issue(self.previous, "晚饭后散步"),
            PLAN | {"metric": "exercise", "trigger_kind": "自定义"},
        )
        self.s.finish(self.previous)
        for _ in range(2):
            self.s.notify()
        with self.h.db.connect() as c:
            self.assertEqual(
                c.execute(
                    "SELECT count(*) FROM reminder_occurrences WHERE id=?",
                    ("weekly:" + self.previous + ":mid",),
                ).fetchone()[0],
                1,
            )
        self.s.check(self.p, a, "周中", "部分达成", [], "散步十分钟")
        self.assertEqual(self.s.checks(a)[0]["result"], "部分达成")
        self.s.notify(shifted(self.end,1))
        with self.h.db.connect() as c:
            self.assertEqual(c.execute("SELECT local_status FROM reminder_occurrences WHERE id=?",
                                       ("weekly:"+self.previous+":mid",)).fetchone()[0],"missed")


    def test_three_failed_weeks_trigger_redesign_and_keep_every_receipt(self):
        periods = [
            self.s.create(shifted(self.start, -7 * i), shifted(self.start, 6 - 7 * i))
            for i in (3, 2, 1, 0)
        ]
        issue = self.s.issue(periods[0], "晚饭后活动")
        last = None
        for index, pid in enumerate(periods):
            if last:
                self.s.check(pid, last, "验收", "未达成", ["忘记执行"], "用户确认本周没有开始")
            if index < 3:
                last = self.s.plan(pid, issue, PLAN)
            self.s.finish(pid)
        series, notes = trends(self.s, periods[-1])
        self.assertEqual([r["total"] for r in series], [1, 1, 1, 0])
        self.assertTrue(any("三次验收" in r and "忘记执行" in r for r in notes))
        self.assertEqual(len([e for e in self.s.timeline(issue) if e["kind"] == "验收"]), 3)

    def test_manual_receipts_and_source_preserving_corrections(self):
        issue = self.s.issue(self.previous, "尝试重新开始")
        a = self.s.plan(self.previous, issue, PLAN | {"metric": "manual"})
        self.s.finish(self.previous)
        action = self.s.actions(self.p, True)[0]
        for i in range(2):
            self.s.record_execution(self.p, a, day(), "完成一道题")
        self.assertEqual(self.s.actual(action), 1)
        self.s.correct(self.p, "专注", "周二另有十分钟纸面学习，已核对手写记录")
        self.s.check(self.p, a, "验收", "已达成")
        self.s.finish(self.p)
        snapshot = self.s.details(self.p)["facts"]
        self.assertEqual(snapshot["focus"], [])
        self.assertIn("手写", snapshot["corrections"]["专注"]["note"])
        self.assertEqual(len(self.s.active()), 0)
        self.s.reopen(self.p)
        self.s.correct(self.p, "专注", "复核后为十二分钟")
        self.s.finish(self.p)
        with self.h.db.connect() as c:
            versions = [
                json.loads(r[0])
                for r in c.execute(
                    "SELECT body FROM weekly_history WHERE period=? AND kind='完成复盘' ORDER BY seq",
                    (self.p,),
                )
            ]
        self.assertEqual(len(versions), 2)
        self.assertIn("十分钟", versions[0]["snapshot"]["corrections"]["专注"]["note"])
        self.assertIn("十二分钟", versions[1]["snapshot"]["corrections"]["专注"]["note"])

    def test_native_first_open_and_custom_week(self):
        from sunday_blue.modules.workspace import install_workspace
        from sunday_blue.ui import MainWindow

        with tempfile.TemporaryDirectory(dir=ROOT / "tests", prefix="sunday-test-") as tmp:
            w = MainWindow(Config(tmp))
            hub = install_workspace(w)
            hub.timer.stop()
            hub.focus_timer.stop()
            try:
                w.show()
                hub.navigate.emit("growth")
                growth = w.page_stack.currentWidget()
                growth.tabs.setCurrentWidget(growth.weekly)
                APP.processEvents()
                page = growth.weekly
                self.assertIsNone(page.pid)
                page.primary.click()
                self.assertTrue(page.pid)
                old = page.pid
                page.step(-1)
                page.primary.click()
                self.assertNotEqual(page.pid, old)
                page.today()
                self.assertEqual(page.pid, old)
                page.answer.setPlainText("切页前的草稿")
                growth.tabs.setCurrentIndex(0)
                self.assertIn("切页前的草稿", hub.weekly.details(old)["answers"].values())
            finally:
                w.config.value["close_to_tray"] = False
                w.close()
                w.deleteLater()
                APP.processEvents()

    def test_interactive_draft_issue_plan_verify_and_finish(self):
        # Run native Qt editors, including their validation and Save buttons.
        i = self.s.issue(self.previous, "启动复习", "学习")
        self.s.plan(self.previous, i, PLAN)
        self.s.finish(self.previous)
        page = WeeklyPage(self.h)
        page.resize(920, 700)
        page.show()
        APP.processEvents()
        self.addCleanup(page.close)
        page.answer.setFocus()
        QTest.keyClicks(page.answer, "small step")
        QTest.qWait(450)
        self.assertIn("small step", self.s.details(self.p)["answers"].values())
        failures = []

        def dialog(fill):
            def execute():
                d = APP.activeModalWidget()
                try:
                    fill(d)
                    d.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save).click()
                    if d.isVisible():
                        raise AssertionError("editor did not accept")
                except Exception as exc:
                    failures.append(str(exc))
                    if d:
                        d.reject()

            QTimer.singleShot(0, execute)

        page.tabs.setCurrentIndex(2)
        dialog(lambda d: d.findChildren(QLineEdit)[0].setText("散步习惯"))
        page.new_issue.click()
        self.assertEqual(len(self.s.issues("散步习惯")), 1)
        page.tabs.setCurrentIndex(1)

        def plan(d):
            fields = d.findChildren(QLineEdit)
            for w, t in zip(fields, ["步行", "晚饭后", "换鞋出门", "十分钟", "次日晚饭后重试"]):
                w.setText(t)

        dialog(plan)
        page.new_action.click()
        self.assertEqual(len(self.s.actions(self.p)), 1, failures)
        page.action_list.setCurrentRow(0)

        def verify(d):
            d.findChild(QComboBox).setCurrentText("部分达成")
            d.findChild(QPlainTextEdit).setPlainText("已整理一道错题")

        dialog(verify)
        page.mid.click()
        dialog(verify)
        page.accept.click()
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            page.primary.click()
        self.assertEqual(self.s.details(self.p)["status"], "已完成")
        page.tabs.setCurrentIndex(3)
        self.assertEqual(page.trend.rowCount(), 2)
        page.step(-1)
        self.assertEqual(page.pid, self.previous)
        page.today()
        self.assertEqual(page.pid, self.p)
        self.assertEqual(failures, [])
        page.close()
