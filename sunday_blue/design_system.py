"""Shared visual tokens and curated Chinese typography choices."""
from __future__ import annotations

UI_FONTS = [
    ('Noto Sans SC', '思源黑体（现代、清晰）'),
    ('Microsoft YaHei UI', '微软雅黑 UI（稳重、通用）'),
    ('DengXian', '等线（轻盈、简洁）'),
    ('YouYuan', '幼圆（圆润、轻松）'),
]

CHAT_FONTS = UI_FONTS + [
    ('Noto Serif SC', '思源宋体（典雅、书卷）'),
    ('KaiTi', '楷体（温柔、手写感）'),
    ('FangSong', '仿宋（克制、档案感）'),
    ('STXingkai', '华文行楷（随性、灵动）'),
    ('STXinwei', '华文新魏（鲜明、力量感）'),
    ('STKaiti', '华文楷体（亲切、叙事感）'),
    ('STXihei', '华文细黑（理性、轻快）'),
    ('Microsoft JhengHei UI', '微软正黑 UI（利落、科技感）'),
]

ROLE_FONT_DEFAULTS = {
    'rui': {'font_family': 'Noto Sans SC', 'font_size': 12, 'font_weight': 500},
    'red': {'font_family': 'STXinwei', 'font_size': 12, 'font_weight': 600},
    'ewa': {'font_family': 'YouYuan', 'font_size': 12, 'font_weight': 500},
    'luna': {'font_family': 'KaiTi', 'font_size': 13, 'font_weight': 500},
    'loluns': {'font_family': 'STKaiti', 'font_size': 12, 'font_weight': 500},
    'kia': {'font_family': 'FangSong', 'font_size': 12, 'font_weight': 500},
    'mia': {'font_family': 'STXingkai', 'font_size': 13, 'font_weight': 500},
    'ticktick': {'font_family': 'DengXian', 'font_size': 12, 'font_weight': 600},
    'mubu': {'font_family': 'Noto Serif SC', 'font_size': 12, 'font_weight': 500},
}

BASE = {'space_1': 4, 'space_2': 8, 'space_3': 12, 'space_4': 16,
        'space_6': 24, 'radius_control': 7, 'radius_panel': 10,
        'radius_bubble': 10, 'control_height': 34, 'ui_size': 13}

THEMES = {
    'dark': {
        'canvas': '#0f1117', 'surface': '#151821', 'surface_raised': '#1b1f2a',
        'surface_hover': '#222735', 'surface_selected': '#292f40',
        'text': '#eef0f4', 'text_muted': '#9299a8', 'text_subtle': '#6f7787',
        'border': '#2a3040', 'border_strong': '#3a4255', 'accent': '#6e7ff3',
        'accent_hover': '#8492ff', 'accent_soft': '#262d52', 'danger': '#ef6b73',
        'user_bubble': '#34456c', 'assistant_bubble': '#1b1f29',
        'bubble_border': '#343b4c', 'selection': '#3c4b81'},
    'light': {
        'canvas': '#f7f7f8', 'surface': '#ffffff', 'surface_raised': '#ffffff',
        'surface_hover': '#f0f1f4', 'surface_selected': '#e9ebf3',
        'text': '#1d2028', 'text_muted': '#666d7a', 'text_subtle': '#8b919d',
        'border': '#e1e3e8', 'border_strong': '#cfd3dc', 'accent': '#5e6ad2',
        'accent_hover': '#4f5bc4', 'accent_soft': '#eceefe', 'danger': '#d84a55',
        'user_bubble': '#e5e9fc', 'assistant_bubble': '#ffffff',
        'bubble_border': '#dfe2e8', 'selection': '#cbd2fb'},
}

def tokens(theme='dark'):
    return BASE | THEMES['light' if theme == 'light' else 'dark']

# Recovery visualization semantics; pastel fills remain readable in both themes.
RECOVERY_COLORS = {'red':'#efb6b5','orange':'#efccaa','yellow':'#eadfa8','green':'#bddbc9','unknown':'#dce1e8'}
RECOVERY_LABELS = {'red':'建议恢复','orange':'谨慎安排','yellow':'基本恢复','green':'可考虑训练','unknown':'数据不足'}
STATE_ACCENTS = {'ready':'#75a38b','caution':'#c5aa64','rest':'#ca8e8d'}
