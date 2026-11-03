"""Sunday Blue desktop entry point. No dependence on any previous project."""
import os
import sys
from pathlib import Path

def main():
    from PySide6.QtWidgets import QApplication, QMessageBox
    from PySide6.QtCore import QTimer, QLockFile
    from sunday_blue.storage import Config, root_path
    from sunday_blue.ui import MainWindow
    app=QApplication(sys.argv)
    app.setApplicationName('Sunday Blue')
    app.setOrganizationName('SundayBlue')
    root=root_path()
    (root/'data').mkdir(parents=True,exist_ok=True)
    lock=QLockFile(str(root/'data'/'app.lock'))
    if not lock.tryLock(100):
        QMessageBox.information(None,'Sunday Blue','软件已在运行，请切换到现有 Sunday Blue 窗口。')
        return 0
    try:
        window=MainWindow(Config(root))
    except Exception as exc:
        QMessageBox.critical(None,'启动失败',str(exc))
        return 1
    window.show()
    if '--smoke' in sys.argv:
        def snapshot():
            window.grab().save(str(root/'docs'/'ui-preview.png'))
            window.close()
        QTimer.singleShot(1200,snapshot)
    return app.exec()

if __name__=='__main__':
    raise SystemExit(main())
