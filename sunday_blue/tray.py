"""Optional source-mode background lifetime; no service or packaging required."""
from PySide6.QtWidgets import QSystemTrayIcon,QMenu

class Tray:
    def __init__(self,window):
        self.window=window;self.exiting=False
        self.icon=QSystemTrayIcon(window.windowIcon(),window)
        self.icon.setToolTip('Sunday Blue · 双击打开')
        menu=QMenu(window);menu.addAction('打开 Sunday Blue',self.show);menu.addAction('退出软件',self.exit)
        self.icon.setContextMenu(menu);self.menu=menu
        self.icon.activated.connect(lambda reason:self.show() if reason in (QSystemTrayIcon.ActivationReason.DoubleClick,QSystemTrayIcon.ActivationReason.Trigger) else None)

    def show(self):
        self.window.showNormal();self.window.raise_();self.window.activateWindow()

    def hide_on_close(self):
        if self.exiting or not self.window.config.value.get('close_to_tray',False) or not QSystemTrayIcon.isSystemTrayAvailable():return False
        self.icon.show();self.window.hide();return True

    def exit(self):
        self.exiting=True
        if not self.window.close():self.exiting=False;self.show()
        else:self.icon.hide()
