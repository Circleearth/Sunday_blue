"""Explicit role retirement, dependency checks, export and restartable deletion.

No deletion tests may use the real application data. Recovery is roll-forward:
the approved operation journal and complete export remain until completion.
"""
import json
import os
from pathlib import Path
import shutil
import sqlite3
import uuid
import zipfile
from contextlib import closing

from .files import no_links
from .roles import RoleRegistry, LOCK
from .storage import atomic_json, now

KNOWN_PLUGINS = {'time-context', 'daypart-greetings', 'livingmemory', 'qq-reminders'}


def rows_at(path, query, args=()):
    if not path.exists():
        return []
    no_links(path)
    db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=3)
    db.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in db.execute(query, args)]
    finally:
        db.close()


class RoleLifecycle:
    def __init__(self, config, store, busy=lambda role: False):
        self.config, self.store, self.busy = config, store, busy
        self.root = config.root
        self.registry = RoleRegistry(self.root)
        self.operations = self.root / 'data/role_operations'

    def create(self, name):
        rid = self.registry.create(name)
        self.config.save()  # Adds empty permissions/bindings, never clones another role.
        return rid

    def rename(self, role, name):
        self.registry.get(role)
        self.registry.update(role, name=name)

    def dependencies(self, role):
        blockers = []
        if self.busy(role):
            blockers.append('该角色仍有聊天、记忆窗口或后台操作；请先结束或关闭。')
        qq = self.root / 'data/plugins/qq-reminders/state.sqlite3'
        try:
            pending = rows_at(qq, 'SELECT id FROM rem WHERE role=? AND done=0', (role,))
            if pending:
                blockers.append(f'尚有 {len(pending)} 条 QQ 提醒；请先用原插件取消提醒。')
        except sqlite3.Error:
            blockers.append('无法核对 QQ 提醒数据库，不能安全停用角色。')
        from .plugin_runtime import discover
        from .native_plugins import enabled
        config = self.config.snapshot()
        for spec in config.get('mcp_servers', []):
            if spec.get('enabled') and role in spec.get('roles', []):
                blockers.append(f'MCP {spec["name"]} 仍绑定此角色；请先停用该绑定并核对外部任务。')
        for pid, meta in discover(self.root).items():
            if pid not in KNOWN_PLUGINS and enabled(config, role, pid, meta):
                blockers.append(f'插件 {pid} 尚无已验证的角色清理适配；先停用并核对其外部任务。')
        for directory in (self.root / 'data/plugins').glob('*'):
            if directory.is_dir() and directory.name not in KNOWN_PLUGINS:
                blockers.append(f'存在未知插件数据 {directory.name}；需要清理适配器判定归属，不能猜测删除。')
        return blockers

    def _check_idle(self, role):
        blockers = self.dependencies(role)
        if blockers:
            raise ValueError('\n'.join(blockers))

    def archive(self, role):
        with LOCK:
            self.registry.get(role, active=True)
            if len(self.registry.records()) <= 1:
                raise ValueError('至少保留一个启用角色，请先创建或恢复另一个角色。')
            self._check_idle(role)
            from .living_memory import close_role
            close_role(self.root, role)
            self.registry.update(role, state='archived')

    def restore(self, role):
        with LOCK:
            if self.registry.get(role)['state'] != 'archived':
                raise ValueError('仅已归档角色可以直接恢复；删除中请使用继续清理。')
            self.registry.update(role, state='active')
            self.config.save()

    def paths(self, role):
        self.registry.get(role)
        relative = [f'personas/{role}', f'personas/_archive/{role}',
                    f'assets/roles/{role}', f'data/memory/{role}',
                    f'data/persona_versions/{role}', f'data/plugins/livingmemory/{role}']
        return [self.root / p for p in relative if (self.root / p).exists()]

    def inspect(self, role):
        record = self.registry.get(role)
        sessions = self.store.sessions(role, include_archived=True)
        return dict(role=record, sessions=len(sessions), paths=[str(p.relative_to(self.root)) for p in self.paths(role)],
                    blockers=self.dependencies(role),
                    retained='保留已授权共享的协作记录及来源、共享插件代码、Ollama 模型、外部工作区、全局连接和离线历史备份。')

    def _capture(self, role):
        with self.store.connect() as db:
            sessions = [dict(r) for r in db.execute('SELECT * FROM sessions WHERE role=?', (role,))]
            messages = [dict(r) for r in db.execute('SELECT m.* FROM messages m JOIN sessions s ON m.session=s.id WHERE s.role=?', (role,))]
            audit = [dict(r) for r in db.execute('SELECT * FROM audit WHERE role=?', (role,))]
        ids = [s['id'] for s in sessions]
        extra = {}
        greet = self.root / 'data/plugins/daypart-greetings/state.sqlite3'
        if greet.exists():
            tables = {r['name'] for r in rows_at(greet, "SELECT name FROM sqlite_master WHERE type='table'")}
            for table in ('seen', 'activity'):
                if table in tables:
                    extra['greetings.' + table] = rows_at(greet, f'SELECT * FROM {table} WHERE role=?', (role,))
            for table in ('events', 'triggers'):
                if table in tables:
                    extra['greetings.' + table] = [r for sid in ids for r in rows_at(greet, f'SELECT * FROM {table} WHERE session=?', (sid,))]
        qq = self.root / 'data/plugins/qq-reminders/state.sqlite3'
        if qq.exists():
            extra['qq.rem'] = rows_at(qq, 'SELECT * FROM rem WHERE role=?', (role,))
        from .role_events import EventLedger
        events = EventLedger(self.store).export_role(role)
        return dict(version=1, at=now(), role=self.registry.get(role), sessions=sessions, messages=messages, events=events,
                    audit=audit, plugin_rows=extra, settings=self.config.value['roles'].get(role, {}),
                    role_font=self.config.value.get('chat_display', {}).get('role_fonts', {}).get(role),
                    mcp_bindings=[s['name'] for s in self.config.value.get('mcp_servers', []) if role in s.get('roles', [])])

    def export(self, role, destination):
        self._check_idle(role)
        from .living_memory import close_role
        close_role(self.root, role)
        destination = Path(destination).resolve()
        no_links(destination)
        if destination.exists():
            raise ValueError('导出文件已存在，请选择新文件名。')
        snapshot = self._capture(role)
        source_paths = self.paths(role)
        if any(p == destination or p in destination.parents for p in source_paths):
            raise ValueError('不能导出到待清理的角色目录内。')
        destination.parent.mkdir(parents=True, exist_ok=True)
        tmp = destination.with_name(destination.name + '.tmp-' + uuid.uuid4().hex)
        try:
            with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as z:
                z.writestr('record.json', json.dumps(snapshot, ensure_ascii=False, indent=2))
                for base in source_paths:
                    no_links(base)
                    for p in base.rglob('*'):
                        no_links(p)
                        if p.is_file():
                            z.write(p, 'files/' + p.relative_to(self.root).as_posix())
            with zipfile.ZipFile(tmp) as z:
                if z.testzip() is not None:
                    raise RuntimeError('角色备份校验失败，未删除任何数据。')
            os.replace(tmp, destination)
        finally:
            tmp.unlink(missing_ok=True)
        return destination

    def delete(self, role, confirmed=False):
        if not confirmed:
            raise ValueError('必须先展示删除范围并由用户明确确认。')
        with LOCK:
            if self.registry.get(role)['state'] != 'archived':
                raise ValueError('请先归档角色，再执行永久删除。')
            self._check_idle(role)
            operation = uuid.uuid4().hex
            folder = self.operations / operation
            no_links(folder)
            folder.mkdir(parents=True)
            backup = self.export(role, folder / 'backup.zip')
            manifest = dict(version=1, id=operation, role=role, state='approved', backup=backup.name,
                            paths=[p.relative_to(self.root).as_posix() for p in self.paths(role)], at=now())
            journal = folder / 'operation.json'
            atomic_json(journal, manifest)
            self._resume(journal)
            return backup

    def resume_pending(self):
        errors = []
        for journal in sorted(self.operations.glob('*/operation.json')):
            try:
                self._resume(journal)
            except Exception as exc:
                errors.append(f'{journal.parent.name}：{exc}')
        return errors

    def _resume(self, journal):
        with LOCK:
            no_links(journal)
            manifest = json.loads(journal.read_text(encoding='utf-8'))
            if manifest['state'] == 'done':
                return
            role = manifest['role']
            self._check_idle(role)
            backup = journal.parent / 'backup.zip'
            no_links(backup)
            with zipfile.ZipFile(backup) as z:
                if z.testzip() is not None:
                    raise ValueError('备份损坏；停止恢复，请保留现场。')
                record = json.loads(z.read('record.json'))
                if record['role']['id'] != role:
                    raise ValueError('备份角色不匹配')
            from .living_memory import close_role
            close_role(self.root, role)
            self.registry.update(role, state='deleting')
            ids = [s['id'] for s in record['sessions']]
            # Idempotent steps. A crash never makes a partially removed role runnable.
            self._purge_shared(role, ids)
            allowed = {f'personas/{role}', f'personas/_archive/{role}', f'assets/roles/{role}',
                       f'data/memory/{role}', f'data/persona_versions/{role}', f'data/plugins/livingmemory/{role}'}
            for relative in manifest['paths']:
                if relative not in allowed:
                    raise ValueError('删除日志包含未知范围，拒绝执行。')
                p = self.root / relative
                no_links(p)
                if p.exists():
                    for child in p.rglob('*'): no_links(child)
                    shutil.rmtree(p)
            with self.store.connect() as db:
                from .role_events import EventLedger
                EventLedger.retire_role(db, role)
                db.execute('DELETE FROM messages WHERE session IN (SELECT id FROM sessions WHERE role=?)', (role,))
                db.execute('DELETE FROM audit WHERE role=?', (role,))
                db.execute('UPDATE sessions SET parent=NULL WHERE parent IN (SELECT id FROM sessions WHERE role=?) AND role<>?', (role, role))
                db.execute('DELETE FROM sessions WHERE role=?', (role,))
            self.config.value.get('roles', {}).pop(role, None)
            self.config.save()
            self.registry.update(role, state='deleted')  # Tombstone prevents ID reuse.
            manifest['state'] = 'done'
            atomic_json(journal, manifest)

    def _purge_shared(self, role, session_ids):
        greet = self.root / 'data/plugins/daypart-greetings/state.sqlite3'
        if greet.exists():
            no_links(greet)
            with closing(sqlite3.connect(greet, timeout=3)) as db, db:
                tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                for table in ('seen', 'activity'):
                    if table in tables: db.execute(f'DELETE FROM {table} WHERE role=?', (role,))
                for table in ('events', 'triggers'):
                    if table in tables: db.executemany(f'DELETE FROM {table} WHERE session=?', [(s,) for s in session_ids])
        qq = self.root / 'data/plugins/qq-reminders/state.sqlite3'
        if qq.exists():
            no_links(qq)
            with closing(sqlite3.connect(qq, timeout=3)) as db, db:
                if db.execute('SELECT 1 FROM rem WHERE role=? AND done=0', (role,)).fetchone():
                    raise ValueError('出现新的 QQ 提醒，已暂停删除。')
                db.execute('DELETE FROM rem WHERE role=? AND done=1', (role,))
