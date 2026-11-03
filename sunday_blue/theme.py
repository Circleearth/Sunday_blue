from __future__ import annotations

# Dark (default) — keep the current look as the fallback theme.
DARK_STYLE = '''
* { font-family: "Microsoft YaHei UI", "Segoe UI"; font-size: 13px; color: #dbe5f2; }
QWidget { background: #101827; }
QWidget#shell { border: 1px solid #425572; border-radius: 14px; background: #101827; }
QFrame#top { background: #111c2e; border-bottom: 1px solid #33405a; border-top-left-radius: 14px; border-top-right-radius: 14px; }
QLabel { background: transparent; border: none; }
QLabel#brand { color: #e2d2a5; font-size: 18px; font-weight: 600; letter-spacing: 3px; }
QLabel#eyebrow { color: #8a9cb5; font-size: 10px; letter-spacing: 2px; }
QLabel#title { font-size: 25px; font-weight: 600; color: #eff4ff; }
QLabel#muted { color: #8395ae; font-size: 12px; }
QLabel#section { color: #cfbf96; font-size: 11px; letter-spacing: 2px; }
QPushButton { background: #1c2a40; border: 1px solid #35465e; border-radius: 7px; padding: 8px 13px; }
QPushButton:hover { background: #2a3e58; border-color: #7187a7; }
QPushButton:pressed { background: #304e72; }
QPushButton:disabled { color: #5d6a7e; border-color: #253246; background: #152032; }
QPushButton#primary { background: #b9cde8; color: #142035; border: 1px solid #d1e2f5; font-weight: 600; }
QPushButton#primary:hover { background: #e1edff; }
QPushButton#ghost { background: transparent; border-color: transparent; color: #aabbd1; }
QPushButton#ghost:hover { background: #26344a; }
QPushButton#close:hover { background: #813b4b; }
QPushButton#role { border: 1px solid #293952; background: #152135; border-radius: 10px; padding: 6px; }
QPushButton#role:checked { background: #293a52; border: 1px solid #c2ac7e; }
QPushButton#role:hover { border-color: #8a9db7; }
QFrame#sidebar, QFrame#rail { background: #101b2c; }
QFrame#sidebar { border-right: 1px solid #28364c; }
QFrame#rail { border-left: 1px solid #344158; }
QFrame#portrait { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #22334c,stop:0.5 #16263d,stop:1 #101b2d); border: 1px solid #3e506b; border-radius: 12px; }
QFrame#composer { background: #19263a; border: 1px solid #3c506c; border-radius: 12px; }
QPlainTextEdit, QTextEdit, QTextBrowser { background: #142035; border: 1px solid #33445e; border-radius: 6px; padding: 8px; selection-background-color: #42618b; }
QPlainTextEdit#input { background: transparent; border: none; font-size: 14px; }
QLineEdit, QComboBox, QSpinBox { background: #142035; border: 1px solid #40506b; border-radius: 6px; padding: 7px; min-height: 20px; }
QComboBox QAbstractItemView { background: #1a2940; selection-background-color: #354d6d; }
QListWidget { background: transparent; border: none; outline: none; }
QListWidget::item { padding: 12px 10px; margin: 3px 0; border-radius: 7px; color: #a5b5cb; }
QListWidget::item:selected { background: #253750; color: #edf3ff; }
QListWidget::item:hover { background: #1d2d43; }
QScrollArea { background: transparent; border: none; }
QScrollBar:vertical { background: transparent; width: 7px; margin: 0; }
QScrollBar::handle:vertical { background: #384d68; min-height: 35px; border-radius: 3px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QProgressBar { background: #233248; border: none; height: 4px; border-radius: 2px; }
QProgressBar::chunk { background: #b9a275; border-radius: 2px; }
QTabWidget::pane { border: 1px solid #33465e; border-radius: 8px; padding: 8px; }
QTabBar::tab { background: #17253a; color: #8fa3bd; padding: 11px 17px; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #e6d4ac; border-bottom-color: #c4ab78; }
QCheckBox { spacing: 8px; padding: 5px 0; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #66809f; border-radius: 3px; background: #152439; }
QCheckBox::indicator:checked { background: #a4bedc; border: 3px solid #486183; }
QDialog { background: #101b2c; }
QToolTip { background: #26364c; color: #e3ebf6; border: 1px solid #637792; padding: 6px; }
'''

# Light — "文件夹背景色" clean white, mirrors every DARK_STYLE selector.
LIGHT_STYLE = '''
* { font-family: "Microsoft YaHei UI", "Segoe UI"; font-size: 13px; color: #1f2937; }
QWidget { background: #f6f7f9; }
QWidget#shell { border: 1px solid #d0d5dd; border-radius: 14px; background: #f6f7f9; }
QFrame#top { background: #ffffff; border-bottom: 1px solid #e5e7eb; border-top-left-radius: 14px; border-top-right-radius: 14px; }
QLabel { background: transparent; border: none; }
QLabel#brand { color: #1a56db; font-size: 18px; font-weight: 600; letter-spacing: 3px; }
QLabel#eyebrow { color: #6b7280; font-size: 10px; letter-spacing: 2px; }
QLabel#title { font-size: 25px; font-weight: 600; color: #111827; }
QLabel#muted { color: #6b7280; font-size: 12px; }
QLabel#section { color: #a16207; font-size: 11px; letter-spacing: 2px; }
QPushButton { background: #ffffff; border: 1px solid #d0d5dd; border-radius: 7px; padding: 8px 13px; }
QPushButton:hover { background: #f3f4f6; border-color: #9ca3af; }
QPushButton:pressed { background: #e5e7eb; }
QPushButton:disabled { color: #9ca3af; border-color: #e5e7eb; background: #f9fafb; }
QPushButton#primary { background: #2563eb; color: #ffffff; border: 1px solid #1d4ed8; font-weight: 600; }
QPushButton#primary:hover { background: #1d4ed8; }
QPushButton#ghost { background: transparent; border-color: transparent; color: #4b5563; }
QPushButton#ghost:hover { background: #eef1f5; }
QPushButton#close:hover { background: #ef4444; color: #ffffff; }
QPushButton#role { border: 1px solid #e5e7eb; background: #ffffff; border-radius: 10px; padding: 6px; }
QPushButton#role:checked { background: #f2f0e8; border: 1px solid #a16207; }
QPushButton#role:hover { border-color: #9ca3af; }
QFrame#sidebar, QFrame#rail { background: #f6f7f9; }
QFrame#sidebar { border-right: 1px solid #e5e7eb; }
QFrame#rail { border-left: 1px solid #e5e7eb; }
QFrame#portrait { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #eaf1fb,stop:0.5 #f4f7fc,stop:1 #f6f7f9); border: 1px solid #cfd8e3; border-radius: 12px; }
QFrame#composer { background: #ffffff; border: 1px solid #d0d5dd; border-radius: 12px; }
QPlainTextEdit, QTextEdit, QTextBrowser { background: #ffffff; border: 1px solid #d0d5dd; border-radius: 6px; padding: 8px; selection-background-color: #bfd3f5; }
QPlainTextEdit#input { background: transparent; border: none; font-size: 14px; }
QLineEdit, QComboBox, QSpinBox { background: #ffffff; border: 1px solid #d0d5dd; border-radius: 6px; padding: 7px; min-height: 20px; }
QComboBox QAbstractItemView { background: #ffffff; selection-background-color: #d6e4fb; }
QListWidget { background: transparent; border: none; outline: none; }
QListWidget::item { padding: 12px 10px; margin: 3px 0; border-radius: 7px; color: #374151; }
QListWidget::item:selected { background: #dbe7fb; color: #0f172a; }
QListWidget::item:hover { background: #f3f4f6; }
QScrollArea { background: transparent; border: none; }
QScrollBar:vertical { background: transparent; width: 7px; margin: 0; }
QScrollBar::handle:vertical { background: #cbd5e1; min-height: 35px; border-radius: 3px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QProgressBar { background: #e5e7eb; border: none; height: 4px; border-radius: 2px; }
QProgressBar::chunk { background: #2563eb; border-radius: 2px; }
QTabWidget::pane { border: 1px solid #e5e7eb; border-radius: 8px; padding: 8px; background: #f6f7f9; }
QTabBar::tab { background: #ffffff; color: #6b7280; padding: 11px 17px; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #1f2937; border-bottom-color: #a16207; }
QCheckBox { spacing: 8px; padding: 5px 0; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #9ca3af; border-radius: 3px; background: #ffffff; }
QCheckBox::indicator:checked { background: #2563eb; border: 3px solid #bfdbfe; }
QDialog { background: #f6f7f9; }
QToolTip { background: #ffffff; color: #111827; border: 1px solid #d0d5dd; padding: 6px; }
'''

# Backwards-compatible alias so existing imports keep working.
STYLE = DARK_STYLE

def style_for(name):
    return LIGHT_STYLE if name == 'light' else DARK_STYLE
