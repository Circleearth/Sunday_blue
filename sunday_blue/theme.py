STYLE = '''
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
