import tempfile,unittest
from pathlib import Path
from sunday_blue.modules.database import ModuleDB
from sunday_blue.modules.personal_notes import PersonalNotes
class NotesTests(unittest.TestCase):
 def test_unicode_original_paths_and_duplicates(self):
  with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as root:
   db=ModuleDB(root);s=PersonalNotes(db);body='  原文\n  另一行  ';a=s.save('灵感/杂念',body);b=s.save('灵感/杂念',body)
   self.assertNotEqual(a,b);self.assertTrue(Path(a).is_file());self.assertTrue(Path(a).read_text(encoding='utf-8').endswith(body));self.assertEqual(len(s.rows()),2);self.assertTrue(Path(a).is_relative_to(Path(root)))
 def test_directory_change_keeps_old(self):
  with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as root:
   db=ModuleDB(root);s=PersonalNotes(db);s.save('A','text');key=s.rows()[0]['id'];db.set('personal_notes_dir',str(Path(root)/'other'));s.save('B','second');self.assertIn('text',s.read(key))
