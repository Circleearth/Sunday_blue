"""Presentation components only; no session/database/provider ownership."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QColor, QPainter, QPen, QFont, QTextOption
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QPlainTextEdit, QTextBrowser
from .storage import ROLES

def text_label(text, name=None):
    w = QLabel(text)
    if name: w.setObjectName(name)
    return w

def button(text, callback, name=None):
    b = QPushButton(text)
    if name: b.setObjectName(name)
    b.clicked.connect(callback)
    return b

class TitleBar(QFrame):
    def mousePressEvent(self, event):
        if event.button()==Qt.MouseButton.LeftButton and self.window().windowHandle():
            self.window().windowHandle().startSystemMove()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            w=self.window()
            w.showNormal() if w.isMaximized() else w.showMaximized()

class Composer(QPlainTextEdit):
    send = Signal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self._composing = False
    def inputMethodEvent(self, event):
        self._composing = bool(event.preeditString())
        super().inputMethodEvent(event)
    def keyPressEvent(self,event):
        if not self._composing and event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter) and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.send.emit()
            return
        super().keyPressEvent(event)

class Portrait(QFrame):
    def __init__(self,root):
        super().__init__()
        self.root=root; self.role='rui'; self.pix=QPixmap(); self.tint=QColor('#7cb7ff')
        self.setObjectName('portrait'); self.setMinimumHeight(310)

    def set_role(self,role):
        self.role=role
        self.pix=QPixmap(str(self.root/'assets'/'roles'/role/'portrait.png'))
        self.tint=QColor(next(r[3] for r in ROLES if r[0]==role))
        self.update()

    def paintEvent(self,event):
        super().paintEvent(event)
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        width,height=self.width(),self.height()
        # Fine geometric framing leaves the entire central area for custom artwork.
        p.setPen(QPen(QColor('#3b4e68'),1))
        p.drawLine(20,44,width-20,44); p.drawLine(20,height-55,width-20,height-55)
        for x,y,dx,dy in [(10,10,1,1),(width-11,10,-1,1),(10,height-11,1,-1),(width-11,height-11,-1,-1)]:
            p.setPen(QPen(QColor('#bba77d'),2)); p.drawLine(x,y,x+20*dx,y); p.drawLine(x,y,x,y+20*dy)
        if not self.pix.isNull():
            pix=self.pix.scaled(max(1,width-28),max(1,height-90),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
            p.drawPixmap((width-pix.width())//2,48+(height-100-pix.height())//2,pix)
        p.setPen(QColor('#8c9cb2')); p.setFont(QFont('Segoe UI',9))
        p.drawText(22,29,'CHARACTER  /  '+self.role.upper())
        p.setPen(QColor('#677d9a'))
        p.drawText(self.rect().adjusted(22,0,-22,-17),Qt.AlignmentFlag.AlignBottom|Qt.AlignmentFlag.AlignHCenter,'S U N D A Y   B L U E')

class Bubble(QLabel):
    """A selectable label, never a nested scroll view. Height follows wrapped text."""
    def __init__(self,text,user=False,tool=False,light=False,width=0,font=None):
        super().__init__()
        self.user=user
        self.raw=''
        self._available=width or 600
        self.chat_font=font or QFont('Microsoft YaHei UI',12)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setMargin(12)
        self.set_theme(light)
        self.set_text(text)

    def set_theme(self,light):
        background=('#dbe7fb' if self.user else '#eef1f5') if light else ('#294761' if self.user else '#1b2a40')
        border='#b9cdea' if light else '#42637f'
        color='#1f2937' if light else '#e0e8f3'
        family=self.chat_font.family().replace('"','').replace('\\','')
        size=self.chat_font.pointSizeF()
        weight=int(self.chat_font.weight())
        self.setStyleSheet(f'QLabel {{background:{background}; border:1px solid {border}; border-radius:11px; color:{color}; font-family:"{family}"; font-size:{size}pt; font-weight:{weight};}}')
        self.setFont(self.chat_font)
        self.ensurePolished()
        self.fit()

    def set_text(self,text):
        self.raw=(text or '').replace('\r\n','\n').replace('\r','\n').strip()
        self.setText(self.raw)
        self.fit()

    def set_available_width(self,width):
        self._available=width
        self.fit()

    def fit(self,*args):
        cap=max(64,int(self._available*.8))
        longest=max((self.fontMetrics().horizontalAdvance(line) for line in self.raw.splitlines()),default=20)
        target=min(cap,max(64,longest+30))
        self.setFixedWidth(target)
        self.setFixedHeight(max(46,self.heightForWidth(target)+4))

    def toPlainText(self):
        return self.raw
