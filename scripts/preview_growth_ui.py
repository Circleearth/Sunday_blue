"""Synthetic native previews; never sends notifications or reads user records."""
import sys,tempfile
from pathlib import Path
from datetime import datetime,timedelta,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from sunday_blue.storage import Config,Store
from sunday_blue.modules.hub import ModuleHub
from sunday_blue.module_views.growth import GrowthPage
from sunday_blue.theme import style_for
app=QApplication([])
with tempfile.TemporaryDirectory(dir='tests',prefix='sunday-growth-') as root:
 c=Config(root);h=ModuleHub(c,Store(c.data),start_timer=False);s=h.learning.add('subject','高等数学');ch=h.learning.add('chapter','第一章 · 函数与极限',s)
 for title,total,correct in [('函数的连续性',12,12),('导数与链式法则',10,7),('极限的求解',0,0)]:
  u=h.learning.add('unit',title,ch);h.learning.assess(u,85)
  if total:h.learning.practice(u,total,correct,'注意复合函数的内外层关系' if total!=correct else '')
 h.contracts.sign('本周学习挑战','study_minutes',120,(datetime.now(timezone.utc)+timedelta(days=7)).isoformat(),1.5,1)
 p=GrowthPage(h);p.setStyleSheet(style_for('light'));p.resize(1120,740);p.show();app.processEvents();p.learning.tree.setCurrentItem(p.learning.tree.topLevelItem(0).child(0).child(1));app.processEvents();p.grab().save('.cache/learning-preview.png')
 p.tabs.setCurrentIndex(1);app.processEvents();p.grab().save('.cache/contracts-preview.png');h.close();p.close()
