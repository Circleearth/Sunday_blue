import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QMessageBox

from sunday_blue.modules.database import ModuleDB
from sunday_blue.modules.personal_notes import PersonalNotes
from sunday_blue.module_views.personal_notes import PersonalNotesPage


class Hub(QObject):
    closed = Signal()


class NotesEditorTests(unittest.TestCase):
    def test_edit_delete_restore_across_restart(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder:
            hub = Hub()
            hub.db = ModuleDB(folder)
            page = PersonalNotesPage(hub)
            page.new_button.click()
            page.title.setText("晨间")
            page.body.setPlainText("原文\n\n  第二段")
            page.save_button.click()
            key = page.key
            path = Path(page.service.row(key)["path"])
            page.new_button.click()
            page.title.setText("第二条")
            page.body.setPlainText("其他")
            page.save_button.click()
            page.items.setCurrentRow(1)
            self.assertEqual(page.key, key)
            page.title.setText("晨间笔记")
            page.body.insertPlainText("补充")
            with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Cancel):
                page.items.setCurrentRow(0)
            self.assertEqual(page.items.currentRow(), 1)
            page.save_button.click()
            self.assertEqual(page.key, key)
            self.assertIn("补充原文", path.read_text(encoding="utf-8"))
            page.delete_button.click()
            self.assertTrue(path.exists())
            page = PersonalNotesPage(hub)
            page.scope.setCurrentIndex(1)
            self.assertEqual(page.key, key)
            page.delete_button.click()
            self.assertEqual(page.scope.currentIndex(), 0)
            self.assertEqual(page.title.text(), "晨间笔记")
            page.body.setPlainText("草稿")
            page.store_draft()
            reopened = PersonalNotesPage(hub)
            self.assertEqual((reopened.key, reopened.body.toPlainText()), (key, "草稿"))
            self.assertTrue(reopened.save_button.isEnabled())
            app.processEvents()

    def test_legacy_and_external_edit_conflict(self):
        with tempfile.TemporaryDirectory() as folder:
            db = ModuleDB(folder)
            path = Path(folder) / "old.md"
            path.write_text("# Old\n\n记录时间：2025-01-01T00:00:00\n\n  original\n", encoding="utf-8")
            with db.connect() as conn:
                conn.execute("CREATE TABLE personal_notes(id TEXT PRIMARY KEY,title TEXT,path TEXT,created TEXT)")
                conn.execute("INSERT INTO personal_notes VALUES(?,?,?,?)", ("a", "Old", str(path), "2025-01-01T00:00:00"))
            notes = PersonalNotes(db)
            body, revision = notes.document("a")
            self.assertEqual(body, "  original\n")
            path.write_text("external", encoding="utf-8")
            with self.assertRaises(ValueError):
                notes.update("a", "new", "changed", revision)
            self.assertEqual(path.read_text(), "external")
