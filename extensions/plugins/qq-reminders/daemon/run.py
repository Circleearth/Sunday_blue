"""qq-reminders silent daemon.

Runs headless under pythonw (no console window), registered by install_task.bat
through a Windows Task Scheduler task. Responsibilities:

- poll data/plugins/qq-reminders/state.sqlite3 every `poll_interval` seconds
- when a reminder is due AND the QQ gateway (the dsh profile) is alive, deliver it:
    * optional LLM polish via the host-configured API (OpenAI-compatible /v1)
    * QQ proactive message via the Tencent QQ Bot OpenAPI (creds from the DSH
      profile, not re-stored here)
- if the gateway / network is down (e.g. no-net commute windows), the reminder
  stays pending and self-heals on a later poll; after `delivery_max_retries`
  misses it is abandoned and logged. Nothing is lost silently, nothing spams.

The daemon only READS the host's settings.json / state.sqlite3 and APPENDS to
its own log; it never writes into the host conversation db.
"""
from __future__ import annotations
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]  # Sunday_Blue source or installed dir
# Load the plugin main.py by explicit path under a unique module name. A bare
# `import main` would shadow onto the app's own <ROOT>/main.py entry point.
import importlib.util

_spec = importlib.util.spec_from_file_location("_sb_qq_reminders_plugin", HERE.parent / "main.py")
plugin = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(plugin)
sys.path.insert(0, str(ROOT))  # for `from sunday_blue.storage import protect`
PLUGIN_ID = plugin.PLUGIN_ID


def _settings():
    p = ROOT / "data" / "settings.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _cfg_for_role(role):
    """Per-role daemon config = _conf_schema.json defaults (single source of truth),
    then this role's stored plugin_settings, then host api section filling the
    LLM endpoint/model/key. Reminders are per-role, so delivery settings resolve
    per reminder row, not globally."""
    from sunday_blue.plugin_runtime import discover
    meta = discover(ROOT).get(PLUGIN_ID, {})
    values = {k: spec.get("default") for k, spec in meta.get("schema", {}).items()}
    host = _settings()
    values.update(host.get("roles", {}).get(role, {}).get("plugin_settings", {}).get(PLUGIN_ID, {}))
    api = host.get("api") or {}
    if not values.get("llm_base_url"):
        values["llm_base_url"] = api.get("base_url", "")
    if not values.get("llm_model"):
        values["llm_model"] = api.get("model", "")
    if not values.get("llm_key_override"):
        # Same user, same DPAPI store the app uses, so reuse it directly.
        from sunday_blue.storage import protect
        values["_host_key_plain"] = protect(api.get("key_encrypted", ""), decrypt=True)
    return values


def _log(msg):
    line = "[%s] %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    logf = ROOT / "data" / "plugins" / PLUGIN_ID / "daemon.log"
    logf.parent.mkdir(parents=True, exist_ok=True)
    with logf.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _creds(profile):
    p = (Path(os.path.expandvars("%USERPROFILE%")) / ".dsh" / "profiles" / profile / "cordis.patch.yml")
    if not p.exists():
        return None
    t = p.read_text(encoding="utf-8")
    aid = re.search(r"appId:\s*['\"]?([A-Za-z0-9]+)", t)
    sec = re.search(r"appSecret:\s*['\"]?([A-Za-z0-9]+)", t)
    return {"appId": aid.group(1), "appSecret": sec.group(1)} if (aid and sec) else None


def _gateway_alive():
    """QQ delivery needs a live dsh gateway with an ESTABLISHED outbound conn,
    mirroring the Rui watchdog liveness rule. We only deliver when it is up; if
    it is down we stay pending (no lost reminder, no spam). We never spawn a
    gateway ourselves - that is the Rui watchdog's job, not this plugin's."""
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process -Filter 'Name=\"node.exe\"' | "
         "Where-Object { $_.CommandLine -match 'dsh' -and $_.CommandLine -match 'qqbot' } | "
         "Select-Object -ExpandProperty ProcessId"],
        capture_output=True, text=True, timeout=15)
    pids = [x for x in out.stdout.split() if x.isdigit()]
    if not pids:
        return False
    st = subprocess.run("netstat -ano".split(), capture_output=True, text=True, timeout=15)
    return any(("ESTABLISHED" in ln and any(p in ln for p in pids))
               for ln in st.stdout.splitlines())


def _opener(cfg):
    proxy = cfg.get("http_proxy") or ""
    return (urllib.request.build_opener(urllib.request.ProxyHandler({"https": proxy, "http": proxy}))
            if proxy else urllib.request.build_opener())


def _token(creds, cfg):
    body = json.dumps({"appId": creds["appId"], "clientSecret": creds["appSecret"]}).encode()
    req = urllib.request.Request("https://bots.qq.com/app/getAppAccessToken",
                                 data=body, headers={"Content-Type": "application/json"})
    with _opener(cfg).open(req, timeout=20) as r:
        return json.loads(r.read().decode()).get("access_token")


def _qq_send(creds, token, openid, text, cfg):
    url = "https://api.sgroup.qq.com/v2/users/%s/messages" % openid
    body = json.dumps({"msg_type": 2, "markdown": {"content": text}, "msg_seq": 1}).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json", "Authorization": "QQBot " + token})
    with _opener(cfg).open(req, timeout=30) as r:
        return r.status == 200


def _llm_polish(cfg, text, role):
    base = (cfg.get("llm_base_url") or "").rstrip("/")
    model = cfg.get("llm_model")
    key = cfg.get("llm_key_override") or cfg.get("_host_key_plain") or ""
    if not base or not model or not key:
        return text
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content":
            "把下面这条提醒润色成一句自然、简短、符合 %s 角色口吻的话（不新增事实，保持原意）：%s" % (role, text)}],
        "max_tokens": 80}).encode()
    req = urllib.request.Request(base + "/chat/completions", data=body,
                                 headers={"Content-Type": "application/json",
                                          "Authorization": "Bearer " + key})
    with _opener(cfg).open(req, timeout=60) as r:
        j = json.loads(r.read().decode())
    return j["choices"][0]["message"]["content"].strip() or text


def _deliver(rows):
    db = plugin._conn({"_plugin_root": str(ROOT)})
    now = datetime.now()
    for nid, role, text, tod, dovr, repeat, nxt, _lastf, fail in rows:
        if not nxt or datetime.fromisoformat(nxt) > now:
            continue
        # Settings resolve per reminder's creating role.
        cfg = _cfg_for_role(role)
        final = text
        if cfg.get("llm_polish"):
            # Per-day cap so an accidental "polish on" can't burn LLM budget.
            today = datetime.now().strftime("%Y-%m-%d")
            st = db.execute("SELECT val FROM poll_state WHERE key='llm_calls_' || ?",
                            (today,)).fetchone()
            used = int(st[0]) if st else 0
            cap = int(cfg.get("llm_max_daily", 10))
            if used >= cap:
                _log("llm polish skipped for %s: daily cap %d reached; sending fixed text" % (role, cap))
            else:
                try:
                    final = _llm_polish(cfg, text, role)
                    db.execute("INSERT INTO poll_state(key,val) VALUES(?,1) "
                               "ON CONFLICT(key) DO UPDATE SET val=val+1",
                               ("llm_calls_" + today,))
                except Exception as e:
                    _log("llm polish failed (%s): %s; sending fixed text" % (type(e).__name__, e))
        creds = _creds(cfg.get("dsh_profile", "qqbot"))
        sent = False
        role_label = role
        try:
            from sunday_blue.storage import ROLES
            role_label = dict((r[0], r[1]) for r in ROLES).get(role, role)
        except Exception:
            pass
        test_url = (cfg.get("test_send_url") or "").strip()
        if test_url:
            # Test mode: POST the final text to the override endpoint instead of
            # the real QQ OpenAPI, so delivery can be verified without QQ.
            try:
                body = json.dumps({"role": role, "text": final}).encode()
                req = urllib.request.Request(test_url, data=body,
                                             headers={"Content-Type": "application/json"})
                with _opener(cfg).open(req, timeout=30) as r:
                    sent = r.status == 200
            except Exception as e:
                _log("reminder %d test_send_url error: %s" % (nid, e))
        elif not creds:
            _log("reminder %d: no DSH %s creds; stays pending" % (nid, cfg.get("dsh_profile", "qqbot")))
        elif not _gateway_alive():
            _log("reminder %d not sent: QQ gateway not alive; stays pending" % nid)
        else:
            try:
                tok = _token(creds, cfg)
                sent = _qq_send(creds, tok, cfg.get("qq_openid"), "%s：%s" % (role_label, final), cfg)
            except Exception as e:
                _log("reminder %d send error: %s" % (nid, e))
        if sent:
            if repeat == "daily" and tod:
                nf = now + timedelta(days=1)
                nf = nf.replace(hour=int(tod[:2]), minute=int(tod[3:5]), second=0, microsecond=0)
                db.execute("UPDATE rem SET last_fired=?, next_fire=?, fail_count=0 WHERE id=?",
                           (now.isoformat(timespec="seconds"), nf.isoformat(timespec="seconds"), nid))
            else:
                db.execute("UPDATE rem SET last_fired=?, done=1 WHERE id=?",
                           (now.isoformat(timespec="seconds"), nid))
            _log("reminder %d delivered -> %s" % (nid, role))
        else:
            fail += 1
            cap = int(cfg.get("delivery_max_retries", 5))
            if fail > cap:
                db.execute("UPDATE rem SET fail_count=?, done=1 WHERE id=?", (fail, nid))
                _log("reminder %d abandoned after %d failures" % (nid, fail))
            else:
                db.execute("UPDATE rem SET fail_count=?, next_fire=? WHERE id=?",
                            (fail, (now + timedelta(seconds=int(cfg.get("poll_interval", 15))))
                                .isoformat(timespec="seconds"), nid))
    db.commit()
    db.close()


def _tick(cfg):
    db = plugin._conn(cfg)
    rows = db.execute(
        "SELECT id, role, text, time_of_day, date_override, repeat, next_fire, last_fired, fail_count "
        "FROM rem WHERE done=0 AND next_fire IS NOT NULL").fetchall()
    db.close()
    _deliver(rows)


def _pid_alive(pid):
    """ctypes liveness probe (OpenProcess+GetExitCodeProcess), no third-party dep."""
    import ctypes
    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    code = ctypes.c_ulong()
    ok = ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
    ctypes.windll.kernel32.CloseHandle(handle)
    return bool(ok) and code.value == 259  # STILL_ACTIVE


def _single_instance():
    """Watchdog contract: the hourly Task Scheduler task may launch us repeatedly;
    only the first instance wins, the rest exit immediately (near-zero cost)."""
    lockf = ROOT / "data" / "plugins" / PLUGIN_ID / "daemon.lock"
    lockf.parent.mkdir(parents=True, exist_ok=True)
    if lockf.exists():
        try:
            pid = int(lockf.read_text(encoding="utf-8").strip() or 0)
            if pid and _pid_alive(pid):
                return False
        except ValueError:
            pass
    lockf.write_text(str(os.getpid()), encoding="utf-8")
    return True


def main():
    if not _single_instance():
        return
    _log("daemon starting (pid %d)" % os.getpid())
    while True:
        try:
            _tick({})
        except Exception as e:
            _log("tick error: %s" % e)
        # Poll interval resolves per role at delivery time; the sleep just spaces
        # out the low-cost db checks (default 15s keeps RAM/CPU near-zero).
        try:
            host = _settings()
            interval = 15
            for role in host.get("roles", {}):
                v = host["roles"][role].get("plugin_settings", {}).get(PLUGIN_ID, {})
                if isinstance(v.get("poll_interval"), int):
                    interval = v["poll_interval"]
                    break
            time.sleep(max(5, interval))
        except Exception:
            time.sleep(15)


if __name__ == "__main__":
    main()
