"""Operational checks and control for the qq-reminders daemon.

Used by the plugin's settings-dialog control panel (see main.py's optional
settings_extra hook, documented in handoff/PLUGIN_SPEC.md section 3b). All
checks are read-only except install()/stop()/restart(), which only touch this
plugin's own Task Scheduler task and its own pythonw process — never the host
app's data or any external gateway. Delivery is self-contained: the daemon
sends proactively via the QQ Bot OpenAPI and does not depend on a gateway
process, so no gateway liveness is reported here.
"""
from __future__ import annotations
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

PLUGIN_ID = 'qq-reminders'
TASK_NAME = 'SundayBlue-QQ-Reminders'
DEFAULT_PYTHONW = 'C:/Users/zsc18/AppData/Local/Programs/Python/Python314/pythonw.exe'


def _run(root):
    """Load daemon/run.py under a stable module name (it has no side effects on import)."""
    p = Path(root) / 'extensions' / 'plugins' / 'qq-reminders' / 'daemon' / 'run.py'
    spec = importlib.util.spec_from_file_location('_sb_qqrem_run', str(p))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.ROOT = Path(root)
    return mod


def _lock(root):
    return Path(root) / 'data' / 'plugins' / PLUGIN_ID / 'daemon.lock'


def check(root):
    """Read-only status of the daemon, its watchdog task, and pending reminders."""
    run = _run(root)
    out = {'daemon_alive': False, 'daemon_pid': None, 'task_installed': False, 'pending': 0}
    lock = _lock(root)
    if lock.exists():
        try:
            pid = int(lock.read_text(encoding='utf-8').strip() or 0)
            if pid and run._pid_alive(pid):
                out['daemon_alive'] = True
                out['daemon_pid'] = pid
        except ValueError:
            pass
    try:
        r = subprocess.run(['schtasks', '/Query', '/TN', TASK_NAME],
                           capture_output=True, text=True, timeout=15,
                           creationflags=0x08000000)
        out['task_installed'] = r.returncode == 0
    except Exception:
        pass
    dbf = Path(root) / 'data' / 'plugins' / PLUGIN_ID / 'state.sqlite3'
    if dbf.exists():
        try:
            c = sqlite3.connect(str(dbf))
            out['pending'] = c.execute(
                'SELECT COUNT(*) FROM rem WHERE done=0 AND next_fire IS NOT NULL').fetchone()[0]
            c.close()
        except sqlite3.Error:
            pass
    return out


def _cfg(root):
    """Resolve delivery config the way the daemon does: schema defaults, then the
    host's settings.json (role plugin_settings + api section)."""
    root = Path(root).resolve()
    sys.path.insert(0, str(root))
    from sunday_blue.plugin_runtime import discover
    meta = discover(root).get(PLUGIN_ID, {})
    values = {k: spec.get('default') for k, spec in meta.get('schema', {}).items()}
    sf = root / 'data' / 'settings.json'
    host = json.loads(sf.read_text(encoding='utf-8')) if sf.exists() else {}
    api = host.get('api') or {}
    if not values.get('llm_base_url'):
        values['llm_base_url'] = api.get('base_url', '')
    if not values.get('llm_model'):
        values['llm_model'] = api.get('model', '')
    for rv in host.get('roles', {}).values():
        ps = (rv.get('plugin_settings') or {}).get(PLUGIN_ID) or {}
        for k, v in ps.items():
            if v:
                values[k] = v
    return values


def send_test(root):
    """Send one proactive QQ message to the owner to verify the delivery path,
    without creating a reminder. Returns a short human-readable status string."""
    run = _run(root)
    cfg = _cfg(root)
    profile = cfg.get('dsh_profile', 'qqbot')
    creds = run._creds(profile)
    if not creds:
        return '未找到 QQ 机器人凭据（%USERPROFILE%/.dsh/profiles/%s/cordis.patch.yml）' % profile
    openid = cfg.get('qq_openid')
    if not openid:
        return '未设置 qq_openid，无法发送'
    last = None
    for _ in range(2):  # one retry: SSL EOF via a flaky proxy is often transient
        try:
            tok = run._token(creds, cfg)
            ok = run._qq_send(creds, tok, openid,
                              '🟢 Sunday Blue 试发消息：收到即说明主动提醒链路可用', cfg)
            if ok:
                return '已发送一条试发消息到你的 QQ'
            last = 'QQ 接口拒绝/发送失败'
        except Exception as e:
            s = str(e)
            last = s
            if 'UNEXPECTED_EOF' not in s:
                break  # non-transient failure (4xx, bad creds…): no point retrying
    if 'UNEXPECTED_EOF' in str(last) or 'urlopen' in str(last) or 'proxy' in str(last).lower():
        return ('网络/代理不通或超时（%s）：请确认 7890 代理能正常出网后重试；'
                '到点的提醒会自动挂起重试，不会丢' % str(last)[:120])
    if last:
        return '发送失败：%s（需网络与代理正常；守护日志 data/plugins/qq-reminders/daemon.log）' % str(last)[:160]
    return '发送失败，请看守护日志 data/plugins/qq-reminders/daemon.log'


def _vbs_path(root):
    return Path(root) / 'extensions' / 'plugins' / PLUGIN_ID / 'daemon' / 'launch.vbs'


def install(root, pythonw=None):
    """Register the watchdog task and start the daemon silently.

    - The launcher .vbs is written into the plugin's own daemon dir with ABSOLUTE
      paths (a Task Scheduler trigger has no reliable working directory, so a
      relative path would not find run.py).
    - The watchdog task re-runs the .vbs on a schedule; the daemon's own
      single-instance lock dedupes, so re-firing while it is alive is a no-op.
    - The daemon is started immediately with a direct Popen of pythonw (most
      reliable), not only through the task.
    """
    root = Path(root).resolve()
    pythonw = (pythonw or DEFAULT_PYTHONW).replace('/', os.sep)
    if not Path(pythonw).exists():
        pythonw = Path(sys.executable).with_name('pythonw.exe').as_posix() or Path(sys.executable).as_posix()
    daemon = str((root / 'extensions' / 'plugins' / PLUGIN_ID / 'daemon' / 'run.py').resolve())
    vbs = _vbs_path(root)
    vbs.parent.mkdir(parents=True, exist_ok=True)
    vbs.write_text(
        'Set sh = CreateObject("WScript.Shell")\n'
        'sh.Run """{0}"" ""{1}""", 0, False\n'
        'Set sh = Nothing\n'.format(pythonw, daemon),
        encoding='ascii')
    CREATE_NO_WINDOW = 0x08000000
    subprocess.run(['schtasks', '/Create', '/F', '/SC', 'MINUTE', '/MO', '30',
                    '/TN', TASK_NAME, '/TR', 'wscript.exe "%s"' % str(vbs)],
                   capture_output=True, text=True, timeout=30, creationflags=CREATE_NO_WINDOW)
    subprocess.run(['schtasks', '/Change', '/TN', TASK_NAME, '/ENABLE'],
                   capture_output=True, text=True, timeout=30, creationflags=CREATE_NO_WINDOW)
    _spawn_daemon(pythonw, daemon)
    import time
    time.sleep(2)
    return check(root)


def _spawn_daemon(pythonw, daemon):
    subprocess.Popen([pythonw, daemon], creationflags=0x08000000)


def stop(root):
    """Delete the watchdog task and kill the daemon; delivered history is untouched."""
    CREATE_NO_WINDOW = 0x08000000
    subprocess.run(['schtasks', '/Delete', '/F', '/TN', TASK_NAME],
                   capture_output=True, text=True, timeout=30, creationflags=CREATE_NO_WINDOW)
    lock = _lock(root)
    if lock.exists():
        try:
            pid = int(lock.read_text(encoding='utf-8').strip() or 0)
            if pid:
                subprocess.run(['taskkill', '/PID', str(pid), '/F'],
                               capture_output=True, text=True, timeout=15, creationflags=CREATE_NO_WINDOW)
        except ValueError:
            pass
    return check(root)


def restart(root, pythonw=None):
    """Full stop then start of this plugin's own components (its daemon + watchdog
    task). Returns the post-restart status dict."""
    stop(root)
    return install(root, pythonw)
