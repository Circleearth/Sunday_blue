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
        self.assertIn('休息',a+b)
        self.assertEqual(g.for_session('a'),{})
    def test_cooldown_and_disable_repeat(self):
        g=Greetings(self.config.data);c=self.config.value
        c['greetings']={'night_repeat':True,'night_interval_minutes':15}
        self.assertIsNotNone(g.on_message(c,'rui','a',1,self.at(1)))
        self.assertIsNone(g.on_message(c,'rui','a',2,self.at(1,minute=14)))
        self.assertIsNotNone(g.on_message(c,'rui','a',3,self.at(1,minute=15)))
        c['greetings']['night_repeat']=False
        self.assertIsNone(g.on_message(c,'rui','a',4,self.at(2)))
    def test_plugins_independent_and_no_persistent_prompt(self):
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

    def test_model_reply_stored_and_trigger_not_repeated_after_tools(self):
        from sunday_blue.agent import Agent
        sid=self.store.create('rui');self.store.add(sid,'user','hello')
        agent=Agent(self.root,self.config.snapshot(),self.store,sid)
        replies=[([{'type':'text','text':'早上好，今天想聊什么？'},{'type':'tool_use','id':'a','name':'memory_read','input':{}}],{},'tool_use'),
                 ([{'type':'text','text':'接着回答你的问题。'}],{},'end_turn')]
        with patch.object(agent.provider,'complete',side_effect=replies) as api:
            agent._run()
            self.assertIn('<greeting_event>',api.call_args_list[0].args[0])
            self.assertNotIn('<greeting_event>',api.call_args_list[1].args[0])
        history=self.store.messages(sid,True)
        self.assertIn('早上好',str(history))
        self.assertNotIn('<greeting_event>',str(history))
        self.assertEqual(Greetings(self.config.data).for_session(sid),{})

    def test_failed_request_retry_and_legacy_history(self):
        from sunday_blue.agent import Agent
        sid=self.store.create('rui');mid=self.store.add(sid,'user','hello')
        first=Agent(self.root,self.config.snapshot(),self.store,sid)
        with patch.object(first.provider,'complete',side_effect=RuntimeError('network')):
            with self.assertRaises(RuntimeError):first._run()
        retry=Agent(self.root,self.config.snapshot(),self.store,sid)
        with patch.object(retry.provider,'complete',return_value=([{'type':'text','text':'你好。'}],{},'end_turn')) as api:
            retry._run();self.assertIn('<greeting_event>',api.call_args.args[0])
        g=Greetings(self.config.data)
        with g.connection() as db:db.execute('INSERT INTO events VALUES(?,?,?,?)',(sid,mid,'旧版本已经显示的寒暄','2026-11-03'))
        restored=g.replay_legacy(sid,self.store.messages(sid,True))
        self.assertEqual(restored[1]['content'],'旧版本已经显示的寒暄')
        self.assertEqual(restored[1]['id'],mid)
        self.assertNotIn('旧版本已经显示的寒暄',str(self.store.messages(sid,True)))
