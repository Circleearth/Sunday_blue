import tempfile,time,threading,json
from pathlib import Path
from datetime import date,datetime,timedelta
from unittest import TestCase
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from sunday_blue.storage import Config,Store
from sunday_blue.modules.database import ModuleDB
from sunday_blue.modules.allowance import Allowance
from sunday_blue.modules.rewards import Rewards
from sunday_blue.modules.planner import Planner
from sunday_blue.modules.organizer import Organizer
from sunday_blue.modules.dida import Dida
from sunday_blue.modules.hub import ModuleHub
from sunday_blue.plugin_runtime import load
from sunday_blue.native_plugins import enabled
APP=QApplication.instance() or QApplication([])
ROOT=Path(__file__).resolve().parents[1]
class SharedTests(TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'tests',prefix='sunday-test-');self.config=Config(self.temp.name);self.db=ModuleDB(self.config.root)
    def tearDown(self):self.temp.cleanup()
    def test_allowance_rollover_reservation_and_monthly_gate(self):
        current=[date(2026,10,2)];a=Allowance(self.db,lambda:current[0])
        with self.db.connect() as db:a.reserve(db,'a',6000)
        self.assertEqual(a.status()['available_cents'],4000)
        current[0]=date(2026,11,2)
        self.assertEqual(a.status()['available_cents'],14000)
        with self.assertRaises(ValueError):a.change(20000)
        with self.db.connect() as db:
            db.execute('CREATE TABLE activity_records(day TEXT,seconds REAL)')
            for day in range(1,28):db.execute('INSERT INTO activity_records VALUES(?,?)',(f'2026-10-{day:02d}',7200))
        self.assertTrue(a.status()['can_change']);a.change(20000)
        with self.assertRaises(ValueError):a.change(30000)
        self.assertEqual(a.status()['available_cents'],14000)
        current[0]=date(2026,12,2);self.assertEqual(a.status()['available_cents'],34000)
    def test_budget_redemption_quota_atomic(self):
        rewards=Rewards(self.db)
        with self.db.connect() as db:db.execute("INSERT INTO coin_ledger VALUES('seed',10000,'test','now')")
        rid=rewards.add('real',10,'budget',cents=7000)
        first=rewards.redeem(rid,'once');self.assertEqual(rewards.redeem(rid,'once')['id'],first['id'])
        with self.assertRaises(ValueError):rewards.redeem(rid,'twice')
        self.assertEqual(rewards.balances()['coins'],9990);self.assertEqual(rewards.allowance.status()['available_cents'],3000)
    def test_schedule_occurrences_and_checkins_deduplicate(self):
        service=Planner(self.db);now=datetime.now().astimezone().replace(microsecond=0)
        rid=service.add('water',now.isoformat(),'daily',True,True)
        first=service.due(now);self.assertEqual(len(first),1)
        self.assertEqual(service.due(now)[0]['id'],first[0]['id'])
        service.mark(first[0]['id'],'local','sent');service.mark(first[0]['id'],'qq','sent')
        self.assertEqual(service.due(now),[])
        service.due(now+timedelta(days=1));self.assertEqual(len(service.history()),2)
        item=service.add_checkin('学习');service.check(item);service.check(item)
        self.assertEqual(service.checkins()[0]['done'],1)
        with self.db.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM checkin_history').fetchone()[0],1)
    def test_kia_scope_proposals_and_reversible_organization(self):
        plugin=load('kia-organizer',ROOT);cfg=self.config.snapshot()|{'_plugin_root':str(self.config.root)}
        with self.assertRaises(PermissionError):plugin.dispatch(cfg,'rui','search',{})
        args={'title':'主题','body':'原始信息'}
        item=plugin.dispatch(cfg,'kia','capture',args);again=plugin.dispatch(cfg,'kia','capture',args)
        self.assertEqual(item['id'],again['id']);self.assertEqual(item['status'],'proposal')
        plugin.dispatch(cfg,'kia','organize',{'id':item['id'],'category':'生活备忘'})
        service=Organizer(self.db);self.assertEqual(service.search()[0]['category'],'生活备忘');service.undo(item['id'])
        self.assertEqual(service.search()[0]['category'],'收件箱')
    def test_dida_history_preserved_and_no_remote_write(self):
        service=Dida(self.db);row={'id':'same','project':'work','title':'Task','status':0,'due':'2026-11-10','repeat':'P1D'}
        service.ingest([row]);service.ingest([row]);service.ingest([row|{'status':2}]);service.ingest([])
        self.assertEqual(len(service.tasks()),1);self.assertEqual(service.tasks()[0]['status'],2)
        with self.db.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM dida_history').fetchone()[0],2)
        self.assertFalse(hasattr(service,'delete'));self.assertFalse(hasattr(service,'create'))
    def test_dynamic_feedback_nonblocking_bounded_and_disposable(self):
        hub=ModuleHub(self.config,Store(self.config.data),start_timer=False);hub.config.value['api']['model']='fixture'
        started=threading.Event();release=threading.Event();seen=[];hub.feedback.connect(lambda r,t:seen.append(t))
        def complete(*args,**kwargs):started.set();release.wait(2);return ([{'type':'text','text':'一起慢慢来。'}],{},'end_turn')
        try:
            with patch('sunday_blue.modules.focus_dialogue.RoleProvider.complete',side_effect=complete) as request:
                begin=time.monotonic();hub.start_focus('学习',duration=180)
                self.assertLess(time.monotonic()-begin,1);self.assertTrue(started.wait(1))
                hub.focus.pause();self.assertEqual(hub.focus.status()['state'],'paused')
                release.set();deadline=time.monotonic()+2
                while time.monotonic()<deadline and hub.focus_dialogue.busy:APP.processEvents();time.sleep(.01)
                self.assertNotIn('一起慢慢来。',seen);self.assertEqual(request.call_count,1)
                self.assertTrue(any('暂停' in t for t in seen))
                hub.focus.finish();self.assertEqual(hub.focus_dialogue.history,[])
        finally:release.set();hub.close();hub.deleteLater();APP.processEvents()
    def test_shared_pages_use_live_services(self):
        from sunday_blue.module_views.planner import CalendarPage,RemindersPage,CheckinsPage
        hub=ModuleHub(self.config,Store(self.config.data),start_timer=False)
        pages=[CalendarPage(hub),RemindersPage(hub),CheckinsPage(hub)]
        try:
            hid=hub.planner.add_checkin('阅读');hub.planner.check(hid);hub.changed.emit('planner')
            self.assertIn('已完成',pages[2].items.item(0).text())
            pages[0].archive_day();self.assertEqual(hub.organizer.search()[0]['category'],'日记完整记录')
            pages[0].archive_day();self.assertEqual(len(hub.organizer.search()),1)
        finally:
            hub.close()
            for page in pages:page.deleteLater()
            hub.deleteLater();APP.processEvents()
    def test_focus_records_include_earned_coins_and_qq_channel_diagnosis(self):
        hub=ModuleHub(self.config,Store(self.config.data),start_timer=False)
        try:
            self.assertEqual(hub.focus.records(),[])
            clock=[0];hub.focus.clock=lambda:clock[0]
            hub.focus.start('学习')
            for _ in range(25):clock[0]+=5;hub.focus.checkpoint()  # 125s, past the 120s valid threshold
            hub.focus.finish()
            records=hub.focus.records()
            self.assertEqual(len(records),1)
            self.assertGreater(records[0]['coins'],0)
            self.assertIn('coins',records[0])
            page=__import__('sunday_blue.module_views.focus',fromlist=['FocusPage']).FocusPage(hub)
            self.assertIn('+',page.records.item(0).text())
            diagnosis=hub.reminder_delivery.diagnose()
            self.assertEqual(diagnosis['openid_ok'],False)
            self.assertIn('openid',diagnosis['error'])
            hub.db.set('shared_qq',{'profile':'qqbot','openid':'owner-openid','proxy':''})
            from unittest.mock import patch
            from sunday_blue.modules.reminder_delivery import ReminderDelivery
            class _FakeTransport:
                @staticmethod
                def _creds(profile):return {'appId':'a','appSecret':'b'} if profile=='qqbot' else None
                @staticmethod
                def _token(creds,cfg):return 'token'
                @staticmethod
                def _qq_send(creds,token,openid,text,cfg):return True
            with patch.object(ReminderDelivery,'_transport',lambda self:_FakeTransport):
                diagnosis=hub.reminder_delivery.diagnose()
                self.assertEqual((diagnosis['openid_ok'],diagnosis['creds_ok'],diagnosis['token_ok']),(True,True,True))
                self.assertTrue(hub.reminder_delivery.test_send())
                hub.db.set('shared_qq',{'profile':'missing','openid':'owner-openid','proxy':''})
                diagnosis=hub.reminder_delivery.diagnose()
                self.assertEqual((diagnosis['creds_ok'],diagnosis['token_ok']),(False,False))
                self.assertIn('凭据',diagnosis['error'])
        finally:
            hub.close();hub.deleteLater();APP.processEvents()
