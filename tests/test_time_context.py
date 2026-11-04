import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from sunday_blue.time_context import time_context
from sunday_blue.agent import system_prompt
from sunday_blue.plugin_runtime import load
from test_core import Fixture

class TimeTests(Fixture):
    def test_midnight_and_timezone(self):
        zone=timezone(timedelta(hours=8))
        before=time_context(datetime(2026,11,3,23,59,tzinfo=zone))
        after=time_context(datetime(2026,11,4,0,0,tzinfo=zone))
        self.assertIn('2026-11-03',before)
        self.assertIn('2026-11-04',after)
        self.assertIn('UTC+08:00',after)
        self.assertIn('星期三',after)
        with self.assertRaises(ValueError):time_context(datetime(2026,1,1))
    def test_every_role_system_only(self):
        for role in self.config.value['roles']:
            sid=self.store.create(role)
            self.store.add(sid,'user','hello')
            with patch.object(load('time-context',self.root),'time_context',return_value='UNIQUE_CLOCK_METADATA'):
                self.assertEqual(system_prompt(self.root,role,self.config.value).count('UNIQUE_CLOCK_METADATA'),1)
            self.assertNotIn('UNIQUE_CLOCK_METADATA',str(self.store.messages(sid)))
    def test_clock_resampled_and_quiet_policy(self):
        with patch.object(load('time-context',self.root),'time_context',side_effect=['CLOCK_A','CLOCK_B']):
            self.assertIn('CLOCK_A',system_prompt(self.root,'rui',self.config.value))
            self.assertIn('CLOCK_B',system_prompt(self.root,'rui',self.config.value))
        self.assertIn('不要例行报时',time_context())
