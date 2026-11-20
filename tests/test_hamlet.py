import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import uuid

from sunday_blue.hamlet.page import Bridge
from sunday_blue.hamlet.world import Village
from sunday_blue.modules.database import ModuleDB
from sunday_blue.modules.focus import Focus

ROOT = Path(__file__).resolve().parents[1]


class ValleyTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.db = ModuleDB(folder.name)
        Focus(self.db)
        self.wall = 100000.
        self.game = Village(self.db,lambda:self.wall)
        with self.db.connect() as c:
            for table in ('coin_ledger','work_points'):
                c.execute('INSERT INTO '+table+" VALUES('seed',10,'seed','test')")

    def act(self,command,arg='',rid=None):
        return self.game.transact(command,arg,rid or uuid.uuid4().hex)

    def advance(self,minutes):
        self.wall += minutes*600
        return self.game.transact()['state']

    def test_closed_game_farm_to_forge_and_expansion(self):
        self.act('sow','wheat:2')
        with self.assertRaises(ValueError):self.act('sow','berry:2')
        self.act('start','mine')
        ready=self.advance(35)['ready']
        self.assertEqual([j['plot'] for j in ready],[2])
        self.act('harvest',ready[0]['id'])
        self.act('start','pasture')
        self.act('start','smelt')
        s=self.advance(36)
        self.assertEqual((s['inventory']['ingot'],s['inventory']['milk'],s['bond']),(1,2,1))
        self.act('start','expand')
        self.act('start','dairy')
        self.game=Village(self.db,lambda:self.wall)
        s=self.advance(65)
        self.assertEqual((s['plots'],s['inventory']['milk']),(4,1))
        self.assertEqual(self.game.transact()['state'],s)

    def test_clock_exchange_restart_and_auto_stop(self):
        with self.db.connect() as c:
            c.execute("INSERT INTO focus_runs VALUES('live','学习','','rui','running',0,'a',NULL,NULL)")
        self.game.transact()
        self.wall+=60
        with self.db.connect() as c:c.execute("UPDATE focus_runs SET elapsed=60,state='paused'")
        self.assertEqual(self.game.transact()['state']['world'],60)
        self.wall+=600
        self.assertEqual(self.game.transact()['state']['world'],120)
        with self.db.connect() as c:
            c.execute("UPDATE focus_runs SET state='finished' WHERE id='live'")
            c.execute("INSERT INTO focus_runs VALUES('break','学习','','rui','running',600,'a',NULL,NULL)")
            c.execute("INSERT INTO focus_timers VALUES('break','short_break',600,4,NULL)")
        self.assertFalse(self.game.transact()['running'])
        rid=uuid.uuid4().hex
        self.act('exchange','work',rid)
        s=self.act('exchange','work',rid)
        self.assertEqual((s['work'],s['state']['cash']),(9,27))
        with self.assertRaises(ValueError):self.act('exchange','coin',rid)
        self.assertEqual(self.act('exchange','coin')['coins'],9)
        self.act('auto','20');self.act('start','delve')
        s=self.advance(38*21)
        self.assertGreater(s['floor'],1)
        self.assertEqual((s['auto'],s['jobs']),(0,[]))
        self.assertGreaterEqual(s['cash'],0)
        self.assertEqual(self.game.transact()['state']['cash'],s['cash'])
        with self.db.connect() as c:
            self.assertEqual(c.execute('SELECT sum(amount) FROM hamlet_ledger').fetchone()[0],s['cash'])

    def test_legacy_conversion_once(self):
        self.db.set('hamlet.v1',dict(spent=2,coins=1,ore=4,wheat=3,plots=[1,0,0],weapon=2))
        for i in range(2):
            v=self.game.transact()
            self.assertEqual((v['work'],v['state']['cash'],v['state']['inventory']['wheat'],v['damage']),(8,25,5,3))
        self.assertEqual(self.db.get('hamlet.v1')['ore'],4)

    def test_desktop_manages_engine_lifetime(self):
        import time
        from PySide6.QtCore import QObject,Signal
        from PySide6.QtWidgets import QApplication
        from sunday_blue.hamlet.page import GameSession
        class Host(QObject):
            closed=Signal()
            changed=Signal(str)
            failed=Signal(str)
        engine=Path(os.environ.get('SUNDAY_GODOT') or ROOT/'runtime/godot/Godot.exe')
        if not engine.is_file():self.skipTest('Godot 4.6 unavailable')
        app=QApplication.instance() or QApplication([])
        host=Host();host.root=ROOT;host.db=self.db
        session=GameSession(host)
        self.addCleanup(session.close)
        self.assertTrue(session.launch(['--headless']))
        process=session.process
        self.assertFalse(session.launch(['--headless']))
        deadline=time.monotonic()+8
        while self.db.get('hamlet.v2') is None and time.monotonic()<deadline:
            app.processEvents()
            time.sleep(.04)
        self.assertIsNotNone(self.db.get('hamlet.v2'))
        host.closed.emit()
        self.assertIsNotNone(process.poll())
        self.assertIsNone(session.bridge)

    def test_real_engine_scene(self):
        engine=Path(os.environ.get('SUNDAY_GODOT') or ROOT/'runtime/godot/Godot.exe')
        if not engine.is_file():self.skipTest('Godot 4.6 unavailable')
        b=Bridge(self.game)
        self.addCleanup(b.close)
        env=dict(os.environ,SUNDAY_VALLEY_PORT=str(b.server.server_port),SUNDAY_VALLEY_TOKEN=b.token)
        display=['--headless'] if not env.get('SUNDAY_VALLEY_CAPTURE') else ['--position','-4000,-4000','--audio-driver','Dummy']
        result=subprocess.run([str(engine),*display,'--path',str(ROOT/'assets/hamlet/game'),
                               '--script',str(ROOT/'tests/hamlet_scene_check.gd')],env=env,
                              capture_output=True,timeout=35,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        output=(result.stdout+result.stderr).decode('utf8','replace')
        self.assertEqual(result.returncode,0,output)
        self.assertNotIn('SCRIPT ERROR',output)
        state=self.game.transact()
        self.assertEqual([j['key'] for j in state['state']['jobs']],['wheat','delve'])
        self.assertEqual(state['work'],9)
