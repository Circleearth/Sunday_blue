from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from test_core import Fixture
from sunday_blue.daypart_greetings import Greetings,period_at
from sunday_blue.agent import system_prompt

class GreetingTests(Fixture):
    def at(self,hour,day=3,minute=0):return datetime(2026,11,day,hour,minute,tzinfo=timezone(timedelta(hours=8)))
    def test_period_boundaries(self):
        expected={0:'凌晨',4:'凌晨',5:'清晨',7:'清晨',8:'早上',10:'早上',11:'中午',13:'中午',14:'下午',16:'下午',17:'傍晚',18:'傍晚',19:'晚上',21:'晚上',22:'夜间',23:'夜间'}
        for hour,name in expected.items():self.assertEqual(period_at(self.at(hour))[2],name)
    def test_first_only_shared_across_sessions_and_restart(self):
        g=Greetings(self.config.data);c=self.config.value
        first=g.on_message(c,'rui','a',1,self.at(8))
        self.assertIn('早上',first)
        self.assertIsNone(Greetings(self.config.data).on_message(c,'rui','b',2,self.at(9)))
        self.assertIn('中午',g.on_message(c,'rui','b',3,self.at(11)))
        self.assertIn('早上',g.on_message(c,'rui','b',4,self.at(8,day=4)))
        self.assertIn('早上',g.on_message(c,'red','c',5,self.at(8)))
    def test_night_repeats_and_same_message_is_idempotent(self):
        g=Greetings(self.config.data);c=self.config.value
        a=g.on_message(c,'luna','a',1,self.at(1))
        self.assertEqual(a,g.on_message(c,'luna','a',1,self.at(1)))
        b=g.on_message(c,'luna','a',2,self.at(1,minute=1))
        self.assertNotEqual(a,b)
        self.assertIn('睡',a+b)
        self.assertEqual(len(g.for_session('a')),2)
    def test_cooldown_and_disable_repeat(self):
        g=Greetings(self.config.data);c=self.config.value
        c['greetings']={'night_repeat':True,'night_interval_minutes':15}
        self.assertIsNotNone(g.on_message(c,'rui','a',1,self.at(1)))
        self.assertIsNone(g.on_message(c,'rui','a',2,self.at(1,minute=14)))
        self.assertIsNotNone(g.on_message(c,'rui','a',3,self.at(1,minute=15)))
        c['greetings']['night_repeat']=False
        self.assertIsNone(g.on_message(c,'rui','a',4,self.at(2)))
    def test_plugins_are_independent_and_prompt_free(self):
        c=self.config.value;g=Greetings(self.config.data)
        c['roles']['rui']['native_plugins']={'time-context':False,'daypart-greetings':True}
        with patch('sunday_blue.agent.time_context') as clock:
            prompt=system_prompt(self.root,'rui',c);clock.assert_not_called()
        sid=self.store.create('rui');mid=self.store.add(sid,'user','hello')
        greeting=g.on_message(c,'rui',sid,mid,self.at(8))
        self.assertNotIn(greeting,prompt)
        self.assertEqual(len(self.store.messages(sid,True)),1)
        c['roles']['rui']['native_plugins']={'time-context':True,'daypart-greetings':False}
        with patch('sunday_blue.agent.time_context',return_value='clock token'):
            self.assertIn('clock token',system_prompt(self.root,'rui',c))
        self.assertIsNone(g.on_message(c,'rui',sid,mid+1,self.at(11)))
