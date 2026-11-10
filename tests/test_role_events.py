from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sunday_blue.storage import Config, Store
from sunday_blue.role_events import EventLedger
from sunday_blue.role_lifecycle import RoleLifecycle
from sunday_blue.agent import Agent

ROOT = Path(__file__).resolve().parents[1]


class EventTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'tests', prefix='sunday-test-')
        self.root = Path(self.temp.name); self.config = Config(self.root); self.store = Store(self.config.data)
        self.ledger = EventLedger(self.store); self.service = RoleLifecycle(self.config,self.store)
        self.sid = self.store.create('kia'); self.mid = self.store.add(self.sid,'user','今天跑了三公里')

    def tearDown(self): self.temp.cleanup()

    def test_source_is_real_user_text_and_inference_stays_unconfirmed(self):
        original = self.ledger.record('kia',self.sid,self.mid,'original','伪造原文')
        self.assertEqual(original['body'],'今天跑了三公里')
        self.assertEqual(original['id'],self.ledger.record('kia',self.sid,self.mid,'original')['id'])
        inferred = self.ledger.record('kia',self.sid,self.mid,'inference','也许今天很疲劳')
        self.assertEqual(inferred['state'],'unconfirmed')
        self.assertEqual(inferred['root_id'],original['id'])
        self.assertEqual(inferred['id'],self.ledger.record('kia',self.sid,self.mid,'inference','也许今天很疲劳')['id'])
        with self.assertRaises(PermissionError): self.ledger.record('rui',self.sid,self.mid,'original')
        with self.assertRaises(ValueError): self.ledger.record('kia',self.sid,self.mid,'decision','强制升级')

    def test_sharing_revocation_confirmations_and_cross_role_dedup(self):
        event = self.ledger.record('kia',self.sid,self.mid,'original')
        self.assertEqual(self.ledger.list('rui'), [])
        with self.assertRaises(PermissionError): self.ledger.get('rui',event['id'])
        self.ledger.share_by_user(event['id'],['rui'])
        denied = self.ledger.derive('rui',event['id'],'task','明天跑步',lambda *a:False)
        self.assertEqual(denied['status'],'denied')
        task = self.ledger.derive('rui',event['id'],'task','明天跑步',lambda *a:True)
        self.assertEqual(task['state'],'pending')
        duplicate = self.ledger.derive('kia',event['id'],'task','再建同一任务',lambda *a:self.fail('不应重复确认'))
        self.assertEqual(duplicate['status'],'already_exists')
        self.assertEqual(self.ledger.complete('rui',task['id'],lambda *a:False)['status'],'denied')
        self.assertEqual(self.ledger.get('rui',task['id'])['state'],'pending')
        self.assertEqual(self.ledger.complete('rui',task['id'],lambda *a:True)['state'],'completed')
        self.ledger.share_by_user(event['id'],[])
        with self.assertRaises(PermissionError): self.ledger.get('rui',event['id'])

    def test_delete_preserves_shared_source_but_removes_private_records(self):
        source = self.ledger.record('kia',self.sid,self.mid,'original')
        private = self.ledger.record('kia',self.sid,self.mid,'inference','未共享的私人推断')
        self.ledger.share_by_user(source['id'],['rui'])
        self.service.archive('kia')
        backup = self.service.delete('kia',confirmed=True)
        self.assertTrue(backup.exists())
        shared = self.ledger.get('rui',source['id'])
        self.assertIsNone(shared['owner']); self.assertIsNone(shared['source_session'])
        self.assertEqual(shared['body'],'今天跑了三公里')
        with self.store.connect() as db:
            self.assertIsNone(db.execute('SELECT * FROM role_events WHERE id=?',(private['id'],)).fetchone())
            self.assertEqual(db.execute("SELECT count(*) FROM role_event_readers WHERE role='kia'").fetchone()[0],0)
        self.assertEqual(self.ledger.list('mia'),[])

    def test_grant_rechecked_after_confirmation(self):
        source = self.ledger.record('kia',self.sid,self.mid,'original')
        self.ledger.share_by_user(source['id'],['rui'])
        def revoked(*args):
            self.ledger.share_by_user(source['id'],[])
            return True
        with self.assertRaises(PermissionError): self.ledger.derive('rui',source['id'],'decision','结论',revoked)

    def test_tools_use_same_confirmation_boundary(self):
        self.config.value['roles']['kia']['capabilities'] = {'collaboration':True}
        replies = [([{'type':'tool_use','id':'rec1','name':'event_record','input':{'kind':'original'}}],{},'tool_use'),
                   ([{'type':'text','text':'已记录原文'}],{},'end_turn')]
        agent = Agent(self.root,self.config.snapshot(),self.store,self.sid)
        with patch.object(agent.provider,'complete',side_effect=replies) as complete:
            agent._run()
        schemas = complete.call_args_list[0].args[2]
        self.assertIn('event_record',{s['name'] for s in schemas})
        self.assertEqual(self.ledger.list('kia')[0]['body'],'今天跑了三公里')
        self.assertNotIn('今天跑了三公里',complete.call_args_list[0].args[0])

    def test_event_ui_lists_and_reviews_separate_kinds(self):
        from PySide6.QtWidgets import QApplication
        from sunday_blue.event_preferences import EventDialog
        app = QApplication.instance() or QApplication([])
        self.ledger.record('kia',self.sid,self.mid,'inference','疲劳可能较高')
        dialog = EventDialog(self.store,'kia')
        self.assertEqual(dialog.items.count(),2)
        labels = [dialog.items.item(i).text() for i in range(dialog.items.count())]
        self.assertTrue(any('AI 推断（未确认）' in label for label in labels))
        self.assertTrue(any('用户原始记录' in label for label in labels))
        dialog.reject(); dialog.deleteLater(); app.processEvents()
