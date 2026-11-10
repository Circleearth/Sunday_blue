from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave
import time
from PySide6.QtWidgets import QApplication
from sunday_blue.storage import Config, Store
from sunday_blue.modules.database import ModuleDB
from sunday_blue.modules.rewards import Rewards
from sunday_blue.modules.focus import Focus
from sunday_blue.modules.focus_preferences import import_sound, sound_path
from sunday_blue.modules.focus_alarm import FocusAlarm
from sunday_blue.modules.hub import ModuleHub
from sunday_blue.module_views.focus import FocusPage
from sunday_blue.module_views.focus_settings import FocusSettings

APP = QApplication.instance() or QApplication([])
ROOT = Path(__file__).resolve().parents[1]


class PomodoroTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='sunday-test-', dir=ROOT/'tests')
        self.config = Config(self.temp.name); self.db = ModuleDB(self.config.root)
        self.rewards = Rewards(self.db); self.now = 0; self.completed = []
        self.focus = Focus(self.db, clock=lambda: self.now, on_complete=self.completed.append)

    def tearDown(self): self.temp.cleanup()

    def advance(self, seconds):
        while seconds:
            step = min(seconds, 5); self.now += step; seconds -= step; self.focus.checkpoint()

    def test_countdown_caps_time_and_settles_once(self):
        self.focus.start('学习', phase='focus', duration=125)
        self.advance(120); self.now += 9; self.focus.checkpoint()
        self.assertEqual(self.focus.status()['state'], 'idle')
        self.assertEqual(self.focus.records()[0]['seconds'], 125)
        self.assertEqual(self.rewards.balances()['coins'], 2)
        self.focus.checkpoint(); self.focus.finish()
        self.assertEqual(len(self.completed), 1)
        self.assertEqual(self.focus.cycle(), {'completed':1, 'next_phase':'short_break'})
        self.assertEqual(len(self.db.events('test')), 1)

    def test_breaks_no_rewards_fourth_focus_long_break(self):
        for i in range(4):
            self.focus.start('工作', duration=125); self.advance(125)
            expected = 'long_break' if i == 3 else 'short_break'
            self.assertEqual(self.focus.cycle()['next_phase'], expected)
            self.focus.start('工作', phase=expected, duration=130); self.advance(130)
            self.assertEqual(self.focus.cycle()['next_phase'], 'focus')
        self.assertEqual(len(self.focus.records()), 4)
        self.assertEqual(self.rewards.balances()['coins'], 8)
        self.assertEqual(len(self.completed), 8)

    def test_pause_restart_settings_snapshot_and_sleep(self):
        self.focus.start('阅读', '持续读书', 'red', duration=180)
        self.advance(20); self.focus.pause(); self.now += 1000
        self.focus.set_options({'focus_minutes':30})
        self.focus = Focus(self.db, clock=lambda:self.now, on_complete=self.completed.append)
        state = self.focus.status()
        self.assertEqual((state['state'], state['duration'], state['elapsed']), ('paused',180,20))
        self.assertEqual(state['role_id'], 'red')
        self.focus.resume(); self.now += 60; self.focus.checkpoint()
        self.assertEqual(self.focus.status()['state'],'paused')
        self.assertEqual(self.focus.status()['elapsed'],20)
        self.focus.resume(); self.advance(160)
        self.assertEqual(len(self.completed),1)
        Focus(self.db, on_complete=self.completed.append)
        self.assertEqual(len(self.completed),1)  # restart never replays alarms

    def test_early_finish_is_not_completed_pomodoro(self):
        self.focus.start('学习', duration=1500); self.advance(125)
        result = self.focus.finish()
        self.assertTrue(result['valid']); self.assertFalse(result['completed_timer'])
        self.assertEqual(self.focus.cycle()['completed'],0); self.assertEqual(self.completed,[])
        with self.assertRaises(ValueError): self.focus.set_options({'volume':101})
        self.assertEqual(self.focus.options()['volume'],65)

    def test_sound_import_is_owned_and_default_wav_valid(self):
        alarm = FocusAlarm(self.config.root)
        source = alarm._default()
        with wave.open(str(source)) as audio: self.assertGreater(audio.getnframes(),0)
        imported = import_sound(self.config.root, source)
        self.assertTrue(sound_path(self.config.root, imported).is_file())
        self.focus.set_options({'sounds':{'focus':imported}})
        self.assertEqual(self.focus.options()['sounds']['focus'],imported)
        with self.assertRaises(ValueError): sound_path(self.config.root, '../outside.mp3')
        with patch.object(alarm,'_default') as default:
            alarm.play('focus',self.focus.options()|{'sound_enabled':False})
            default.assert_not_called()
        with patch.object(QApplication,'beep') as beep:
            alarm._failed(); alarm._failed(); beep.assert_called_once()
        alarm.deleteLater(); APP.processEvents()

    def test_ui_auto_finish_and_dialog_draft(self):
        hub = ModuleHub(self.config,Store(self.config.data),start_timer=False)
        hub.focus.clock = lambda:self.now
        page = FocusPage(hub); page.target.setValue(3); page.begin()
        try:
            with patch.object(hub.focus_alarm,'play') as play:
                for _ in range(36): self.now += 5; hub._focus_tick()
                play.assert_called_once(); self.assertEqual(page.phase,'short_break')
                self.assertEqual(page.clock.text(),'05:00'); self.assertTrue(page.start.isEnabled())
                self.assertIn('专注已结束',page.banner.text())
            dialog = FocusSettings(hub); dialog.fields['focus_minutes'].setValue(42); dialog.reject()
            self.assertEqual(hub.focus.options()['focus_minutes'],3)
            dialog = FocusSettings(hub); dialog.fields['focus_minutes'].setValue(42); dialog.save()
            self.assertEqual(hub.focus.options()['focus_minutes'],42)
            page.select_phase('focus'); self.assertEqual(page.clock.text(),'42:00')
        finally:
            hub.close(); page.deleteLater(); dialog.deleteLater(); hub.deleteLater(); APP.processEvents()

    def test_default_sound_decodes_with_real_qt_backend_muted(self):
        from PySide6.QtMultimedia import QMediaPlayer,QAudioOutput
        alarm=FocusAlarm(self.config.root)
        alarm.player=QMediaPlayer(alarm);alarm.output=QAudioOutput(alarm)
        alarm.output.setMuted(True);alarm.player.setAudioOutput(alarm.output)
        alarm.player.errorOccurred.connect(alarm._failed)
        with patch.object(QApplication,'beep') as beep:
            alarm.play('focus',self.focus.options())
            deadline=time.monotonic()+5
            while time.monotonic()<deadline and alarm.player.mediaStatus()!=QMediaPlayer.MediaStatus.EndOfMedia:
                APP.processEvents();time.sleep(.01)
            self.assertFalse(alarm.fallback_used);beep.assert_not_called()
            self.assertGreater(alarm.player.duration(),0)
            self.assertEqual(alarm.player.mediaStatus(),QMediaPlayer.MediaStatus.EndOfMedia)
        alarm.stop();alarm.deleteLater();APP.processEvents()

    def test_auto_loop_limit_and_manual_stop(self):
        hub=ModuleHub(self.config,Store(self.config.data),start_timer=False)
        hub.focus.clock=lambda:self.now
        hub.focus.set_options({'auto_loop':True,'max_rounds':2,'focus_minutes':3,'short_break_minutes':1})
        try:
            with patch.object(hub.focus_alarm,'play'):
                hub.start_focus('学习',duration=180)
                for _ in range(36):self.now+=5;hub._focus_tick()
                self.assertEqual(hub.focus.status()['phase'],'short_break')
                for _ in range(12):self.now+=5;hub._focus_tick()
                self.assertEqual(hub.focus.status()['phase'],'focus')
                for _ in range(36):self.now+=5;hub._focus_tick()
                self.assertEqual(hub.focus.status()['state'],'idle')
                self.assertEqual(hub.rewards.balances()['coins'],6)
                hub.start_focus('学习',duration=180);self.now+=5;hub.focus.finish()
                self.assertEqual(hub.focus.status()['state'],'idle')
                self.assertFalse(hub.db.get('focus_loop',{}).get('enabled'))
        finally:hub.close();hub.deleteLater();APP.processEvents()

    def test_focus_bubbles_survive_and_mark_previous_round(self):
        hub=ModuleHub(self.config,Store(self.config.data),start_timer=False);page=FocusPage(hub)
        try:
            for i in range(25):page.feedback('rui',str(i))
            self.assertEqual(page.feed.count(),20)
            page.begin()
            self.assertTrue(page.feed.item(0).text().startswith('【上一轮】'))
            self.assertEqual(page.feed.count(),20)
        finally:hub.close();page.deleteLater();hub.deleteLater();APP.processEvents()
