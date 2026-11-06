import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from sunday_blue.storage import Config, Store
from sunday_blue.files import FileTools
from sunday_blue.personas import read_persona, save_persona, previous_persona
from sunday_blue.living_memory import enqueue, pending_count, queue_connect
from sunday_blue.agent import system_prompt
from sunday_blue.plugin_runtime import turn_hooks

ROOT = Path(__file__).resolve().parents[1]


class MemoryPersonaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='sunday-test-', dir=ROOT/'tests')
        self.root = Path(self.temp.name)
        self.config = Config(self.root)
        self.store = Store(self.config.data)
        shutil.copytree(ROOT/'personas', self.root/'personas')

    def tearDown(self):
        self.temp.cleanup()

    def test_inbox_idempotent_role_local_and_filters_tool_results(self):
        sid = self.store.create('rui')
        uid = self.store.add(sid, 'user', '我喜欢茶')
        self.store.add(sid, 'assistant', [{'type':'tool_use','id':'x','name':'read_file','input':{}}])
        self.store.add(sid, 'user', [{'type':'tool_result','tool_use_id':'x','content':'secret tool receipt'}])
        self.store.add(sid, 'assistant', [{'type':'text','text':'记住了'}])
        for _ in range(2):
            enqueue(self.root, 'rui', sid, uid, self.store.messages(sid))
        self.assertEqual(pending_count(self.root, 'rui'), 1)
        for role in self.config.value['roles']:
            if role != 'rui':
                self.assertEqual(pending_count(self.root, role), 0)
        with queue_connect(self.root, 'rui') as db:
            raw = db.execute('SELECT messages FROM turns').fetchone()[0]
        self.assertNotIn('secret tool receipt', raw)
        self.assertEqual(len(json.loads(raw)), 2)
        with self.assertRaises(ValueError):
            pending_count(self.root, '../red')

    def test_incomplete_turn_is_not_remembered(self):
        sid = self.store.create('rui')
        uid = self.store.add(sid, 'user', '还没有回复')
        enqueue(self.root, 'rui', sid, uid, self.store.messages(sid))
        self.assertEqual(pending_count(self.root, 'rui'), 0)

    def test_memory_always_requires_review_even_with_trusted_workspace(self):
        review = []
        ft = FileTools(self.root, 'rui', [{'path':str(self.root.parent), 'write':True,'trusted':True}],
                       lambda *args: review.append(args) or False, lambda *args: None)
        path = self.root/'data/memory/rui/long_term.md'
        original = path.read_text(encoding='utf-8')
        self.assertEqual(ft.write('', content='新偏好', memory=True)['status'], 'denied')
        self.assertEqual(path.read_text(encoding='utf-8'), original)
        self.assertEqual(review[0][2]['before'].replace('\r\n','\n'), original)
        self.assertEqual(review[0][2]['after'], '新偏好')

    def test_persona_version_conflict_and_archive_not_in_prompt(self):
        before = read_persona(self.root, 'rui')
        after = before | {'voice.md': '轻松但认真。'}
        path = save_persona(self.root, 'rui', before, after)
        self.assertTrue(path.exists())
        self.assertEqual(previous_persona(self.root, 'rui'), before)
        self.assertEqual(read_persona(self.root, 'rui'), after)
        with self.assertRaises(RuntimeError):
            save_persona(self.root, 'rui', before, before | {'voice.md':'过期修改'})
        with self.assertRaises(ValueError):
            save_persona(self.root, 'rui', after, after | {'identity.md':''})
        prompt = system_prompt(self.root, 'rui', self.config.snapshot())
        self.assertIn('轻松但认真。', prompt)
        self.assertNotIn('memory.put', prompt)
        self.assertNotIn('训练执行率由 Python', prompt)
        self.assertNotEqual(read_persona(self.root, 'red')['voice.md'], '轻松但认真。')

    def test_plugin_hooks_disabled_and_failure_contained(self):
        shutil.copytree(ROOT/'extensions/plugins/livingmemory', self.root/'extensions/plugins/livingmemory')
        config = self.config.snapshot()
        with patch('sunday_blue.living_memory.get_brain', side_effect=RuntimeError('offline')) as brain:
            self.assertEqual(turn_hooks(self.root,config,'rui','before_turn','sid',{'content':'hi'}), '')
            brain.assert_not_called()
            config['roles']['rui'].setdefault('native_plugins',{})['livingmemory'] = True
            errors = []
            self.assertEqual(turn_hooks(self.root,config,'rui','before_turn','sid',{'content':'hi'},
                                       on_error=lambda pid,exc:errors.append(str(exc))), '')
            self.assertEqual(errors, ['offline'])

    def test_agent_injects_memory_only_in_request_and_queues_completed_text(self):
        from types import SimpleNamespace
        from sunday_blue.agent import Agent
        shutil.copytree(ROOT/'extensions/plugins/livingmemory', self.root/'extensions/plugins/livingmemory')
        self.config.value['roles']['rui'].setdefault('native_plugins',{})['livingmemory'] = True
        sid = self.store.create('rui')
        self.store.add(sid,'user','我喝茶加糖吗？')
        fake_brain = SimpleNamespace(call=lambda *args,**kwargs: {'count':1, 'text':'旧记忆：喝茶不加糖。'})
        with patch('sunday_blue.living_memory.get_brain',return_value=fake_brain), \
             patch('sunday_blue.agent.Provider.complete',return_value=([{'type':'text','text':'你说过不加糖。'}],{},'end_turn')) as complete:
            Agent(self.root,self.config.snapshot(),self.store,sid)._run()
        self.assertIn('旧记忆：喝茶不加糖。',complete.call_args.args[0])
        self.assertNotIn('旧记忆',json.dumps(self.store.messages(sid),ensure_ascii=False))
        self.assertEqual(pending_count(self.root,'rui'),1)


class EditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_edit_confirmed_memory_and_persona_preview(self):
        from PySide6.QtWidgets import QDialog
        from sunday_blue.memory_editor import MemoryEditor
        from sunday_blue.persona_preferences import PersonaDialog
        from sunday_blue.change_review import ChangeReview
        from PySide6.QtCore import QTimer
        with tempfile.TemporaryDirectory(prefix='sunday-test-',dir=ROOT/'tests') as temp:
            root = Path(temp)
            config = Config(root)
            store = Store(config.data)
            shutil.copytree(ROOT/'personas',root/'personas')
            editor = MemoryEditor(root, 'rui', store)
            self.assertFalse(editor.editor.isReadOnly())
            editor.editor.setPlainText('用户确认：喜欢乌龙茶。')
            with patch.object(editor, 'review', return_value=True):
                editor.save()
            self.assertIn('乌龙茶', (config.data/'memory/rui/long_term.md').read_text(encoding='utf-8'))
            self.assertTrue(list((config.data/'backups').glob('*.bak')))
            dialog = PersonaDialog(root, 'rui')
            from sunday_blue.theme import style_for
            dialog.setStyleSheet(style_for('dark'))
            dialog.show()
            dialog.sections.setCurrentRow(2)
            dialog.editor.setPlainText('用轻松而清晰的语言。')
            seen = []
            def confirm():
                modal = self.app.activeModalWidget()
                if isinstance(modal,QDialog) and modal is not dialog:
                    seen.append(bool(modal.findChildren(ChangeReview)))
                    modal.accept()
            timer = QTimer()
            timer.timeout.connect(confirm)
            timer.start(20)
            dialog.review_save()
            timer.stop()
            self.assertTrue(all(seen) and seen)
            self.assertEqual(read_persona(root,'rui')['voice.md'], '用轻松而清晰的语言。')
            dialog.grab().save(str(ROOT/'docs/persona-editor-preview.png'))
            dialog.close()
            editor.deleteLater()
            dialog.deleteLater()
            self.app.processEvents()

    def test_memory_panel_monitor_does_not_start_ollama(self):
        import time
        from PySide6.QtTest import QTest
        from PySide6.QtCore import Qt
        from sunday_blue.memory_preferences import MemoryPanel, _jobs
        with tempfile.TemporaryDirectory(prefix='sunday-test-',dir=ROOT/'tests') as temp:
            root = Path(temp)
            config = Config(root)
            with patch('sunday_blue.memory_preferences.ollama_status',return_value={
                    'online':False,'model_ready':False,'models':[],'owned':False}), \
                 patch('sunday_blue.memory_preferences.start_ollama',return_value={'online':True}) as start:
                panel = MemoryPanel(root,config=config)
                from sunday_blue.theme import style_for
                panel.setStyleSheet(style_for('dark'))
                panel.resize(900,280)
                panel.show()
                def wait():
                    deadline=time.monotonic()+3
                    while (_jobs or panel.busy) and time.monotonic()<deadline:
                        self.app.processEvents()
                        QTest.qWait(10)
                    self.assertFalse(panel.busy)
                self.app.processEvents()
                wait()
                start.assert_not_called()
                panel.enable_memory.setChecked(True)
                self.assertTrue(Config(root).value['roles']['rui']['native_plugins']['livingmemory'])
                panel.roles.setCurrentIndex(panel.roles.findData('red'))
                self.assertFalse(panel.enable_memory.isChecked())
                panel.grab().save(str(ROOT/'docs/memory-controls-preview.png'))
                QTest.mouseClick(panel.buttons[1],Qt.MouseButton.LeftButton)
                wait()
                start.assert_called_once_with(root)
                panel.close()
                panel.deleteLater()
                self.app.processEvents()
