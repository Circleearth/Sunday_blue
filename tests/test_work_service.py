import math,tempfile,unittest
from pathlib import Path
from sunday_blue.modules.database import ModuleDB
from sunday_blue.modules.work import Work
ROOT=Path(__file__).resolve().parents[1]
class WorkTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'tests',prefix='sunday-test-');self.db=ModuleDB(self.temp.name);self.work=Work(self.db)
    def tearDown(self):self.temp.cleanup()
    def binding(self,tid):
        with self.db.connect() as db:return Work.validate_binding(db,tid)
    def tables(self):
        with self.db.connect() as db:
            db.executescript('CREATE TABLE focus_runs(id TEXT PRIMARY KEY,state TEXT); CREATE TABLE focus_task_links(run_id TEXT PRIMARY KEY,task_id TEXT,title TEXT,progress_start REAL); CREATE TABLE activity_records(id TEXT PRIMARY KEY,seconds REAL);')
    def test_hierarchy_weighted_progress_is_not_time(self):
        parent=self.work.create('release');a=self.work.create('code',parent,estimate_minutes=30);b=self.work.create('review',parent,estimate_minutes=90)
        with self.assertRaises(ValueError):self.work.create('too deep',a)
        self.work.update(a,progress=100);self.assertEqual(self.work.task(a)['status'],'done');self.assertEqual(self.work.task(parent)['progress'],25)
        self.tables()
        with self.db.connect() as db:
            db.execute('INSERT INTO focus_task_links VALUES(?,?,?,?)',('run',b,'review',0));db.execute('INSERT INTO activity_records VALUES(?,?)',('run',600))
        self.assertEqual(self.work.task(parent)['actual_seconds'],600);self.assertEqual(self.work.task(parent)['progress'],25)
        with self.assertRaises(ValueError):self.binding(parent)
        with self.assertRaises(ValueError):self.work.update(parent,progress=99)
        with self.assertRaises(ValueError):self.work.update(parent,status='done')
        self.work.update(b,progress=99.9999);self.assertLess(self.work.task(parent)['progress'],100)
        with self.assertRaises(ValueError):self.work.update(parent,status='done')
        self.work.update(b,status='done');self.assertEqual(self.work.task(parent)['progress'],100)
    def test_archive_preserves_history_and_busy_guard(self):
        parent=self.work.create('project');child=self.work.create('part',parent);self.tables()
        with self.db.connect() as db:
            db.execute('INSERT INTO focus_runs VALUES(?,?)',('r','paused'));db.execute('INSERT INTO focus_task_links VALUES(?,?,?,?)',('r',child,'part',0))
        with self.assertRaises(ValueError):self.work.archive(parent)
        with self.db.connect() as db:db.execute("UPDATE focus_runs SET state='finished'");db.execute('INSERT INTO activity_records VALUES(?,?)',('r',300))
        self.work.archive(parent);self.assertEqual(self.work.tasks(),[]);self.assertEqual(len(self.work.tasks(True)),2);self.assertEqual(self.work.task(parent)['actual_seconds'],300)
        self.assertTrue(self.work.history(child));self.assertEqual(Work(ModuleDB(self.temp.name)).task(child)['archived'],1)
        with self.assertRaises(ValueError):self.work.archive(child,False)
        self.work.archive(parent,False);self.assertEqual(len(self.work.tasks()),2)
    def test_noop_events_and_external_id_unique(self):
        a=self.work.create('a',dida_id='dida-stable');before=len(self.db.events('test'))
        self.work.update(a,title='a');self.assertEqual(len(self.db.events('test')),before)
        with self.assertRaises(ValueError):self.work.create('b',dida_id='dida-stable')
        b=self.work.create('b')
        with self.assertRaises(ValueError):self.work.update(b,dida_id='dida-stable')
        self.work.update(a,title='renamed',progress=35);self.assertEqual(self.work.task(a)['dida_id'],'dida-stable');self.assertEqual(len(self.work.history(a)),2)
        self.work.archive(a)
        with self.assertRaises(ValueError):self.work.create('replacement',dida_id='dida-stable')
    def test_numeric_validation_and_status(self):
        for invalid in (True,float('nan'),float('inf'),-1,'25'):
            with self.assertRaises(ValueError):self.work.create('bad',estimate_minutes=invalid)
        t=self.work.create('ok')
        for values in ({'progress':101},{'progress':True},{'priority':4},{'priority':1.5},{'due':'yesterday'},{'parent_id':'x'}):
            with self.assertRaises(ValueError):self.work.update(t,**values)
        self.work.update(t,status='done');self.assertEqual(self.work.task(t)['progress'],100)
        with self.assertRaises(ValueError):self.binding(t)
        self.work.update(t,progress=50);self.assertEqual(self.work.task(t)['status'],'doing')
        self.work.update(t,status='paused')
        with self.assertRaises(ValueError):self.binding(t)
    def test_suggest_and_parent_guard(self):
        later=self.work.create('later',due='2026-12-01',priority=3);early=self.work.create('early',due='2026-11-15',priority=0)
        parent=self.work.create('parent');child=self.work.create('child',parent,due='2026-11-01')
        self.work.update(parent,status='paused');self.assertEqual([r['id'] for r in self.work.suggest()],[early,later])
        with self.assertRaises(ValueError):self.binding(child)
        self.tables()
        with self.db.connect() as db:db.execute('INSERT INTO focus_runs VALUES(?,?)',('run','running'));db.execute('INSERT INTO focus_task_links VALUES(?,?,?,?)',('run',early,'early',0))
        with self.assertRaises(ValueError):self.work.create('unsafe new child',early)
    def test_parent_history_before_subtasks_still_counts(self):
        p=self.work.create('task');self.tables()
        with self.db.connect() as db:db.execute('INSERT INTO focus_task_links VALUES(?,?,?,?)',('r',p,'old name',0));db.execute('INSERT INTO activity_records VALUES(?,?)',('r',420))
        self.work.create('new subtask',p);self.work.update(p,title='new name');self.assertEqual(self.work.task(p)['actual_seconds'],420)
        with self.db.connect() as db:self.assertEqual(db.execute('SELECT title FROM focus_task_links').fetchone()[0],'old name')

    def test_reopening_child_reopens_completed_parent_atomically(self):
        parent=self.work.create('project');child=self.work.create('part',parent)
        self.work.update(child,status='done')
        self.assertEqual(self.work.task(parent)['status'],'done')
        with self.db.connect() as db:self.assertEqual(db.execute('SELECT status FROM work_tasks WHERE id=?',(parent,)).fetchone()[0],'todo')
        self.work.update(parent,status='done');self.work.update(child,progress=40)
        row=self.work.task(parent);self.assertEqual((row['status'],row['progress']),('doing',40))
        with self.db.connect() as db:self.assertEqual(db.execute('SELECT status FROM work_tasks WHERE id=?',(parent,)).fetchone()[0],'doing')
        self.assertEqual(self.binding(child)['id'],child)
        correction=self.work.history(parent)[0]
        self.assertEqual(correction['kind'],'child_reopened');self.assertEqual(correction['payload']['child_id'],child)
        self.assertEqual(correction['payload']['before']['status'],'done')
