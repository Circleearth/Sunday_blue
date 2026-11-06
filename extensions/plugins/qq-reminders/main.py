"""QQ reminder plugin: agent-side tools + a silent background daemon contract.

Design (lightest version that achieves the goal):
- Agent creates reminders via plugin tools; state lives in
  data/plugins/qq-reminders/state.sqlite3 (table rem).
- A separate silent daemon (daemon/run.py, pythonw = no console window) polls
  the db every 15 seconds. When a reminder fires and a live QQ gateway
  (dsh qqbot profile, checked by its outbound ESTABLISHED connection) plus an
  owner-openid are available, it POSTs to the Tencent QQ Bot OpenAPI
  (proactive message). LLM polishing is optional (off by default).
- The daemon never modifies the host: it only READS Sunday_Blue's
  settings.json + state.sqlite3 and APPENDS to its own log. If the QQ gateway
  is down (e.g. no network, commutes), the reminder stays pending and
  self-heals when the gateway is back (no lost reminders, no spam).
"""
from __future__ import annotations
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

_PLUGIN_ID='qq-reminders'

# Delivery/LLM defaults live ONLY in _conf_schema.json (single source of
# truth: the host renders it into the settings form and the daemon reads it
# via discover()). main.py deliberately keeps no parallel copy so the two
# can never drift.
_REMIND_SCHEMA = {
    'type': 'object',
    'properties': {
        'text': {'type': 'string', 'description': 'The reminder text (sent as-is, prefixed with the role name).'},
        'time_of_day': {'type': 'string', 'description': 'HH:MM (24h). For repeat=daily only.'},
        'date': {'type': 'string', 'description': 'Optional date override for a one-shot HH:MM, e.g. 2026-11-08. Defaults to today, or tomorrow if already past.'},
        'repeat': {'type': 'string', 'enum': ['once', 'daily'], 'description': 'once fires a single time; daily repeats every day at time_of_day.'},
    },
    'required': ['text'],
}

TOOLS = [
    {'name': 'add_reminder',
     'description': 'Create a reminder. The QQ bot will proactively DM the owner at the trigger time '
                    '(with the creating role name prefixed). For repeat=daily use time_of_day only. '
                    'If the user did not give a clear time, ASK before calling this; do not guess.',
     'input_schema': _REMIND_SCHEMA},
    {'name': 'list_reminders',
     'description': 'List this roles reminders and their next fire time.',
     'input_schema': {'type': 'object', 'properties': {}}},
    {'name': 'remove_reminder',
     'description': 'Remove a reminder. By id (from add_reminder) or by text (fuzzy).',
     'input_schema': {'type': 'object', 'properties': {
        'id': {'type': 'integer', 'description': 'Reminder id from add_reminder'},
        'text': {'type': 'string', 'description': 'Fuzzy text match'}}}},
]

def tools():
    return TOOLS

def system_context(config):
    """Inject short usage guidance into the role system prompt (not shown in chat)."""
    cfg = config or {}
    profile = cfg.get('dsh_profile', 'qqbot')
    polish = cfg.get('llm_polish', False)
    cap = cfg.get('llm_max_daily', 10)
    return (
        'You have a QQ reminder plugin: you can create, list and remove reminders with '
        'add_reminder / list_reminders / remove_reminder. The QQ bot '
        '(profile ' + profile + ') will proactively DM the owner at trigger time, prefixed with '
        'the role name. For repeat=daily use time_of_day. If the user has not stated a concrete '
        'time or every-day/once repetition, ASK first; do not invent a time. '
        'If delivery fails (no network, etc.) the reminder is NOT lost, it stays '
        'pending and self-heals when the gateway recovers, so tell the user it will be sent '
        'as soon as possible, without promising a fixed time. '
        'LLM polishing is ' + ('on (max ' + str(cap) + ' per day)' if polish else 'off (fixed text, zero cost)') + '.')

# db
def _db_path(config):
    root = Path((config or {}).get('_plugin_root') or
                Path(__file__).resolve().parents[3])
    return root / 'data' / 'plugins' / _PLUGIN_ID / 'state.sqlite3'

def _conn(config):
    p = _db_path(config)
    p.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(p), timeout=10)
    db.executescript('''
        CREATE TABLE IF NOT EXISTS rem (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL, text TEXT NOT NULL,
            time_of_day TEXT, date_override TEXT,
            repeat TEXT NOT NULL DEFAULT 'once',
            next_fire TEXT, last_fired TEXT,
            done INTEGER NOT NULL DEFAULT 0,
            fail_count INTEGER NOT NULL DEFAULT 0,
            created TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS poll_state (key TEXT PRIMARY KEY, val TEXT);
    ''')
    return db

def _now_iso():
    return datetime.now().astimezone().isoformat(timespec='seconds')

def _parse_fire(time_of_day, date_override, now):
    if not time_of_day:
        return None
    hh = int(time_of_day[:2]); mm = int(time_of_day[3:5])
    base = now
    if date_override:
        base = base.replace(year=int(date_override[:4]), month=int(date_override[5:7]),
                            day=int(date_override[8:10]))
    cand = base.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if cand <= now and not date_override:
        cand += timedelta(days=1)
    return cand

def add_reminder(config, role, text, time_of_day=None, date_override=None, repeat='once'):
    text = (text or '').strip()
    if not text:
        return {'status': 'error', 'error': 'text is empty'}
    if repeat == 'daily' and not time_of_day:
        return {'status': 'error', 'error': 'repeat=daily requires time_of_day (HH:MM)'}
    if repeat == 'once' and not time_of_day and not date_override:
        return {'status': 'error', 'error': 'once reminder needs time_of_day and/or date'}
    if time_of_day:
        try:
            hh, mm = int(time_of_day[:2]), int(time_of_day[3:5])
            if hh > 23 or mm > 59:
                raise ValueError
        except Exception:
            return {'status': 'error', 'error': 'time_of_day must be HH:MM (24h), got ' + repr(time_of_day)}
    db = _conn(config)
    now = datetime.now().astimezone()
    nxt = _parse_fire(time_of_day, date_override, now)
    cur = db.execute(
        'INSERT INTO rem(role,text,time_of_day,date_override,repeat,next_fire,done,fail_count,created) '
        'VALUES(?,?,?,?,?,?,0,0,?)',
        (role, text, time_of_day, date_override, repeat,
         nxt.isoformat(timespec='seconds') if nxt else None, _now_iso()))
    db.commit(); db.close()
    return {'status': 'ok', 'id': cur.lastrowid, 'next_fire': str(nxt) if nxt else None, 'repeat': repeat}

def list_reminders(config, role):
    db = _conn(config)
    rows = db.execute(
        'SELECT id,text,time_of_day,date_override,repeat,next_fire,done,fail_count,created '
        'FROM rem WHERE role=? AND done=0 ORDER BY created DESC', (role,)).fetchall()
    db.close()
    return [{'id': r[0], 'text': r[1], 'time_of_day': r[2], 'date': r[3],
             'repeat': r[4], 'next_fire': r[5], 'fail_count': r[7]} for r in rows]

def remove_reminder(config, role, rid=None, text=None):
    db = _conn(config)
    removed = 0
    if rid is not None:
        cur = db.execute('UPDATE rem SET done=1 WHERE id=? AND role=?', (rid, role))
        removed = cur.rowcount
    elif text:
        rows = db.execute('SELECT id FROM rem WHERE role=? AND done=0 AND text LIKE ?',
                          (role, '%' + text.strip() + '%')).fetchall()
        for (i,) in rows:
            db.execute('UPDATE rem SET done=1 WHERE id=?', (i,)); removed += 1
    db.commit(); db.close()
    if rid is None and text is None:
        return {'status': 'error', 'error': 'need id or text'}
    return {'status': 'ok', 'removed': int(removed)}

def dispatch(config, role, name, args):
    args = args or {}
    if name == 'add_reminder':
        return add_reminder(config, role, args.get('text'), args.get('time_of_day'),
                            args.get('date'), args.get('repeat', 'once'))
    if name == 'list_reminders':
        return list_reminders(config, role)
    if name == 'remove_reminder':
        return remove_reminder(config, role, args.get('id'), args.get('text'))
    return {'status': 'error', 'error': 'unknown tool ' + str(name)}

PLUGIN_ID = _PLUGIN_ID
def plugin(config, role, name, args):
    return dispatch(config, role, name, args)


def settings_extra(root):
    """Optional hook (PLUGIN_SPEC section 3b): the host's per-plugin settings
    dialog embeds this panel under the parameter form. Shows live status of
    this plugin's own components (daemon / watchdog task / pending reminders)
    and restart / stop controls that manage ONLY this plugin's pythonw daemon
    and its Task Scheduler task — never the host data or any external
    gateway. Delivery is self-contained (direct QQ Bot OpenAPI), so there is
    no gateway row. Qt imports happen here so plain module import in
    non-GUI tests stays safe."""
    import importlib.util
    from pathlib import Path as _Path
    from PySide6.QtCore import QTimer, QThread, Signal
    from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                                   QPushButton)

    here = _Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location('_sb_qqrem_ctl', str(here / 'daemon_ctl.py'))
    ctl = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ctl)
    root = str(root)

    class _Worker(QThread):
        done = Signal(object)
        def __init__(self, fn):
            super().__init__()
            self._fn = fn
        def run(self):
            try:
                self.done.emit(self._fn())
            except Exception as e:
                self.done.emit({'_error': '%s: %s' % (type(e).__name__, e)})

    w = QWidget()
    w._settings_extra_title = 'QQ 定时提醒 · 运行状态与重启/停止'
    col = QVBoxLayout(w)
    col.setContentsMargins(0, 0, 0, 0)
    col.setSpacing(6)

    states = {}
    for key, title in (('daemon', '守护进程（后台，无窗口）'),
                       ('task', '看门狗计划任务（守护被杀会自动补）'),
                       ('pending', '挂起中待发的提醒')):
        row = QHBoxLayout()
        cap = QLabel(title)
        cap.setObjectName('muted')
        val = QLabel('未检测')
        row.addWidget(cap)
        row.addStretch()
        row.addWidget(val)
        col.addLayout(row)
        states[key] = val

    restart_btn = QPushButton('重启')
    stop_btn = QPushButton('停止')
    test_btn = QPushButton('试发一条')
    check_btn = QPushButton('检查')
    result = QLabel('')
    result.setObjectName('muted')
    result.setWordWrap(True)
    note = QLabel('「重启/停止」只管本插件的守护进程与看门狗任务。提醒由守护进程直接调 QQ 机器人接口主动发送，不依赖外部网关进程；断网时段到点的提醒挂起、联网后自动补发。')
    note.setObjectName('muted')
    note.setWordWrap(True)

    ops = []

    def refresh(force=False):
        if ops and not force:
            return  # a restart/stop is still running; do not flip buttons mid-op
        try:
            st = ctl.check(root)
        except Exception as exc:
            for v in states.values():
                v.setText('检测失败：%s' % exc)
            return
        states['daemon'].setText('运行中（PID %s）' % st['daemon_pid']
                                 if st['daemon_alive'] else '未运行')
        states['task'].setText('已注册（每 30 分钟自检拉起）'
                               if st['task_installed'] else '未注册')
        states['pending'].setText('%d 条' % st['pending'])

    def _run_bg(key, fn):
        def on_done(ret):
            ops.remove(worker)
            for b in (restart_btn, stop_btn, test_btn, check_btn):
                b.setEnabled(True)
            restart_btn.setText('重启'); stop_btn.setText('停止')
            test_btn.setText('试发一条'); check_btn.setText('检查')
            if key == 'test':
                result.setText(ret if isinstance(ret, str) else '试发完成')
            elif isinstance(ret, dict) and ret.get('_error'):
                result.setText('操作失败：%s，点“检查”看当前状态' % ret['_error'])
            else:
                if key == 'restart':
                    alive = ret.get('daemon_alive') if isinstance(ret, dict) else False
                    result.setText('已重启：守护进程 ' + ('运行中' if alive else '未起来，点“检查”看详情'))
                else:
                    result.setText('已停止守护进程与看门狗任务')
            refresh()
        for b in (restart_btn, stop_btn, test_btn, check_btn):
            b.setEnabled(False)
        if key == 'restart':
            restart_btn.setText('重启中…')
            result.setText('正在重启（停旧进程 + 起守护 + 注册看门狗，约 10 秒）')
        elif key == 'stop':
            stop_btn.setText('停止中…')
            result.setText('正在停止…')
        else:
            test_btn.setText('发送中…')
            result.setText('正在试发一条消息到你的 QQ（需网络，约 10 秒）')
        worker = _Worker(fn)
        ops.append(worker)
        worker.done.connect(on_done)
        worker.start()

    restart_btn.clicked.connect(lambda: _run_bg('restart', lambda: ctl.restart(root)))
    stop_btn.clicked.connect(lambda: _run_bg('stop', lambda: ctl.stop(root)))
    test_btn.clicked.connect(lambda: _run_bg('test', lambda: ctl.send_test(root)))
    check_btn.clicked.connect(lambda: refresh(force=True))

    row = QHBoxLayout()
    row.addWidget(restart_btn); row.addWidget(stop_btn)
    row.addWidget(test_btn);    row.addWidget(check_btn)
    row.addStretch()
    col.addLayout(row)
    col.addWidget(note)
    col.addWidget(result)

    refresh(force=True)
    timer = QTimer(w)
    timer.setInterval(15000)
    timer.timeout.connect(lambda: refresh())
    timer.start()
    return w
