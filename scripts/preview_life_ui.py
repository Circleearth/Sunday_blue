"""Native Qt preview of only the redesigned life pages, with synthetic records."""
import sys,tempfile
from datetime import date,timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QPainter,QColor
from sunday_blue.storage import Config,Store
from sunday_blue.modules.hub import ModuleHub
from sunday_blue.module_views.life_work import LifePage
from sunday_blue.theme import style_for
app=QApplication([])
with tempfile.TemporaryDirectory(dir='tests',prefix='sunday-ui-') as d:
 c=Config(d);h=ModuleHub(c,Store(c.data),start_timer=False)
 h.life.exercise('力量训练',40,'high',day=date.today().isoformat(),muscles=['胸','二头肌'])
 h.life.exercise('力量训练',25,'light',day=(date.today()-timedelta(days=2)).isoformat(),muscles=['背','三头肌'])
 p=LifePage(h);p.setStyleSheet(style_for('light'));p.resize(1120,780);p.show();app.processEvents();p.grab().save('.cache/life-recovery-light.png')
 contact=QImage(1600,600,QImage.Format.Format_RGB32);contact.fill(QColor('white'));painter=QPainter(contact)
 for column,index in enumerate((1,2,3)):
  p.tabs.setCurrentIndex(index);p.resize(900,760);app.processEvents();pix=p.grab().scaled(530,590);pix.setDevicePixelRatio(1);painter.drawPixmap(column*533,0,pix)
 painter.end();contact.save('.cache/life-records-preview.png')
 p.tabs.setCurrentIndex(0);p.setStyleSheet(style_for('dark'));p.resize(760,780);app.processEvents();p.grab().save('.cache/life-recovery-dark.png')
 h.close();p.close()
