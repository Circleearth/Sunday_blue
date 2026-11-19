import unittest,tempfile
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication,QEvent,Qt,QMimeData,QPointF
from PySide6.QtGui import QDropEvent
from sunday_blue.storage import Config,Store
from sunday_blue.modules.hub import ModuleHub
from sunday_blue.modules.tree_moves import move
from sunday_blue.module_views.life_work import WorkPage
APP=QApplication.instance() or QApplication([])
class MoveTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=Path(__file__).parent);cfg=Config(self.tmp.name);self.h=ModuleHub(cfg,Store(cfg.data),start_timer=False);self.pages=[]
 def tearDown(self):
  self.h.close()
  for p in self.pages:p.close();p.deleteLater()
  self.h.deleteLater();APP.processEvents();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.tmp.cleanup()
 def test_work_move_cycle_order_and_repeat(self):
  w=self.h.work;a=w.create('A');b=w.create('B');c=w.create('C');child=w.create('child',a,notes='keep');move(self.h.db,'work',child,b);self.assertEqual(w.task(child)['parent_id'],b);self.assertEqual(w.task(child)['notes'],'keep')
  with self.assertRaises(ValueError):move(self.h.db,'work',b,child)
  move(self.h.db,'work',child,None,c);self.assertEqual(w.task(child)['parent_id'],None);self.assertEqual([r['id'] for r in w.tasks()],[a,b,child,c])
  for i in range(5):move(self.h.db,'work',a,None,c);move(self.h.db,'work',b,None,a)
  self.assertEqual({r['id'] for r in w.tasks()},{a,b,c,child})
 def test_learning_reparent_keeps_notes_and_review(self):
  l=self.h.learning;s=l.add('subject','S');a=l.add('chapter','A',s);b=l.add('chapter','B',s);u=l.add('unit','U',a);l.save_notebook(u,'saved',state='familiar')
  from sunday_blue.modules.review_plan import ReviewPlan
  r=ReviewPlan(self.h.db);key=r.add(u);move(self.h.db,'learning',u,b);self.assertEqual(l.notebook(u)['parent'],b);self.assertEqual(l.notebook(b)['progress'],100);self.assertEqual(l.notebook(a)['unit_count'],0);self.assertEqual(r.rows()[0]['id'],key)
  with self.assertRaises(ValueError):move(self.h.db,'learning',u,s)
  self.assertEqual(l.notebook(u)['note'],'saved')
 def test_drop_sorts_and_nests_immediately_without_lost_rows(self):
  w=self.h.work;ids=[w.create(v) for v in ('A','B','C')];p=WorkPage(self.h);self.pages.append(p);p.resize(1100,720);p.show();APP.processEvents()
  for source,target in [(ids[0],ids[1]),(ids[1],ids[2]),(ids[0],ids[2])]:
   def all_items(parent):
    for i in range(parent.childCount()):
     x=parent.child(i);yield x;yield from all_items(x)
   items={i.data(0,Qt.ItemDataRole.UserRole)['id']:i for i in all_items(p.tree.invisibleRootItem())};p.tree.setCurrentItem(items[source]);rect=p.tree.visualItemRect(items[target]);mime=QMimeData();mime.setData(p.tree.MIME,(p.tree.token+':'+source).encode());point=rect.center();point.setX(rect.right()-2) if source==ids[1] else None;event=QDropEvent(QPointF(point),Qt.DropAction.CopyAction|Qt.DropAction.MoveAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier);p.tree.dropEvent(event)
   self.assertTrue(event.isAccepted());self.assertEqual(event.dropAction(),Qt.DropAction.CopyAction);self.assertEqual(w.task(source)["parent_id"],target if source==ids[1] else None);self.assertEqual(len(list(all_items(p.tree.invisibleRootItem()))),3);self.assertEqual({r['id'] for r in w.tasks()},set(ids))
 def test_busy_guard(self):
  w=self.h.work;a=w.create('A');b=w.create('B');self.h.start_focus('工作','A','rui',task_id=a)
  with self.assertRaises(ValueError):move(self.h.db,'work',a,b)
  self.assertIsNone(w.task(a)['parent_id'])

 def test_learning_drop_reorders_and_moves_without_disappearance(self):
  from sunday_blue.module_views.learning_notebook import LearningPage
  l=self.h.learning;root=l.add('subject','course');chapter=l.add('chapter','chapter',root);other=l.add('chapter','other',root);ids=[l.add('unit',v,chapter) for v in ('A','B','C')];p=LearningPage(self.h);self.pages.append(p);p.resize(1100,720);p.show();APP.processEvents()
  for source,target in [(ids[0],ids[1]),(ids[1],ids[2]),(ids[0],other)]:
   p.tree.setCurrentItem(p.items[source]);rect=p.tree.visualItemRect(p.items[target]);mime=QMimeData();mime.setData(p.tree.MIME,(p.tree.token+':'+source).encode());event=QDropEvent(QPointF(rect.center()),Qt.DropAction.CopyAction|Qt.DropAction.MoveAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier);p.tree.dropEvent(event);self.assertEqual(event.dropAction(),Qt.DropAction.CopyAction);APP.processEvents();self.assertEqual(len(p.items),6)
  self.assertEqual(l.notebook(ids[0])['parent'],other);self.assertEqual({r['id'] for r in l.notebook_rows()},{root,chapter,other,*ids})
