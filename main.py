"""Sunday Blue desktop entry point. No dependence on any previous project."""
import os
import sys
from pathlib import Path

def main():
    from PySide6.QtWidgets import QApplication, QMessageBox
    from PySide6.QtCore import QTimer, QLockFile
    from PySide6.QtGui import QFont
    from sunday_blue.storage import Config, root_path
    from sunday_blue.ui import MainWindow
    app=QApplication(sys.argv)
    app.setApplicationName('Sunday Blue')
    app.setOrganizationName('SundayBlue')
    # CJK 中文字形在 175% 缩放下按 22.75 物理像素（小数）光栅化时，Full/Default
    # hinting 会把某些横线压缩到 1px（撇捺/横线粗细不均）；NoHinting 让所有
    # 字形保持光栅化前权重。样式表里的文字字体继承自 app 默认字体，故在此统一设置。
    base=app.font(); base.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    app.setFont(base)
    from sunday_blue.living_memory import close_all
    app.aboutToQuit.connect(close_all)
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
