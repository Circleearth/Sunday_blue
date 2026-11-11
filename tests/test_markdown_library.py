import tempfile,threading,time,unittest,shutil
from pathlib import Path
from PySide6.QtCore import QObject,Signal,QUrl,QCoreApplication,QEvent
from PySide6.QtWidgets import QApplication
from sunday_blue.storage import Config
from sunday_blue.modules.database import ModuleDB
from sunday_blue.modules.markdown_library import MarkdownLibrary,MAX_DOCUMENT
from sunday_blue.module_views.markdown_reader import MarkdownPage
from sunday_blue.modules.duties import Duties
from sunday_blue.modules.organizer import Organizer
from sunday_blue.capabilities import TurnCapabilities
from sunday_blue.settings import Settings
ROOT=Path(__file__).resolve().parents[1]
APP=QApplication.instance() or QApplication([])
class Hub(QObject):
 changed=Signal(str);closed=Signal()
class MarkdownTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'tests',prefix='sunday-test-');self.root=Path(self.tmp.name);self.cfg=Config(self.root)
  self.db=ModuleDB(self.root);self.library=MarkdownLibrary(self.db);self.docs=self.root/'library';self.docs.mkdir()
  (self.docs/'note.md').write_text('# 项目笔记\n\n## 本周目标\n\n记录原文与 source token\n\n- [ ] 待办\n\n[下一篇](second.md)\n',encoding='utf-8')
  (self.docs/'second.md').write_text('# 第二篇\n\n| 主题 | 状态 |\n|---|---|\n| 测试 | 完成 |',encoding='utf-8')
  self.library.set_root(self.docs)
 def tearDown(self):
  APP.processEvents();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.tmp.cleanup()
 def test_scope_encoding_and_bounded_search(self):
  self.assertIn('项目笔记',self.library.read(self.docs/'note.md')[1]);self.assertTrue(self.library.preferences()['recent'])
  outside=self.root/'outside.md';outside.write_text('private',encoding='utf-8')
  with self.assertRaises(PermissionError):self.library.read(outside)
  large=self.docs/'large.md';large.write_bytes(b'x'*(MAX_DOCUMENT+1))
  with self.assertRaises(ValueError):self.library.read(large)
  rows,limited=self.library.search('source token',self.docs,threading.Event());self.assertEqual(len(rows),1);self.assertFalse(limited)
  self.library.favorite(self.docs/'note.md');self.assertEqual(len(self.library.preferences()['favorites']),1)
  self.library.favorite(self.docs/'note.md');self.assertEqual(self.library.preferences()['favorites'],[])
 def test_reader_outline_links_async_search_and_remote_block(self):
  h=Hub();h.db=self.db;h.config=self.cfg;page=MarkdownPage(h);page.open_file(self.docs/'note.md');self.assertEqual(page.outline.count(),2)
  self.assertIn('本周目标',page.reader.toPlainText());self.assertIn('# 项目笔记',page.source.toPlainText())
  self.assertIsNone(page.reader.loadResource(2,QUrl('https://example.test/tracker.png')))
  page.link(QUrl('second.md'));self.assertEqual(page.current.name,'second.md');page.go_back();self.assertEqual(page.current.name,'note.md')
  page.search.setText('source token');start=time.monotonic();page.start_search();self.assertLess(time.monotonic()-start,.5)
  end=time.monotonic()+3
  while page.results.count()==0 and time.monotonic()<end:APP.processEvents();time.sleep(.01)
  self.assertEqual(page.results.count(),1);h.closed.emit();page.deleteLater();h.deleteLater()
 def test_skill_bootstrap_and_settings_location(self):
  target=self.root/'extensions/skills/markdown-writing';target.mkdir(parents=True);shutil.copyfile(ROOT/'extensions/skills/markdown-writing/SKILL.md',target/'SKILL.md')
  duties=Duties(self.db);duties.assign('organizer','mia')
  for role in ('kia','mia'):
   routing=TurnCapabilities(self.root,self.cfg.snapshot(),role,'整理 Markdown 文件');self.assertIn('skill:markdown-writing',routing.active)
   quiet=TurnCapabilities(self.root,self.cfg.snapshot(),role,'你好');self.assertNotIn('skill:markdown-writing',quiet.active)
  duties.set_extensions('organizer',[],[]);Duties(self.db);self.assertEqual(next(s for s in duties.slots() if s['id']=='organizer')['extensions']['skills'],[])
  settings=Settings(self.cfg,'rui');self.assertIn('职责与交接',[settings.nav.item(i).text() for i in range(settings.nav.count())]);self.assertEqual(settings.duties_page.slots.topLevelItemCount(),7)
  settings.close();settings.deleteLater()
