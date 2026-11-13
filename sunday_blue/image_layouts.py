"""External image references and non-destructive framing shared by every art slot."""
import json
from pathlib import Path
from PySide6.QtCore import QObject,Signal,Qt,QRectF,QSize
from PySide6.QtGui import QPixmap,QPainter,QColor
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QPushButton,QDialog,QFileDialog,QSlider,QLabel,QMessageBox
class ArtEvents(QObject):changed=Signal(str,str)
EVENTS=ArtEvents()
def selection(root,key):
 try:return json.loads((Path(root)/'data/image_layouts.json').read_text(encoding='utf-8')).get(key,{})
 except (OSError,ValueError):return {}
def save_selection(root,key,value):
 path=Path(root)/'data/image_layouts.json';path.parent.mkdir(parents=True,exist_ok=True)
 try:data=json.loads(path.read_text(encoding='utf-8'))
 except FileNotFoundError:data={}
 data[key]=value;temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(path);EVENTS.changed.emit(str(root),key)
def paint_image(p,rect,pix,cfg):
 if pix.isNull():return
 factor=min(rect.width()/pix.width(),rect.height()/pix.height())*cfg.get('zoom',1)
 w,h=pix.width()*factor,pix.height()*factor
 target=QRectF(rect.center().x()-w/2+cfg.get('x',0)*rect.width(),rect.center().y()-h/2+cfg.get('y',0)*rect.height(),w,h)
 p.save();p.setClipRect(rect);p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform);p.drawPixmap(target,pix,QRectF(pix.rect()));p.restore()
def framed(root,key,fallback,size):
 cfg=selection(root,key);pix=QPixmap(cfg.get('path',str(fallback)))
 if pix.isNull():pix=QPixmap(str(fallback))
 if pix.isNull():return pix
 out=QPixmap(size);out.fill(Qt.GlobalColor.transparent);p=QPainter(out);paint_image(p,QRectF(out.rect()),pix,cfg);p.end();return out
class Preview(QWidget):
 def __init__(self,pix,cfg,ratio):
  super().__init__();self.pix=pix;self.cfg=dict(cfg);self.ratio=ratio;self.start=None;self.setMinimumSize(250,200)
 def area(self):
  w=min(self.width(),self.height()*self.ratio);h=w/self.ratio;return QRectF((self.width()-w)/2,(self.height()-h)/2,w,h)
 def paintEvent(self,e):
  p=QPainter(self);p.fillRect(self.rect(),QColor('#dce1e8'));p.fillRect(self.area(),QColor('#fafafa'));paint_image(p,self.area(),self.pix,self.cfg);p.setPen(QColor('#7085ac'));p.drawRect(self.area())
 def mousePressEvent(self,e):self.start=e.position()
 def mouseMoveEvent(self,e):
  if self.start is None:return
  delta=e.position()-self.start;self.start=e.position();r=self.area();self.cfg['x']=max(-2,min(2,self.cfg.get('x',0)+delta.x()/r.width()));self.cfg['y']=max(-2,min(2,self.cfg.get('y',0)+delta.y()/r.height()));self.update()
 def mouseReleaseEvent(self,e):self.start=None

def edit_image(parent,root,key,fallback,ratio=1):
 cfg=selection(root,key);pix=QPixmap(cfg.get('path',str(fallback)));dlg=QDialog(parent);dlg.setWindowTitle('选择图片与调整构图');available=dlg.screen().availableGeometry();dlg.resize(min(620,available.width()-40),min(600,available.height()-40));box=QVBoxLayout(dlg)
 preview=Preview(pix,cfg,ratio);box.addWidget(preview,1);hint=QLabel('拖动图片调整位置，滑动缩放；只保存路径和构图，不修改原图。');hint.setWordWrap(True);box.addWidget(hint)
 zoom=QSlider(Qt.Orientation.Horizontal);zoom.setRange(10,500);zoom.setValue(round(cfg.get('zoom',1)*100));zoom.valueChanged.connect(lambda v:(preview.cfg.update(zoom=v/100),preview.update()));box.addWidget(zoom)
 row=QHBoxLayout();box.addLayout(row)
 def choose():
  path,_=QFileDialog.getOpenFileName(dlg,'选择图片',str(Path(cfg.get('path',str(fallback))).parent),'图片 (*.png *.jpg *.jpeg *.webp *.bmp)')
  if not path:return
  image=QPixmap(path)
  if image.isNull():QMessageBox.warning(dlg,'无法读取','请选择可读取的图片。');return
  preview.pix=image;preview.cfg={'path':str(Path(path).resolve()),'zoom':1,'x':0,'y':0};zoom.setValue(100);preview.update()
 def reset():preview.cfg.update(zoom=1,x=0,y=0);zoom.setValue(100);preview.update()
 def defaults():preview.cfg={'zoom':1,'x':0,'y':0};preview.pix=QPixmap(str(fallback));zoom.setValue(100);preview.update()
 def save():
  try:save_selection(root,key,preview.cfg)
  except (OSError,ValueError) as exc:QMessageBox.warning(dlg,'未保存',str(exc));return
  dlg.accept()
 for text,fn in [('选择图片',choose),('重置构图',reset),('默认图片',defaults),('保存',save),('取消',dlg.reject)]:
  b=QPushButton(text);b.clicked.connect(fn);row.addWidget(b)
 dlg.exec()
class EditableImage(QWidget):
 def __init__(self,root,key,fallback,title='选择图片 / 调整',ratio=1,parent=None):
  super().__init__(parent);self.root=root;self.key=key;self.fallback=fallback;self.ratio=ratio;self.setMinimumHeight(70);layout=QVBoxLayout(self);layout.setContentsMargins(4,4,4,4);layout.addStretch();b=QPushButton(title);b.clicked.connect(self.edit);layout.addWidget(b,0,Qt.AlignmentFlag.AlignRight);EVENTS.changed.connect(self.changed);self.reload()
 def changed(self,root,key):
  if root==str(self.root) and key==self.key:self.reload()
 def reload(self):
  self.cfg=selection(self.root,self.key);self.pix=QPixmap(self.cfg.get('path',str(self.fallback)))
  if self.pix.isNull():self.pix=QPixmap(str(self.fallback))
  self.update()
 def set_slot(self,key,fallback):self.key=key;self.fallback=fallback;self.reload()
 def edit(self):edit_image(self,self.root,self.key,self.fallback,self.ratio)
 def paintEvent(self,e):
  p=QPainter(self);p.fillRect(self.rect(),QColor('#edf1f4'));w=min(self.width(),self.height()*self.ratio);h=w/self.ratio;rect=QRectF((self.width()-w)/2,(self.height()-h)/2,w,h);paint_image(p,rect,self.pix,self.cfg)
