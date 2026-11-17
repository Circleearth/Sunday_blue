import unittest,tempfile,json,time
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication,QEvent
from sunday_blue.storage import Config,Store
from sunday_blue.modules.hub import ModuleHub
APP=QApplication.instance() or QApplication([])
class InboxTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=Path(__file__).parent);cfg=Config(self.tmp.name);self.h=ModuleHub(cfg,Store(cfg.data),start_timer=False)
 def tearDown(self):
  self.h.close();self.h.deleteLater();APP.processEvents();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.tmp.cleanup()
 def test_atomic_confirmation_keeps_original_and_deduplicates_tasks(self):
  raw='  original\n raw text  ';r=self.h.duties.capture('note',raw);category=self.h.organizer.categories()[0]
  with self.h.db.connect() as c:c.execute("INSERT INTO inbox_proposals VALUES(?,?,?,?,'ready','',?)",(r['id'],category,'summary','[]','2026-11-17'))
  self.h.inbox_assistant.accept(r['id'],category,'summary',['task']);self.h.inbox_assistant.accept(r['id'],category,'summary',['task'])
  with self.h.db.connect() as c:
   self.assertEqual(c.execute('SELECT body FROM organized_records WHERE id=?',(r['record_id'],)).fetchone()[0],raw);self.assertEqual(c.execute("SELECT count(*) FROM work_tasks WHERE id LIKE 'inbox:%'").fetchone()[0],1)
 def test_background_local_fixture_and_retry(self):
  r=self.h.duties.capture('note','body');category=self.h.organizer.categories()[0]
  class Fake:
   def __init__(self,*a,**k):self.config={}
   def complete(self,*a,**k):return [{'type':'text','text':json.dumps({'category':category,'summary':'summary','todos':['todo']})}],None,None
  with patch('sunday_blue.modules.inbox_assistant.RoleProvider',Fake):
   self.assertTrue(self.h.inbox_assistant.pump(r['id']))
   limit=time.monotonic()+5
   while self.h.inbox_assistant.busy and time.monotonic()<limit:time.sleep(.01)
  self.assertEqual(self.h.inbox_assistant.proposal(r['id'])['state'],'ready')
  with self.h.db.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM work_tasks').fetchone()[0],0)
