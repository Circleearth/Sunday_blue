import tempfile,unittest
from pathlib import Path
from sunday_blue.storage import Config
from sunday_blue.modules.database import ModuleDB,day
from sunday_blue.modules.life import Life
from sunday_blue.modules.focus import Focus
from sunday_blue.modules.work import Work
from sunday_blue.modules.rewards import Rewards
ROOT=Path(__file__).resolve().parents[1]
class LifeFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'tests',prefix='sunday-test-');self.cfg=Config(self.tmp.name);self.db=ModuleDB(self.tmp.name)
        self.life=Life(self.db);self.work=Work(self.db);self.clock=0;self.focus=Focus(self.db,clock=lambda:self.clock);self.rewards=Rewards(self.db)
    def tearDown(self):self.tmp.cleanup()
    def finish(self,category,seconds,label='',task_id=None):
        self.focus.start(category,label,task_id=task_id)
        for _ in range(seconds//5):self.clock+=5;self.focus.checkpoint()
        return self.focus.finish()
    def test_work_task_points_progress_history_and_no_coins(self):
        task=self.work.create('Task');self.work.update(task,progress=20)
        r=self.finish('工作',300,task_id=task)
        self.assertEqual((r['coins_earned'],r['work_points'],r['task_progress']),(0,5,20));self.assertEqual(self.work.task(task)['actual_seconds'],300)
        self.work.update(task,title='Renamed');self.assertEqual(self.focus.records()[0]['task_title'],'Task')
        self.assertEqual(self.focus.finish(),r);self.assertEqual(self.rewards.balances()['coins'],0)
        self.assertEqual(self.work.task(task)['progress'],20);self.assertTrue(any(h['kind']=='focus' for h in self.work.history(task)))
    def test_learning_bonus_once_and_custom_no_reward(self):
        self.assertEqual(self.finish('学习',300)['coins_earned'],5)
        self.assertEqual(self.finish('学习',300)['coins_earned'],8)
        self.assertEqual(self.finish('学习',300)['coins_earned'],5)
        self.assertEqual(self.finish('随意分类',300)['coins_earned'],0)
        self.assertEqual(self.rewards.balances()['coins'],18)
        with self.assertRaises(ValueError):self.focus.start('运动')
    def test_exercise_dedup_adjustment_and_caps(self):
        first=self.life.exercise('快走',30,'moderate');self.assertEqual(first['coins'],6)
        self.assertEqual(self.life.exercise('快走',30,'moderate')['id'],first['id']);self.assertEqual(self.rewards.balances()['coins'],6)
        self.life.exercise('快走',5,'moderate',record_id=first['id']);self.assertEqual(self.rewards.balances()['coins'],1)
        self.life.exercise('快走',30,'moderate',record_id=first['id']);self.assertEqual(self.rewards.balances()['coins'],6)
        for n in range(4):self.life.exercise('散步'+str(n),180,'light')
        self.assertEqual(self.rewards.balances()['coins'],20)
        with self.assertRaises(ValueError):self.life.exercise('极限',180,'high')
        with self.assertRaises(ValueError):self.life.exercise('异常',float('nan'),'light')
    def test_daily_edits_are_one_upload_reward_and_energy_reads_sources(self):
        self.life.save_daily(day(),meal='午饭',sleep_hours=7,phone_total=90,phone_fun=30,screen_hours=4,energy=70)
        self.life.save_daily(day(),meal='午饭改正',sleep_hours=8,phone_total=90,phone_fun=30)
        self.assertEqual(self.rewards.balances()['coins'],1)
        with self.assertRaises(ValueError):self.life.save_daily(day(),phone_total=30,phone_fun=90)
        self.finish('工作',300);self.finish('学习',300);self.life.exercise('慢走',10,'light')
        state=self.life.energy();self.assertEqual((state['work_minutes'],state['study_minutes'],state['exercise_minutes']),(5,5,10));self.assertEqual(len(state['trend']),7)
    def test_housework_timer_and_checkin_share_one_reward(self):
        self.life.housework('清理桌面');self.assertEqual(self.rewards.balances()['coins'],1)
        result=self.finish('家务',300,'清理桌面');self.assertEqual(result['coins_earned'],0)
        self.life.housework('清理桌面');self.assertEqual(self.rewards.balances()['coins'],1)
    def test_policy_upgrade_keeps_existing_run_and_ledger(self):
        self.focus.start('工作');rid=self.focus.status()['id']
        with self.db.connect() as c:c.execute('DELETE FROM focus_reward_policy WHERE run_id=?',(rid,))
        reopened=Focus(self.db,clock=lambda:self.clock);reopened.resume()
        for _ in range(25):self.clock+=5;reopened.checkpoint()
        self.assertEqual(reopened.finish()['coins_earned'],2)
        self.assertEqual(self.rewards.balances()['coins'],2)
