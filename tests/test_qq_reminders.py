"""qq-reminders plugin: discovery, agent tool dispatch, db round-trip, daemon delivery."""
import json
import shutil
import sys
import tempfile
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading

import os
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sunday_blue.storage import Config, Store
from sunday_blue.plugin_runtime import discover, load
from sunday_blue.native_plugins import enabled


class QQRemindersFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='qqrem-test-', dir=Path(__file__).parent)
        self.root = Path(self.temp.name) / 'app'
        self.config = Config(self.root)
        shutil.copytree(Path(__file__).resolve().parents[1] / 'extensions' / 'plugins',
                        self.root / 'extensions' / 'plugins')
        (self.root / 'extensions' / 'skills').mkdir(parents=True)
        shutil.copytree(Path(__file__).resolve().parents[1] / 'extensions' / 'skills' / 'qq-reminders',
                        self.root / 'extensions' / 'skills' / 'qq-reminders')
        self.store = Store(self.config.data)
        # make the daemon's ROOT (repo-relative) point at this temp root so it writes
        # into the temp data dir, not the real one.
        self.plugin = load('qq-reminders', self.root)

    def tearDown(self):
        self.temp.cleanup()

    def _cfg(self, **extra):
        return {'_plugin_root': str(self.root), **extra}


class QQReminderTests(QQRemindersFixture):
    def test_discovery_and_default_enablement(self):
        meta = discover(self.root)
        self.assertIn('qq-reminders', meta)
        self.assertNotIn('error', meta['qq-reminders'])
        self.assertTrue(enabled(self.config.value, 'luna', 'qq-reminders'))
        self.assertTrue(enabled(self.config.value, 'rui', 'qq-reminders'))

    def test_add_list_remove_roundtrip(self):
        p = self.plugin
        cfg = self._cfg()
        r = p.add_reminder(cfg, 'luna', '主人要去睡觉了哦', time_of_day='22:30', repeat='daily')
        self.assertEqual(r['status'], 'ok')
        self.assertIn('next_fire', r)
        r2 = p.add_reminder(cfg, 'rui', '整理每晚必做清单', time_of_day='21:00', repeat='daily')
        self.assertEqual(r2['status'], 'ok')
        items = p.list_reminders(cfg, 'luna')
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['text'], '主人要去睡觉了哦')
        self.assertEqual(items[0]['repeat'], 'daily')
        rm = p.remove_reminder(cfg, 'luna', text='睡觉')
        self.assertEqual(rm['removed'], 1)
        self.assertEqual(p.list_reminders(cfg, 'luna'), [])
        # role isolation: rui's reminder is untouched
        self.assertEqual(len(p.list_reminders(cfg, 'rui')), 1)

    def test_missing_time_rejected(self):
        cfg = self._cfg()
        r = self.plugin.add_reminder(cfg, 'luna', '提醒', repeat='daily')
        self.assertEqual(r['status'], 'error')
        r2 = self.plugin.add_reminder(cfg, 'rui', '提醒')  # once, no time at all
        self.assertEqual(r2['status'], 'error')

    def test_agent_dispatch_path(self):
        cfg = self._cfg()
        res = self.plugin.dispatch(cfg, 'luna', 'add_reminder',
                                   {'text': '测试', 'time_of_day': '09:00', 'repeat': 'daily'})
        self.assertEqual(res['status'], 'ok')
        res2 = self.plugin.dispatch(cfg, 'luna', 'list_reminders', {})
        self.assertEqual(len(res2), 1)
        res3 = self.plugin.dispatch(cfg, 'luna', 'remove_reminder', {'text': '测试'})
        self.assertEqual(res3['removed'], 1)


class QQReminderDaemonTests(QQRemindersFixture):
    """Delivery path, verified against a local capture endpoint (no real QQ call)."""

    def _run_tick(self):
        # Load the daemon from THIS test's temp copy, freshly, under a unique
        # module name. A plain `import run` would hit sys.modules with the
        # previous test's copy (whose plugin plugin reads that test's db).
        import importlib.util
        p = self.root / 'extensions' / 'plugins' / 'qq-reminders' / 'daemon' / 'run.py'
        spec = importlib.util.spec_from_file_location('qqdaemon_%s' % id(self), str(p))
        daemon = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(daemon)
        daemon.ROOT = self.root
        daemon._tick({})
        return daemon

    def _set_role_cfg(self, role, **kv):
        # The daemon resolves delivery settings per role from settings.json,
        # exactly like the real app does.
        self.config.value['roles'][role].setdefault('plugin_settings', {})['qq-reminders'] = kv
        self.config.save()

    def test_daemon_polls_and_posts_via_test_endpoint(self):
        captured = []

        class Capture(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                n = int(self.headers['Content-Length'])
                captured.append(json.loads(self.rfile.read(n)))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{}')

        server = ThreadingHTTPServer(('127.0.0.1', 0), Capture)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            port = server.server_address[1]
            cfg = self._cfg()
            self._set_role_cfg('luna', test_send_url=f'http://127.0.0.1:{port}/send', llm_polish=False)
            self.plugin.add_reminder(cfg, 'luna', '主人要去睡觉了哦', time_of_day='00:00', repeat='once')
            db = self.plugin._conn(cfg)
            db.execute("UPDATE rem SET next_fire='2000-01-01T00:00:00'")
            db.commit(); db.close()
            self._run_tick()
            self.assertTrue(captured, 'daemon did not POST the reminder')
            self.assertEqual(captured[0]['role'], 'luna')
            self.assertIn('睡觉', captured[0]['text'])
            # delivered once → marked done
            self.assertEqual(self.plugin.list_reminders(cfg, 'luna'), [])
        finally:
            server.shutdown()
            server.server_close()

    def test_daily_reminder_reschedules_not_done(self):
        captured = []

        class Capture(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                captured.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{}')

        server = ThreadingHTTPServer(('127.0.0.1', 0), Capture)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            port = server.server_address[1]
            cfg = self._cfg()
            self._set_role_cfg('luna', test_send_url=f'http://127.0.0.1:{port}/send', llm_polish=False)
            self.plugin.add_reminder(cfg, 'luna', '每晚必做', time_of_day='21:00', repeat='daily')
            db = self.plugin._conn(cfg)
            db.execute("UPDATE rem SET next_fire='2000-01-01T00:00:00'")
            db.commit()
            rows = db.execute('SELECT next_fire, done FROM rem').fetchall()
            db.close()
            self.assertEqual(rows[0][1], 0)  # daily stays open
            self._run_tick()
            db2 = self.plugin._conn(cfg)
            after = db2.execute('SELECT next_fire, done FROM rem').fetchall()
            db2.close()
            self.assertEqual(after[0][1], 0)          # still open
            self.assertNotEqual(after[0][0], '2000-01-01T00:00:00')  # re-rolled to next day
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
