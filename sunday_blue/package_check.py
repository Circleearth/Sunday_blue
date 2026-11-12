"""Explicit offline packaging check, using disposable data and no screenshots."""
import json
import sys
import tempfile
import traceback
from pathlib import Path


def verify():
    from PySide6.QtCore import QTimer, QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication, QSystemTrayIcon
    from .storage import Config, root_path
    from .ui import MainWindow
    from .modules.workspace import install_workspace
    base = root_path()
    fixtures = base / 'tests'
    fixtures.mkdir(exist_ok=True)
    result = {'ok': False}
    window = None
    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    try:
        with tempfile.TemporaryDirectory(prefix='sunday-package-', dir=fixtures) as directory:
            config = Config(Path(directory))
            config.value['close_to_tray'] = True
            window = MainWindow(config)
            hub = install_workspace(window)
            hub.timer.stop()  # No scheduling or external channel activity in verification.
            hub.focus_timer.stop()
            window.show()
            def check_hide():
                try:
                    result['pages'] = window.page_stack.count()
                    assert result['pages'] >= 9 and hasattr(window,'relationship_button'), 'Missing pages or chat relationships entry'
                    result['tray_available'] = QSystemTrayIcon.isSystemTrayAvailable()
                    if result['tray_available']:
                        window.close()
                        assert not window.isVisible(), 'Close did not hide to tray'
                        assert window.tray.icon.isVisible(), 'Tray icon missing'
                    QTimer.singleShot(150, check_alive)
                except Exception:
                    result['error'] = traceback.format_exc()
                    app.quit()
            def check_alive():
                try:
                    result['background_event_loop'] = True
                    if result['tray_available']:
                        window.tray.show()
                        assert window.isVisible(), 'Tray restore failed'
                    result['ok'] = True
                except Exception:
                    result['error'] = traceback.format_exc()
                finally:
                    app.quit()
            QTimer.singleShot(250, check_hide)
            app.exec()
            hub.close()
            window.tray.icon.hide()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()
    except Exception:
        result['ok'] = False
        result['error'] = traceback.format_exc()
    (base / 'package-check.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if result['ok'] else 1
