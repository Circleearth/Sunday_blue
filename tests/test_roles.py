import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from sunday_blue.storage import Config, Store
from sunday_blue.roles import RoleRegistry, list_roles, require_role
from sunday_blue.role_lifecycle import RoleLifecycle
from sunday_blue.personas import read_persona
from sunday_blue.living_memory import enqueue, pending_count

ROOT = Path(__file__).resolve().parents[1]


class RoleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'tests', prefix='roles-')
        self.root = Path(self.temp.name)
        self.config = Config(self.root)
        self.store = Store(self.config.data)
        self.service = RoleLifecycle(self.config, self.store)

    def tearDown(self):
        self.temp.cleanup()

    def test_create_rename_restart_and_memory_isolation(self):
        rid = self.service.create('自定义 / 角色')
        self.assertTrue(rid.startswith('role_'))
        self.assertEqual(self.config.value['roles'][rid]['roots'], [])
        sid = self.store.create(rid)
        uid = self.store.add(sid, 'user', '唯一记录')
        self.store.add(sid, 'assistant', '已收到')
        enqueue(self.root, rid, sid, uid, self.store.messages(sid))
        original = read_persona(self.root, rid)
        self.service.rename(rid, '新名字')
        restarted = Config(self.root)
        self.assertEqual(restarted.registry.get(rid)['name'], '新名字')
        self.assertIn(rid, restarted.value['roles'])
        self.assertEqual(original, read_persona(self.root, rid))
        self.assertEqual(pending_count(self.root, rid), 1)
        self.assertEqual(pending_count(self.root, 'rui'), 0)
        self.assertEqual(self.store.sessions(rid)[0]['id'], sid)
        with self.assertRaises(ValueError): self.store.create('../bad')

    def test_archive_restore_blocks_execution_and_keeps_data(self):
        rid = self.service.create('保留数据')
        sid = self.store.create(rid)
        self.store.add(sid, 'user', '原文')
        self.service.archive(rid)
        self.assertNotIn(rid, {r[0] for r in list_roles(self.root)})
        for fn in (lambda: self.store.create(rid), lambda: pending_count(self.root, rid)):
            with self.assertRaises(ValueError): fn()
        self.service.restore(rid)
        self.assertEqual(self.store.messages(sid)[0]['content'], '原文')

    def test_busy_and_pending_reminders_block_retirement(self):
        rid = self.service.create('待处理')
        self.service.busy = lambda role: True
        with self.assertRaises(ValueError): self.service.archive(rid)
        self.service.busy = lambda role: False
        path = self.root/'data/plugins/qq-reminders/state.sqlite3'
        path.parent.mkdir(parents=True)
        db = sqlite3.connect(path)
        db.execute('CREATE TABLE rem(id INTEGER, role TEXT, done INTEGER)')
        db.execute('INSERT INTO rem VALUES(1,?,0)', (rid,)); db.commit(); db.close()
        with self.assertRaises(ValueError): self.service.archive(rid)
        self.assertEqual(require_role(self.root, rid)['state'], 'active')

    def test_delete_exports_and_cleans_only_owned_data(self):
        rid = self.service.create('被删除的测试角色')
        sid = self.store.create(rid)
        uid = self.store.add(sid, 'user', '需要备份的原文')
        self.store.add(sid, 'assistant', '回应')
        enqueue(self.root, rid, sid, uid, self.store.messages(sid))
        self.config.value['mcp_servers'] = [{'name':'shared', 'roles':[rid,'rui']}]
        self.config.value['api']['model'] = 'untouched'
        other = self.store.create('rui'); self.store.add(other, 'user', '其他角色')
        self.service.archive(rid)
        with self.assertRaises(ValueError): self.service.delete(rid)
        backup = self.service.delete(rid, confirmed=True)
        with zipfile.ZipFile(backup) as z:
            record = json.loads(z.read('record.json'))
            self.assertEqual(record['messages'][0]['content'], '"需要备份的原文"')
            self.assertTrue(any('inbox.sqlite3' in f for f in z.namelist()))
        self.assertIsNone(self.store.session(sid))
        self.assertEqual(self.store.messages(other)[0]['content'], '其他角色')
        self.assertFalse((self.root/'personas'/rid).exists())
        self.assertFalse((self.root/'data/plugins/livingmemory'/rid).exists())
        self.assertEqual(self.config.value['api']['model'], 'untouched')
        self.assertEqual(self.config.value['mcp_servers'][0]['roles'], ['rui'])
        restart = Config(self.root)
        self.assertNotIn(rid, restart.value['roles'])
        self.assertFalse((self.root/'data/memory'/rid).exists())

    def test_interrupted_delete_is_inert_and_restart_finishes(self):
        rid = self.service.create('恢复测试')
        sid = self.store.create(rid)
        self.store.add(sid, 'user', '原始内容')
        self.service.archive(rid)
        with patch('sunday_blue.role_lifecycle.shutil.rmtree', side_effect=OSError('模拟占用或断电')):
            with self.assertRaises(OSError): self.service.delete(rid, confirmed=True)
        self.assertEqual(self.service.registry.get(rid)['state'], 'deleting')
        with self.assertRaises(ValueError): self.store.create(rid)
        restarted = RoleLifecycle(Config(self.root), self.store)
        self.assertEqual(restarted.resume_pending(), [])
        self.assertEqual(restarted.resume_pending(), [])
        self.assertIsNone(self.store.session(sid))
        self.assertEqual(len(list(restarted.operations.glob('*/backup.zip'))), 1)

    def test_unknown_plugin_data_and_symlinks_fail_closed(self):
        rid = self.service.create('依赖检查')
        unknown = self.root/'data/plugins/custom'
        unknown.mkdir(parents=True)
        with self.assertRaises(ValueError): self.service.archive(rid)
        self.assertEqual(self.service.registry.get(rid)['state'], 'active')


class RoleUITests(unittest.TestCase):
    setUp = RoleTests.setUp
    tearDown = RoleTests.tearDown
    def test_all_role_consumers_follow_registry(self):
        from PySide6.QtWidgets import QApplication
        from sunday_blue.ui import MainWindow
        from sunday_blue.settings import Settings
        from sunday_blue.persona_preferences import PersonaDialog
        from sunday_blue.role_preferences import RoleManager
        app = QApplication.instance() or QApplication([])
        window = MainWindow(self.config)
        rid = window.role_service.create('动态角色')
        window.refresh_roles()
        self.assertIn(rid, window.role_buttons)
        window.switch_role(rid)
        sid = window.sid
        window.role_service.rename(rid, '改名后')
        window.refresh_roles()
        self.assertEqual(window.sid, sid)
        self.assertEqual(window.chat_title.text(), '改名后')
        settings = Settings(self.config, rid, window)
        self.assertGreaterEqual(settings.role_combo().findData(rid), 0)
        self.assertGreaterEqual(settings.chat_preferences.role.findData(rid), 0)
        persona = PersonaDialog(self.root, rid)
        self.assertGreaterEqual(persona.roles.findData(rid), 0)
        persona.reject(); settings.reject()
        manager = RoleManager(window.role_service, rid, window)
        self.assertEqual(manager.selected(), rid)
        manager.reject()
        window.role_service.archive(rid); window.refresh_roles()
        self.assertNotIn(rid, window.role_buttons)
        self.assertNotEqual(window.role, rid)
        window.close(); app.processEvents()
