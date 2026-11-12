import json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime,timedelta
from PySide6.QtCore import QCoreApplication,QEvent
from PySide6.QtWidgets import QApplication,QWidget
from sunday_blue.storage import Config,Store
from sunday_blue.modules.database import ModuleDB
from sunday_blue.modules.hub import ModuleHub
from sunday_blue.modules.dida_tools import dispatch,normalize
from sunday_blue.modules.dida import Dida
from sunday_blue.modules.life_state import ZONE
from sunday_blue.tray import Tray
from sunday_blue.instance import Instance
from sunday_blue.context_budget import used,threshold,prefix
APP=QApplication.instance() or QApplication([])
ROOT=Path(__file__).resolve().parents[1]
class DesktopUpgradeTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(dir=ROOT/'tests',prefix='sunday-test-');self.root=Path(self.temp.name);self.cfg=Config(self.root);self.db=ModuleDB(self.root)
  self.hub=ModuleHub(self.cfg,Store(self.cfg.data),start_timer=False)
 def tearDown(self):
  self.hub.close();self.hub.deleteLater();APP.processEvents();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.temp.cleanup()
 def test_missing_icon_and_activation(self):
  w=QWidget();w.config=self.cfg;tray=Tray(w);self.assertFalse(tray.icon.icon().isNull())
  instance=Instance(self.root);instance.listen();seen=[];instance.activated.connect(lambda:seen.append(True))
  try:
   other=Instance(self.root);self.assertTrue(other.wake());APP.processEvents();self.assertTrue(seen)
   tray.show();self.assertTrue(w.isVisible());self.cfg.value['close_to_tray']=True
   with patch('sunday_blue.tray.QSystemTrayIcon.isSystemTrayAvailable',return_value=False):self.assertFalse(tray.hide_on_close())
  finally:instance.close();tray.icon.hide();w.close();w.deleteLater()
 def test_sleep_dates_phone_and_no_repeat_reward(self):
  day=(datetime.now(ZONE).date()-timedelta(days=1)).isoformat()
  r=self.hub.life.save_daily(day,sleep_start='23:30',sleep_end='07:00',phone_total=90,phone_fun=45)
  self.assertEqual(r['sleep_hours'],7.5);self.assertEqual(r['sleep_start'],'23:30')
  self.hub.life.save_daily(day,sleep_start='23:30',sleep_end='07:00',phone_total=90,phone_fun=45)
  self.assertEqual(self.hub.rewards.balances()['coins'],1)
  with self.assertRaises(ValueError):self.hub.life.save_daily(day,phone_total=20,phone_fun=30)
 def test_capacity_growth_correction_and_daily_idempotency(self):
  now=datetime.now(ZONE).replace(hour=10,minute=0);day=now.date().isoformat();state=self.hub.life.state
  state.settle(now);r=self.hub.life.exercise('足球',30,'moderate',day=day);cap=state.caps(day)['physical_cap'];self.assertGreater(cap,30)
  self.hub.life.exercise('足球',30,'moderate',day=day);self.assertEqual(state.caps(day)['physical_cap'],cap)
  state.settle(now);state.settle(now);self.assertEqual(state.caps(day)['physical_cap'],cap)
  self.hub.life.exercise('足球',5,'moderate',day=day,record_id=r['id']);self.assertLess(state.caps(day)['physical_cap'],cap)
  later=now+timedelta(days=10);state.settle(later)
  with self.db.connect() as c:
   self.assertGreaterEqual(c.execute('SELECT cap FROM vitality_state').fetchone()[0],30)
   count=c.execute('SELECT count(*) FROM vitality_days').fetchone()[0]
  state.settle(later)
  with self.db.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM vitality_days').fetchone()[0],count)
 def test_reporting_cycle_expiry_and_sent_no_retry(self):
  now=datetime.now(ZONE).replace(hour=10);state=self.hub.life.state;state.report_cycle(now);state.report_cycle(now)
  with self.db.connect() as c:
   row=c.execute("SELECT * FROM reminder_occurrences WHERE schedule_id='life-report'").fetchall();self.assertEqual(len(row),1)
   c.execute("UPDATE reminder_occurrences SET qq_status='sent'")
  state.report_cycle(now)
  with self.db.connect() as c:self.assertEqual(c.execute('SELECT qq_status FROM reminder_occurrences').fetchone()[0],'sent')
  state.report_cycle(now+timedelta(days=1))
  with self.db.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM reminder_occurrences').fetchone()[0],2)
 def test_activity_timer_adjustment_and_focus_exclusion(self):
  timer=self.hub.life_timer;now=[0.0];timer.clock=lambda:now[0];timer.start('放松');now[0]=10;timer.checkpoint();timer.pause();now[0]=100;timer.resume();now[0]=110;timer.pause()
  self.assertEqual(timer.status()['elapsed'],20)
  timer.resume()
  with self.assertRaises(ValueError):self.hub.focus.start('学习')
  timer.pause();timer.finish(12,'low','medium',True);row=timer.history()[0];self.assertEqual(row['elapsed'],20);self.assertEqual(row['effective'],12)
  with self.db.connect() as c:self.assertAlmostEqual(c.execute('SELECT sum(effective) FROM life_timer_days').fetchone()[0],12,places=4)
  self.hub.focus.start('学习')
  with self.assertRaises(ValueError):timer.start('其他')
 def test_muscle_unknown_and_previous_day(self):
  day=(datetime.now(ZONE).date()-timedelta(days=1)).isoformat();self.hub.life.exercise('力量训练',60,'high',day=day,muscles=['胸','二头肌'])
  values={r['part']:r['level'] for r in self.hub.life.state.muscles(datetime.now(ZONE).date().isoformat())}
  self.assertEqual(values['胸'],'orange');self.assertEqual(values['背'],'green');self.assertEqual(values['二头肌'],'orange')
  self.assertNotIn('手臂',values)
  older=(datetime.now(ZONE).date()-timedelta(days=4)).isoformat()
  self.hub.life.exercise('力量训练',60,'high',day=older,muscles=['背'])
  values4={r['part']:r['level'] for r in self.hub.life.state.muscles((datetime.now(ZONE).date()-timedelta(days=3)).isoformat())}
  self.assertEqual(values4['背'],'orange')
  green={r['part']:r['level'] for r in self.hub.life.state.muscles((datetime.now(ZONE).date()-timedelta(days=3+4-1)).isoformat())}
  self.assertEqual(green['背'],'green')
 def test_real_tokens_and_recent_context(self):
  self.assertIsNone(used({}));self.assertEqual(used({'input_tokens':10,'cache_read_input_tokens':20,'output_tokens':3}),33)
  self.assertLess(threshold({'context_limit':32000,'max_tokens':4096}),32000);self.assertEqual(threshold({'context_limit':1000000}),300000)
  messages=[{'id':i,'role':'user' if i%2==0 else 'assistant','content':'x'} for i in range(20)]
  older=prefix(messages);self.assertEqual(older[-1]['id'],11);self.assertEqual(messages[len(older)]['role'],'user')
 def test_dida_structured_contract_and_confirmed_receipt(self):
  p=normalize({'title':'test','due':'2026-11-12T10:00','repeat':{'frequency':'weekly','weekdays':['MO','WE']},'remind_minutes':[0,15]},True)
  self.assertEqual(p['repeatFlag'],'RRULE:FREQ=WEEKLY;INTERVAL=1;BYDAY=MO,WE');self.assertEqual(p['reminders'],['TRIGGER:PT0S','TRIGGER:-PT15M']);self.assertTrue(p['dueDate'].endswith('+08:00'))
  self.assertIsNone(normalize({'title':'once'},True)['repeatFlag'])
  calls=[];task={'id':'t','projectId':'p','title':'test','etag':'v1','status':0}
  class Client:
   def call(self,name,args):
    calls.append(name)
    if name=='get_task_by_id':return dict(task)
    if name=='delete_task':return {'deleted':'t'}
    return dict(task)
  with patch.object(Dida,'client',return_value=Client()):
   with self.assertRaises(ValueError):dispatch(self.root,'delete','t','wrong','v1',approve=lambda *a:True,source='1')
   self.assertNotIn('delete_task',calls)
   r=dispatch(self.root,'delete','t','test','v1',approve=lambda *a:True,source='1');self.assertEqual(r['status'],'deleted')
   dispatch(self.root,'delete','t','test','v1',approve=lambda *a:True,source='1');self.assertEqual(calls.count('delete_task'),1)
 def test_dida_uncertain_write_never_retried(self):
  class Client:
   calls=0
   def call(self,name,args):self.calls+=1;raise TimeoutError()
  client=Client()
  with patch.object(Dida,'client',return_value=client):
   with self.assertRaises(TimeoutError):dispatch(self.root,'create',fields={'title':'test'},approve=lambda *a:True,source='same')
   with self.assertRaises(ValueError):dispatch(self.root,'create',fields={'title':'test'},approve=lambda *a:True,source='same')
   self.assertEqual(client.calls,1)

 def test_optional_ollama_startup_and_external_service_preserved(self):
  import sunday_blue.living_memory as memory
  with patch.object(memory,'start_ollama') as start:
   self.assertIsNone(memory.startup(self.root));start.assert_not_called()
  self.db.set('livingmemory_startup',{'enabled':True})
  with patch.object(memory,'ollama_status',return_value={'online':True}),patch.object(memory,'start_ollama') as start,patch.object(memory.requests,'post') as post:
   job=memory.startup(self.root);job.join(3);self.assertFalse(job.is_alive());start.assert_not_called();self.assertTrue(post.called)
   self.assertTrue(self.db.get('livingmemory_startup_result')['ok'])
  with patch.object(memory,'_ollama',None),patch.object(memory,'_brains',{}),patch.object(memory,'ollama_status',return_value={'online':True}),patch.object(memory.subprocess,'run') as kill:
   memory.stop_ollama();kill.assert_not_called()
 def test_work_unknown_estimate_and_independent_progress(self):
  parent=self.hub.work.create('project',estimate_minutes=100);child=self.hub.work.create('part',parent_id=parent,estimate_minutes=None)
  self.hub.work.update(child,progress=25)
  self.hub.focus.start('工作',task_id=child)
  with self.db.connect() as c:c.execute("UPDATE focus_runs SET elapsed=1800 WHERE state='running'")
  self.hub.focus.finish();p=self.hub.work.task(parent);part=self.hub.work.task(child)
  self.assertEqual(p['progress'],25);self.assertEqual(p['estimate_minutes'],100);self.assertEqual(part['estimate_minutes'],0)
  self.assertAlmostEqual(p['actual_seconds'],part['actual_seconds']);self.assertGreaterEqual(p['actual_seconds'],1800)
 def test_shop_cards_keep_purchase_accounting(self):
  from sunday_blue.module_views.rewards import RewardsPage
  page=RewardsPage(self.hub)
  try:
   self.assertEqual(page.items.count(),len(self.hub.rewards.list()));self.assertIsNotNone(page.items.itemWidget(page.items.item(0)))
   with self.db.connect() as c:c.execute('INSERT INTO coin_ledger VALUES(?,?,?,?)',('fixture',100,'fixture','now'))
   rid=page.items.item(0).data(__import__('PySide6.QtCore',fromlist=['Qt']).Qt.ItemDataRole.UserRole)['id']
   self.hub.rewards.redeem(rid,'unique');balance=self.hub.rewards.balances()['coins'];self.hub.rewards.redeem(rid,'unique');self.assertEqual(self.hub.rewards.balances()['coins'],balance)
  finally:page.close();page.deleteLater()

 def test_dida_capability_respects_global_and_role_disable(self):
  from sunday_blue.capabilities import TurnCapabilities
  self.db.set('dida_mcp_auth',{'token_encrypted':'fixture-presence-only'})
  cfg=self.cfg.snapshot();self.assertIn('dida',TurnCapabilities(self.root,cfg,'rui','滴答任务').active)
  cfg['features']['dida']=False;self.assertNotIn('dida',TurnCapabilities(self.root,cfg,'rui','滴答任务').catalog)
  cfg['features']['dida']=True;cfg['roles']['rui'].setdefault('capabilities',{})['dida']=False
  self.assertNotIn('dida',TurnCapabilities(self.root,cfg,'rui','滴答任务').catalog)
  cfg['roles']['rui']['capabilities']['dida']=True;self.db.set('dida_mcp_auth',{})
  self.assertNotIn('dida',TurnCapabilities(self.root,cfg,'rui','滴答任务').catalog)
