import tempfile
import unittest
from datetime import datetime,timedelta
from pathlib import Path
from unittest.mock import Mock,patch

from PySide6.QtCore import QCoreApplication,QEvent
from PySide6.QtWidgets import QApplication,QPushButton
from sunday_blue.modules.database import day,record_interval
from sunday_blue.modules.hub import ModuleHub
from sunday_blue.modules.life_state import ZONE
from sunday_blue.modules.work_audio import synchronize
from sunday_blue.module_views.moment import MomentPage,current_plan
from sunday_blue.hamlet.world import Village
from sunday_blue.storage import Config,Store

app=QApplication.instance() or QApplication([])

class Transitions(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        cfg=Config(self.temp.name)
        self.h=ModuleHub(cfg,Store(cfg.data),start_timer=False)
        self.widgets=[]

    def tearDown(self):
        self.h.close()
        for widget in self.widgets:widget.close();widget.deleteLater()
        self.h.deleteLater()
        app.processEvents()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        self.temp.cleanup()

    def test_living_day_and_receipts(self):
        before=datetime(2026,11,18,3,58,tzinfo=ZONE)
        self.assertEqual(day(before),'2026-11-17')
        with self.h.db.connect() as c:
            c.execute("INSERT INTO activity_records VALUES('x','工作','任务','rui',300,'2026-11-18','a','b')")
            record_interval(c,'x',before,before+timedelta(minutes=5))
            rows=c.execute("SELECT day,seconds FROM activity_by_day WHERE id='x' ORDER BY day").fetchall()
        self.assertEqual([tuple(r) for r in rows],[('2026-11-17',120),('2026-11-18',180)])
        self.assertEqual(self.h.calendar_records('2026-11-17')[0]['seconds'],120)
        with self.h.db.connect() as c:c.execute("INSERT INTO coin_ledger VALUES('seed',60,'test','t')")
        rewards=self.h.rewards
        rid=rewards.redeem('rest20','once')['id']
        self.assertEqual(rewards.redeem('rest20','once')['id'],rid)
        self.assertEqual(rewards.use_pass(rid,100),1300)
        self.assertEqual(rewards.use_pass(rid,300),1300)
        self.assertEqual(len(rewards.passes()),1)
        self.assertEqual(rewards.balances()['coins'],40)

    def test_phone_event_over_http(self):
        import http.client,time
        from sunday_blue.modules.phone_link import PhoneLink
        link=PhoneLink(self.h.db)
        link.start('127.0.0.1',0)
        try:
            client=http.client.HTTPConnection('127.0.0.1',link.server.server_port,timeout=3)
            headers={'Authorization':'Bearer '+self.h.db.get('phone_token'),'X-Sunday-Time':str(int(time.time())),'X-Sunday-Minutes':'25'}
            for unused in range(2):
                client.request('POST','/break',headers=headers)
                reply=client.getresponse()
                self.assertEqual(reply.status,204);reply.read()
            client.close()
            with self.h.db.connect() as c:self.assertEqual(c.execute("SELECT count(*) FROM reminder_occurrences WHERE id LIKE 'phone-break:%'").fetchone()[0],1)
        finally:link.stop()

    def test_background_refresh_and_plan_rows(self):
        from sunday_blue.image_layouts import EditableImage,set_office_mode
        from sunday_blue.module_views.rewards import RewardsPage
        from sunday_blue.module_views.weekly_plan import WeeklyPlanPage
        image=EditableImage(self.h.root,'test',self.h.root/'missing.png')
        self.widgets.append(image)
        self.assertFalse(image.isVisible())
        set_office_mode(self.h.root,True)
        set_office_mode(self.h.root,False)
        self.assertFalse(image.isVisible())
        shop=RewardsPage(self.h)
        self.widgets.append(shop)
        card=shop.items.itemWidget(shop.items.item(0))
        self.h.changed.emit('attention')
        self.assertIs(shop.items.itemWidget(shop.items.item(0)),card)
        self.h.db.set('weekly_plan:0','09:00–10:00 · 阅读\n临时安排')
        page=WeeklyPlanPage(self.h)
        self.widgets.append(page)
        page.days.setCurrentRow(0)
        self.assertEqual(page.table.item(1,1).text(),'临时安排')
        page.table.item(0,1).setText('学习')
        page.days.setCurrentRow(1)
        self.assertEqual(current_plan(self.h.db,datetime(2026,11,16,9,30)),'学习')
        page.days.setCurrentRow(0)
        self.assertEqual(page.table.item(0,1).text(),'学习')

    def test_optional_sleep_correction_and_one_reward(self):
        target=(datetime.now(ZONE)-timedelta(days=2)).date().isoformat()
        life=self.h.life
        first=life.finalize_daily(target,(0,0,False,False),meal='晚餐')
        self.assertIsNone(first['sleep_hours'])
        revised=life.finalize_daily(target,(0,0,False,False),revision=first['revision'],meal='晚餐',sleep_start='23:00',sleep_end='07:00')
        self.assertEqual(revised['sleep_hours'],8)
        with self.assertRaises(ValueError):life.finalize_daily(target,(0,0,False,False),revision=first['revision'],meal='旧表单')
        self.assertEqual(self.h.rewards.balances()['coins'],1)

    def test_resume_trash_game_and_audio(self):
        work=self.h.work
        root=work.create('项目')
        child=work.create('写摘要',root)
        work.trash(child)
        self.assertFalse(any(r['id']==child for r in work.tasks()))
        work.undo_trash()
        moment=MomentPage(self.h);self.widgets.append(moment)
        next(b for b in moment.findChildren(QPushButton) if b.text()=='工作专注').click()
        self.assertEqual(self.h.focus.status()['task_id'],child)
        self.h.focus.finish()
        self.h.db.set('weekly_plan:0','23:30–次日01:00 · 阅读')
        self.assertEqual(current_plan(self.h.db,datetime(2026,11,17,0,30)),'阅读')
        clock=[1000];game=Village(self.h.db,lambda:clock[0])
        game.transact('start','delve','1'*32)
        clock[0]+=38*600
        self.assertEqual(game.transact()['state']['floor'],2)
        endpoint=Mock()
        endpoint.GetMute.return_value=False
        for hour in (8,11,18,19):synchronize(self.h.db,datetime(2026,11,16,hour),endpoint)
        self.assertEqual([call.args[0] for call in endpoint.SetMute.call_args_list],[1,0])
        endpoint.reset_mock()
        endpoint.GetMute.return_value=True
        for hour in (8,18):synchronize(self.h.db,datetime(2026,11,17,hour),endpoint)
        endpoint.SetMute.assert_not_called()
