"""Read-only recovery visualizations. No database writes, reward rules or model calls."""
from datetime import date
import json
from PySide6.QtCore import Qt,QRectF,QPointF,Signal
from PySide6.QtGui import QPainter,QPainterPath,QColor,QPen,QFont,QPixmap
from PySide6.QtWidgets import QWidget,QFrame,QVBoxLayout,QHBoxLayout,QLabel,QProgressBar,QToolTip,QSizePolicy
from ..art_assets import asset_spec
from ..modules.life_state import DEFAULT_PARTS

from ..design_system import RECOVERY_COLORS,RECOVERY_LABELS,STATE_ACCENTS

def label(text='',name='muted'):
    w=QLabel(text);w.setObjectName(name);w.setWordWrap(True);return w

def card(title=''):
    w=QFrame();w.setObjectName('card');box=QVBoxLayout(w);box.setContentsMargins(18,16,18,16);box.setSpacing(12)
    if title:box.addWidget(label(title,'cardTitle'))
    return w,box

class StatusCard(QFrame):
    def __init__(self,title,parent=None):
        super().__init__(parent);self.setObjectName('card');box=QVBoxLayout(self);box.setContentsMargins(18,16,18,16);box.setSpacing(8)
        top=QHBoxLayout();top.addWidget(label(title,'cardTitle'));top.addStretch();self.badge=label();top.addWidget(self.badge);box.addLayout(top)
        numbers=QHBoxLayout();self.number=label('—','lifeNumber');self.limit=label();numbers.addWidget(self.number);numbers.addWidget(self.limit);numbers.addStretch();box.addLayout(numbers)
        self.bar=QProgressBar();self.bar.setRange(0,1000);self.bar.setTextVisible(False);self.bar.setFixedHeight(7);box.addWidget(self.bar)
        self.note=label();box.addWidget(self.note);self.setMinimumWidth(180)
    def set_state(self,value,cap,percent,note,inverted=False):
        quality=100-percent if inverted else percent
        color=STATE_ACCENTS['ready' if quality>=65 else 'caution' if quality>=40 else 'rest']
        self.number.setText(f'{value:g}');self.limit.setText(f'/ {cap:g}'+(' %' if inverted else ' 点'))
        self.badge.setText(('轻松' if quality>=65 else '留意' if quality>=40 else '先恢复') if inverted else ('可用' if quality>=65 else '放慢' if quality>=40 else '偏低'))
        self.bar.setValue(round(percent*10));self.bar.setStyleSheet(f'QProgressBar::chunk {{background:{color};border-radius:3px;}}')
        self.note.setText(note)

def recovery_rows(states,exercises,today):
    """Keep domain recovery colors; enrich with factual latest training. Missing data stays unknown.
    Domain currently uses day-level decay; intensity is shown, not invented into a new medical model.
    """
    result=[]
    for state in states:
        found=[]
        for r in exercises:
            if r['day']>today:continue
            parts=json.loads(r.get('muscles') or '[]') or DEFAULT_PARTS.get(r['kind'],[])
            if state['part'] in parts:found.append(r)
        latest=max(found,key=lambda r:r['day']) if found else None
        row=dict(state);row['latest']=latest
        if not latest:row['level']='unknown'
        row['status']=RECOVERY_LABELS[row['level']]
        if latest:
            age=(date.fromisoformat(today)-date.fromisoformat(latest['day'])).days
            row['detail']=f"{state['part']} · {row['status']}\n最近：{latest['day']} · {latest['kind']}\n{latest['minutes']:g} 分钟 / {dict(light='轻',moderate='中',high='高').get(latest['intensity'],'未知')}强度 · 距今 {age} 天\n颜色沿用逐日恢复规则；强度与身体感受请一起考虑。"
        else:row['detail']=f"{state['part']} · 数据不足\n最近 200 条运动记录未找到对应部位。未记录不等于没有训练。"
        result.append(row)
    return result

class MuscleMap(QWidget):
    selected=Signal(str)
    def __init__(self,root,parent=None):
        super().__init__(parent);self.rows={};self.regions=[];self.active='';self.setMouseTracking(True);self.setMinimumSize(310,300);self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding)
        self.pixmap=QPixmap(str(asset_spec(root,'recovery_body')['file']));self._build()
        self.setAccessibleName('正面与背面肌群恢复图；也可使用下方部位按钮选择')
    def _build(self):
        def polygon(points):
            p=QPainterPath(QPointF(*points[0]))
            for v in points[1:]:p.lineTo(*v)
            p.closeSubpath();return p
        self.bodies=[]
        for ox in (15,235):
            outline=[(86,66),(69,73),(56,84),(45,126),(33,173),(43,178),(65,136),(71,113),(76,158),(68,184),(70,235),(73,292),(88,292),(98,221),(110,292),(125,292),(128,235),(130,184),(121,158),(127,113),(134,136),(154,178),(164,173),(152,126),(140,84),(128,73),(111,66)]
            self.bodies.append(polygon([(x+ox,y) for x,y in outline]))
            groups={
              '肩':[[(69,77),(82,78),(77,97),(61,102),(60,90)],[(116,78),(130,77),(139,90),(137,102),(122,97)]],
              ('二头肌' if ox==15 else '三头肌'):[[(60,104),(74,100),(68,126),(57,140),(50,135)],[(123,100),(137,104),(147,135),(140,140),(129,126)]],
            }
            if ox==15:
                groups['胸']=[[(83,80),(97,83),(97,111),(78,108),(77,98)],[(101,83),(115,80),(121,98),(119,108),(101,111)]]
                groups['核心']=[[(80,115),(97,116),(97,164),(85,164),(79,150)],[(101,116),(118,115),(119,150),(113,164),(101,164)]]
            else:groups['背']=[[(82,82),(97,88),(97,153),(86,162),(78,117)],[(101,88),(116,82),(121,117),(113,162),(101,153)]]
            for key,parts in groups.items():
                for pts in parts:self.regions.append((key,polygon([(x+ox,y) for x,y in pts])))
    def set_rows(self,rows):self.rows={r['part']:r for r in rows};self.update()
    def transform_info(self):
        scale=min(self.width()/440,self.height()/330);return scale,(self.width()-440*scale)/2,(self.height()-330*scale)/2
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing);s,x,y=self.transform_info();p.translate(x,y);p.scale(s,s)
        if not self.pixmap.isNull():
            size=self.pixmap.size();size.scale(440,330,Qt.AspectRatioMode.KeepAspectRatio)
            p.drawPixmap(QRectF((440-size.width())/2,(330-size.height())/2,size.width(),size.height()),self.pixmap,QRectF(self.pixmap.rect()))
        else:
            p.setPen(QPen(QColor('#b7c3ca'),1.2));p.setBrush(QColor('#edf0f2'))
            for i,body in enumerate(self.bodies):p.drawPath(body);p.drawEllipse(QRectF(93+i*220,23,43,43))
        for key,path in self.regions:
            color=RECOVERY_COLORS[self.rows.get(key,{}).get('level','unknown')];p.setBrush(QColor(color));p.setPen(QPen(QColor('#768a9c') if key==self.active else QColor('#ffffff'),2 if key==self.active else 1.5));p.drawPath(path)
        p.setPen(QColor('#788390'));font=QFont(self.font());font.setPixelSize(12);p.setFont(font)
        p.drawText(QRectF(15,302,200,24),Qt.AlignmentFlag.AlignCenter,'正面');p.drawText(QRectF(235,302,200,24),Qt.AlignmentFlag.AlignCenter,'背面')
    def part_at(self,point):
        s,x,y=self.transform_info();point=QPointF((point.x()-x)/s,(point.y()-y)/s)
        return next((key for key,path in self.regions if path.contains(point)),'')
    def mouseMoveEvent(self,event):
        key=self.part_at(event.position())
        if key!=self.active:self.active=key;self.update()
        if key:QToolTip.showText(event.globalPosition().toPoint(),self.rows.get(key,{}).get('detail',key),self)
        else:QToolTip.hideText()
    def leaveEvent(self,event):self.active='';self.update();QToolTip.hideText()
    def mousePressEvent(self,event):
        key=self.part_at(event.position())
        if key:self.selected.emit(key)

class TrendChart(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self.rows=[];self.setMinimumHeight(240);self.setMouseTracking(True)
    def set_rows(self,rows):self.rows=list(rows);self.update()
    def count(self):return len(self.rows)
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing);area=self.rect().adjusted(38,25,-20,-35)
        p.setPen(QColor('#98a3b0'));font=QFont(self.font());font.setPixelSize(11);p.setFont(font)
        for value in (0,50,100):
            y=area.bottom()-area.height()*value/100;p.drawText(QRectF(0,y-9,30,18),Qt.AlignmentFlag.AlignRight,str(value));p.setPen(QColor('#e1e5eb'));p.drawLine(QPointF(area.left(),y),QPointF(area.right(),y));p.setPen(QColor('#98a3b0'))
        for key,color in [('physical','#76a38d'),('focus','#8794cb'),('eye_strain','#c6a567')]:
            path=QPainterPath()
            for i,r in enumerate(self.rows):
                x=area.left()+i*area.width()/max(1,len(self.rows)-1);y=area.bottom()-r[key]*area.height()/100
                if i:path.lineTo(x,y)
                else:path.moveTo(x,y)
            p.setPen(QPen(QColor(color),2.5));p.drawPath(path)
        p.setPen(QColor('#98a3b0'))
        for i,r in enumerate(self.rows):
            x=area.left()+i*area.width()/max(1,len(self.rows)-1);p.drawText(QRectF(x-25,area.bottom()+8,50,22),Qt.AlignmentFlag.AlignCenter,r['day'][5:])
    def mouseMoveEvent(self,event):
        if not self.rows:return
        i=round((event.position().x()-38)/max(1,self.width()-58)*(len(self.rows)-1));r=self.rows[max(0,min(len(self.rows)-1,i))]
        QToolTip.showText(event.globalPosition().toPoint(),f"{r['day']}\n体力 {r['physical']}% · 专注 {r['focus']}% · 视疲劳 {r['eye_strain']}%\n均为规则估计",self)
