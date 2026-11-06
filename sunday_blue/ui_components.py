"""Presentation components only; no session/database/provider ownership."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QColor, QPainter, QPen, QFont, QTextOption
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QPlainTextEdit, QTextBrowser
from .storage import ROLES
from .design_system import tokens

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
        self.root=root; self.role='rui'; self.pix=QPixmap(); self.tint=QColor('#7cb7ff'); self.theme='dark'
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
        t=tokens(self.theme);p.setPen(QPen(QColor(t['border_strong']),1))
        p.drawLine(20,44,width-20,44); p.drawLine(20,height-55,width-20,height-55)
        for x,y,dx,dy in [(10,10,1,1),(width-11,10,-1,1),(10,height-11,1,-1),(width-11,height-11,-1,-1)]:
            p.setPen(QPen(self.tint,2)); p.drawLine(x,y,x+14*dx,y); p.drawLine(x,y,x,y+14*dy)
        if not self.pix.isNull():
            pix=self.pix.scaled(max(1,width-28),max(1,height-90),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
            p.drawPixmap((width-pix.width())//2,48+(height-100-pix.height())//2,pix)
        p.setPen(QColor(t['text_muted'])); p.setFont(QFont('Noto Sans SC',9))
        p.drawText(22,29,'CHARACTER  /  '+self.role.upper())
        p.setPen(QColor(t['text_subtle']))
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
        self.setMargin(9)
        self.set_theme(light)
        self.set_text(text)

    def set_theme(self,light):
        t=tokens('light' if light is True or light=='light' else 'dark')
        background=t['user_bubble'] if self.user else t['assistant_bubble']
        border=t['bubble_border'];color=t['text']
        family=self.chat_font.family().replace('"','').replace('\\','')
        size=self.chat_font.pointSizeF()
        weight=int(self.chat_font.weight())
        self.setStyleSheet(f'QLabel {{background:{background}; border:1px solid {border}; border-radius:{t["radius_bubble"]}px; color:{color}; font-family:"{family}"; font-size:{size}pt; font-weight:{weight};}}')
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
        target=min(cap,max(56,longest+20))
        self.setFixedWidth(target)
        # QLabel heightForWidth otherwise clamps to the previous fixed minimum,
        # adding four pixels on every theme/resize/stream update.
        self.setMinimumHeight(0);self.setMaximumHeight(16777215)
        self.setFixedHeight(max(self.fontMetrics().height()+20,self.heightForWidth(target)+2))

    def toPlainText(self):
        return self.raw
