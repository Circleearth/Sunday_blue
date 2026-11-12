"""Optional source-mode background lifetime; no service or packaging required."""
from PySide6.QtWidgets import QSystemTrayIcon,QMenu,QWidget
from PySide6.QtCore import QTimer,Qt
from PySide6.QtGui import QIcon,QPixmap,QPainter,QColor

class Tray:
    def __init__(self,window):
        self.window=window;self.exiting=False
        icon=window.windowIcon()
        if icon.isNull() or icon.pixmap(32,32).isNull():
            pixmap=QPixmap(32,32);pixmap.fill(Qt.GlobalColor.transparent)
            painter=QPainter(pixmap);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(QColor('#5b7cf3'));painter.setPen(Qt.PenStyle.NoPen);painter.drawRoundedRect(1,1,30,30,9,9)
            painter.setPen(QColor('white'));painter.drawText(pixmap.rect(),Qt.AlignmentFlag.AlignCenter,'S');painter.end()
            icon=QIcon(pixmap);window.setWindowIcon(icon)
        self.icon=QSystemTrayIcon(icon,window)
        self.icon.setToolTip('Sunday Blue · 双击打开')
        menu=QMenu(window);menu.addAction('打开 Sunday Blue',self.show);menu.addAction('退出软件',self.exit)
        self.icon.setContextMenu(menu);self.menu=menu
        self.icon.activated.connect(lambda reason:self.show() if reason in (QSystemTrayIcon.ActivationReason.DoubleClick,QSystemTrayIcon.ActivationReason.Trigger) else None)
        self.icon.show()
        self.watch=QTimer(window);self.watch.setInterval(3000);self.watch.timeout.connect(self.ensure_accessible);self.watch.start()

    def ensure_accessible(self):
        if self.exiting:return
        if QSystemTrayIcon.isSystemTrayAvailable():
            if not self.icon.isVisible():self.icon.show()
        elif not self.window.isVisible():self.show()

    def show(self):
        self.window.showNormal();self.window.raise_();self.window.activateWindow()

    def hide_on_close(self):
        if self.exiting or not self.window.config.value.get('close_to_tray',False) or not QSystemTrayIcon.isSystemTrayAvailable():return False
        self.icon.show()
        if self.icon.icon().isNull() or not self.icon.isVisible():return False
        self.window.hide();return True

    def exit(self):
        self.exiting=True
        if not self.window.close():
            saving=any(getattr(p,'saving',False) for p in self.window.findChildren(QWidget))
            if not saving and not getattr(self.window,'_shutdown_waiting',False):self.exiting=False
            self.show()
        else:self.icon.hide()
