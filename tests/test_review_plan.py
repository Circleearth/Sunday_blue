import unittest,tempfile
from pathlib import Path
from datetime import date,timedelta
from sunday_blue.modules.database import ModuleDB
from sunday_blue.modules.learning import Learning
from sunday_blue.modules.review_plan import ReviewPlan
class ReviewTests(unittest.TestCase):
 def test_cycle_and_duplicate_guard(self):
  with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as root:
   db=ModuleDB(root);learning=Learning(db);course=learning.add('subject','璇剧▼');chapter=learning.add('chapter','绔犺妭',course);unit=learning.add('unit','鐭ヨ瘑',chapter);p=ReviewPlan(db);key=p.add(unit);p.add(unit);self.assertEqual(len(p.rows()),1)
   with self.assertRaises(ValueError):p.answer(key,'记住')
   with db.connect() as c:c.execute('UPDATE review_plan SET due=?',(date.today().isoformat(),))
   p.answer(key,'记住');self.assertEqual(p.rows()[0]['due'],(date.today()+timedelta(days=3)).isoformat());self.assertEqual(len(p.history(key)),1)
   with self.assertRaises(ValueError):p.answer(key,'记住')

 def test_work_order_and_calendar(self):
  from sunday_blue.modules.work import Work
  from sunday_blue.modules.day_plan import plan
  with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as root:
   db=ModuleDB(root);w=Work(db);a=w.create('A');b=w.create('B');w.reorder([b,a]);self.assertEqual([r['id'] for r in w.tasks()],[b,a]);db.set('day_plan:2026-11-17','late');self.assertTrue(any('游戏' in title for _,title in plan(db,'2026-11-17')))
 def test_hide_and_restore_keep_data(self):
  with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as root:
   db=ModuleDB(root);l=Learning(db);a=l.add('subject','课程');b=l.add('chapter','章节',a);u=l.add('unit','知识',b);l.hide(b)
   with db.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM learning_hidden').fetchone()[0],2);self.assertEqual(c.execute('SELECT count(*) FROM learning_nodes').fetchone()[0],3)
   l.restore_hidden()
   with db.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM learning_hidden').fetchone()[0],0)
