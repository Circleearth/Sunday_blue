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
        self._composing=False; self.clearing=False; self._placeholder=''
        self.textChanged.connect(self._sync_placeholder)
    def _sync_placeholder(self,*args):
        # While an IME (pinyin) candidate is still pending, the real text is empty and the
        # built-in placeholder would sit under the composing text, so hide it; any actual
        # commit or deletion re-evaluates visibility.
        if self.clearing:return
        self.clearing=True
        try:
            super(Composer,self).setPlaceholderText(' ' if (self._composing and not self.toPlainText().strip()) else self._placeholder)
        finally:
            self.clearing=False
    def setPlaceholderText(self,text):
        self._placeholder=text; self._sync_placeholder()
    def keyPressEvent(self,event):
        if self._composing:
            # Enter/Space belong to the pinyin candidate selection; let the IME commit first.
            if event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter,Qt.Key.Key_Space):return
        elif event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter) and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.send.emit(); return
        super().keyPressEvent(event)
    def event(self,e):
        from PySide6.QtGui import QInputMethodEvent
        if isinstance(e,QInputMethodEvent):
            self._composing=not e.hasCommit()
            if not e.hasCommit():self._sync_placeholder()
        return super().event(e)

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

class Bubble(QTextBrowser):
    def __init__(self,text,user=False,tool=False,light=False,width=0):
        super().__init__()
        self.raw=text
        self.setOpenExternalLinks(False)
        self.setOpenLinks(False)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setWordWrapMode(QTextOption.WrapMode.WrapAnywhere)
        self.setSizePolicy(self.sizePolicy().horizontalPolicy(),self.sizePolicy().verticalPolicy())
        if light:
            background='#dbe7fb' if user else ('#f2f4f7' if tool else '#eef1f5')
            border='#b9cdea' if user else '#d0d5dd'
            color='#1f2937'
        else:
            background='#294761' if user else ('#152236' if tool else '#1b2a40')
            border='#42637f' if user else '#31435c'
            color='#e0e8f3'
        self.setStyleSheet(f'QTextBrowser {{ background:{background}; border:1px solid {border}; border-radius:11px; padding:11px; font-size:14px; color:{color}; }}')
        self.setMinimumWidth(64)
        # width = live chat-panel width (dialog size); short replies stay narrow,
        # long ones wrap at the dialog instead of stretching to a fixed cap.
        self._fit_cap = min(560, (width - 40) if width else 560)
        self._cap = self._fit_cap
        self.set_text(text)
        self.document().documentLayout().documentSizeChanged.connect(self.fit)

    def set_text(self,text):
        text=(text or '').replace('\r\n','\n').replace('\r','\n').lstrip()
        self.raw=text
        self._cap = min(self._fit_cap, max(160, self._fit_width(text)))
        self.setMaximumWidth(self._cap)
        # Plain text intentionally avoids external image loads from model-supplied HTML.
        self.setPlainText(text)
        self.fit()

    def _fit_width(self,text):
        # Measure with a per-line cap so short replies stay narrow instead of
        # stretching toward the full dialog width.
        longest=max((self.fontMetrics().horizontalAdvance(line[:420]) for line in text.splitlines()),default=120)
        return longest+40

    def fit(self,*args):
        self.setFixedHeight(max(58,int(self.document().size().height())+26))

    def resizeEvent(self,event):
        # Re-wrap against the live width (window resize) so the bubble tracks the dialog
        # instead of holding its old height.
        super().resizeEvent(event)
        self.document().setTextWidth(max(50,self.width()-32))
        self.fit()
