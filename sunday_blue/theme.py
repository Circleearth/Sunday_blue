"""Qt stylesheet generated from shared design tokens."""
from .design_system import tokens

def style_for(name, ui_display=None):
    t=tokens(name); family=(ui_display or {}).get('font_family','Noto Sans SC').replace('"','')
    return f'''
* {{ font-family:"{family}"; font-size:{t['ui_size']}px; color:{t['text']}; }}
QWidget {{ background:{t['canvas']}; }}
QWidget#shell {{ border:1px solid {t['border_strong']}; border-radius:12px; background:{t['canvas']}; }}
QFrame#top {{ background:{t['surface']}; border-bottom:1px solid {t['border']}; border-top-left-radius:12px; border-top-right-radius:12px; }}
QLabel {{ background:transparent; border:none; }}
QLabel#brand {{ color:{t['text']}; font-size:16px; font-weight:650; letter-spacing:1px; }}
QLabel#eyebrow {{ color:{t['text_subtle']}; font-size:11px; font-weight:550; }}
QLabel#title {{ font-size:22px; font-weight:650; color:{t['text']}; }}
QLabel#muted {{ color:{t['text_muted']}; font-size:12px; }}
QLabel#section {{ color:{t['text_muted']}; font-size:11px; font-weight:650; }}
QLabel#cardTitle {{ color:{t['text']}; font-size:14px; font-weight:650; }}
QFrame#card {{ background:{t['surface']}; border:1px solid {t['border']}; border-radius:{t['radius_panel']}px; }}
QPushButton {{ background:{t['surface_raised']}; border:1px solid {t['border']}; border-radius:{t['radius_control']}px; padding:7px 12px; min-height:18px; }}
QPushButton:hover {{ background:{t['surface_hover']}; border-color:{t['border_strong']}; }}
QPushButton:pressed {{ background:{t['surface_selected']}; }}
QPushButton:focus {{ border-color:{t['accent']}; }}
QPushButton:disabled {{ color:{t['text_subtle']}; background:{t['surface']}; }}
QPushButton#primary {{ background:{t['accent']}; color:#fff; border-color:{t['accent']}; font-weight:650; }}
QPushButton#primary:hover {{ background:{t['accent_hover']}; }}
QPushButton#ghost {{ background:transparent; border-color:transparent; color:{t['text_muted']}; }}
QPushButton#ghost:hover {{ background:{t['surface_hover']}; color:{t['text']}; }}
QPushButton#close:hover {{ background:{t['danger']}; color:#fff; }}
QPushButton#role {{ border:1px solid transparent; background:transparent; border-radius:9px; padding:5px; }}
QPushButton#role:checked {{ background:{t['accent_soft']}; border-color:{t['accent']}; }}
QPushButton#role:hover {{ background:{t['surface_hover']}; }}
QToolButton#role {{ background:transparent; border:1px solid transparent; border-radius:9px; padding:6px; color:{t['text_muted']}; }}
QToolButton#role:checked {{ background:{t['accent_soft']}; border-color:{t['accent']}; color:{t['text']}; }}
QToolButton#role:hover {{ background:{t['surface_hover']}; color:{t['text']}; }}
QFrame#sidebar,QFrame#rail {{ background:{t['surface']}; }}
QFrame#sidebar {{ border-right:1px solid {t['border']}; }} QFrame#rail {{ border-left:1px solid {t['border']}; }}
QFrame#portrait {{ background:{t['surface']}; border:1px solid {t['border']}; border-radius:{t['radius_panel']}px; }}
QFrame#composer {{ background:{t['surface']}; border:1px solid {t['border_strong']}; border-radius:{t['radius_panel']}px; }}
QPlainTextEdit,QTextEdit,QTextBrowser {{ background:{t['surface']}; border:1px solid {t['border']}; border-radius:{t['radius_control']}px; padding:8px; selection-background-color:{t['selection']}; }}
QPlainTextEdit#input {{ background:transparent; border:none; font-size:14px; padding:3px; }}
QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox {{ background:{t['surface_raised']}; border:1px solid {t['border_strong']}; border-radius:{t['radius_control']}px; padding:6px 9px; min-height:20px; }}
QLineEdit:focus,QComboBox:focus,QSpinBox:focus,QDoubleSpinBox:focus {{ border-color:{t['accent']}; }}
QComboBox QAbstractItemView {{ background:{t['surface_raised']}; selection-background-color:{t['surface_selected']}; }}
QListWidget {{ background:transparent; border:none; outline:none; }}
QListWidget::item {{ padding:9px 10px; margin:2px 0; border-radius:7px; color:{t['text_muted']}; }}
QListWidget::item:selected {{ background:{t['surface_selected']}; color:{t['text']}; }} QListWidget::item:hover {{ background:{t['surface_hover']}; }}
QListWidget#settingsNav {{ background:{t['surface']}; border-right:1px solid {t['border']}; padding:8px; }}
QListWidget#settingsNav::item {{ padding:11px 12px; margin:2px 0; }}
QScrollArea {{ background:transparent; border:none; }}
QScrollBar:vertical {{ background:transparent; width:7px; }} QScrollBar::handle:vertical {{ background:{t['border_strong']}; min-height:35px; border-radius:3px; }}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {{ height:0; }} QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical {{ background:transparent; }}
QProgressBar {{ background:{t['border']}; border:none; height:4px; border-radius:2px; }} QProgressBar::chunk {{ background:{t['accent']}; border-radius:2px; }}
QCheckBox {{ spacing:8px; padding:4px 0; }} QCheckBox::indicator {{ width:15px; height:15px; border:1px solid {t['border_strong']}; border-radius:4px; background:{t['surface']}; }}
QCheckBox::indicator:checked {{ background:{t['accent']}; border-color:{t['accent']}; }}
QDialog {{ background:{t['canvas']}; }} QToolTip {{ background:{t['surface_raised']}; color:{t['text']}; border:1px solid {t['border_strong']}; padding:6px; }}
'''

STYLE=style_for('dark')
