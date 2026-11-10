"""Pomodoro options and app-owned sound imports; no external runtime dependency."""
import hashlib
from pathlib import Path

PHASES = {'focus': '专注', 'short_break': '短休息', 'long_break': '长休息'}
DEFAULTS = {'focus_minutes': 25, 'short_break_minutes': 5, 'long_break_minutes': 15,
            'llm_feedback': True, 'auto_loop': False, 'max_rounds': 4, 'long_every': 4, 'sound_enabled': True, 'volume': 65,
            'sounds': {phase: '' for phase in PHASES}}


def options(database):
    saved = database.get('pomodoro_options', {})
    return DEFAULTS | saved | {'sounds': DEFAULTS['sounds'] | saved.get('sounds', {})}


def save_options(database, values):
    result = options(database) | values
    for key, low, high in (('focus_minutes', 1, 240), ('short_break_minutes', 1, 60),
                           ('long_break_minutes', 1, 120), ('max_rounds', 1, 20), ('long_every', 2, 12), ('volume', 0, 100)):
        value = result[key]
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ValueError(f'{key} 需在 {low}–{high} 之间。')
    if not isinstance(result['sound_enabled'], bool) or not isinstance(result['auto_loop'], bool):
        raise ValueError('提示音开关必须为开或关。')
    result['sounds'] = DEFAULTS['sounds'] | result.get('sounds', {})
    for name in PHASES:
        if result['sounds'][name]: sound_path(database.root, result['sounds'][name])
    database.set('pomodoro_options', result)
    return result


def sound_path(root, relative):
    folder = (Path(root) / 'data/sounds/focus').resolve()
    path = (Path(root) / relative).resolve()
    if not path.is_relative_to(folder) or path.suffix.lower() not in ('.mp3', '.wav'):
        raise ValueError('提示音必须是导入到本软件的 MP3 或 WAV 文件。')
    return path


def import_sound(root, source):
    source = Path(source)
    if source.suffix.lower() not in ('.mp3', '.wav'):
        raise ValueError('请选择 MP3 或 WAV 音频。')
    if not source.is_file() or not 0 < source.stat().st_size <= 20 * 1024 * 1024:
        raise ValueError('音频不能为空，且不能超过 20 MB。')
    data = source.read_bytes()
    folder = Path(root) / 'data/sounds/focus'
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / (hashlib.sha256(data).hexdigest()[:24] + source.suffix.lower())
    if not destination.exists(): destination.write_bytes(data)
    return destination.relative_to(root).as_posix()
