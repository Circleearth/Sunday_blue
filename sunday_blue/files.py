"""Allowlisted text file tools, reparse/hardlink checks, reviewed atomic writes."""
from __future__ import annotations
import difflib
import hashlib
import json
import os
import shutil
from pathlib import Path
import stat
import threading
import uuid

WRITE_LOCK = threading.Lock()
MAX_FILE = 1024 * 1024

def inside(path, root):
    return path == root or root in path.parents

def no_links(path):
    for node in (path, *path.parents):
        try:
            s = node.lstat()
        except FileNotFoundError:
            continue
        if node.is_symlink() or getattr(s, 'st_file_attributes', 0) & 0x400:
            raise PermissionError('不允许通过符号链接或 Windows 联接点访问文件。')
        if node == path and stat.S_ISREG(s.st_mode) and s.st_nlink > 1:
            raise PermissionError('不允许访问硬链接文件。')

class FileTools:
    def __init__(self, root, role, rules, approve, audit):
        self.root = Path(root).resolve()
        self.role = role
        self.rules = rules
        self.approve = approve
        self.audit = audit
        self.cancelled=lambda:False

    def request(self,title,path,detail,other=None):
        if self.cancelled():return False
        def trusted(value):
            p=self.check(str(value),True)
            rules=[r for r in self.rules if inside(p,Path(r['path']).resolve())]
            rule=max(rules,key=lambda r:len(Path(r['path']).parts))
            return rule.get('write') and rule.get('trusted',False)
        if trusted(path) and (other is None or trusted(other)):
            self.audit('trusted_auto_approval',json.dumps({'action':title,'path':str(path),'destination':str(other) if other else None},ensure_ascii=False))
            return True
        return self.approve(title,str(path),detail)

    def check(self, value, write=False):
        p = Path(value)
        if not p.is_absolute() or '..' in p.parts:
            raise PermissionError('请提供已授权目录内的绝对路径。')
        # Forbid UNC/device paths and NTFS alternate streams.
        if str(p).startswith(('\\\\', '//')) or ':' in str(p)[len(p.drive):]:
            raise PermissionError('不支持网络路径、设备路径或 NTFS 备用数据流。')
        no_links(p)
        resolved = p.resolve()
        if inside(resolved, self.root):
            raise PermissionError('软件自身文件由设置界面管理；持久记忆请使用 memory 工具。')
        for rule in self.rules:
            base = Path(rule['path'])
            no_links(base)
            if base.is_absolute() and inside(resolved, base.resolve()) and (not write or rule.get('write')):
                return resolved
        raise PermissionError('该路径未在此角色的文件权限中授权' + ('写入。' if write else '读取。'))

    def read(self, path):
        p = self.check(path)
        if p.stat().st_size > MAX_FILE:
            raise ValueError('单文件最多读取 1 MiB UTF-8 文本。')
        return p.read_text(encoding='utf-8-sig')

    def list(self, path):
        p = self.check(path)
        items = []
        for f in sorted(p.iterdir(), key=lambda x: x.name.lower())[:300]:
            try:
                self.check(str(f))
                items.append({'name': f.name, 'directory': f.is_dir(), 'size': f.stat().st_size if f.is_file() else None})
            except (OSError, ValueError):
                continue
        return items

    def search(self, path, query):
        if not query:
            raise ValueError('搜索词不能为空。')
        base = self.check(path)
        matches, scanned, visited = [], 0, 0
        for current, dirs, files in os.walk(base, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d not in {'.git', 'node_modules', '.venv', '__pycache__'})
            safe_dirs = []
            for d in dirs:
                try:
                    self.check(str(Path(current) / d))
                    safe_dirs.append(d)
                except (OSError, ValueError):
                    pass
            dirs[:] = safe_dirs
            for name in sorted(files):
                visited += 1
                if visited > 1500:
                    return {'matches': matches, 'truncated': True, 'scanned': scanned}
                p = Path(current) / name
                try:
                    text = self.read(str(p))
                    scanned += 1
                except (OSError, ValueError, UnicodeError):
                    continue
                for n, line in enumerate(text.splitlines(), 1):
                    if query.casefold() in line.casefold():
                        matches.append({'path': str(p), 'line': n, 'text': line[:500]})
                        if len(matches) >= 100:
                            return {'matches': matches, 'truncated': True, 'scanned': scanned}
        return {'matches': matches, 'truncated': False, 'scanned': scanned}

    def write(self, path, content=None, old_text=None, new_text=None, memory=False):
        if memory:
            p = self.root / 'data' / 'memory' / self.role / 'long_term.md'
            no_links(p)
        else:
            p = self.check(path, True)
        if p.exists() and p.stat().st_size > MAX_FILE:
            raise ValueError('文件过大，当前编辑器仅处理 1 MiB 内的 UTF-8 文本。')
        original = p.read_bytes() if p.exists() else None
        before = original.decode('utf-8-sig') if original is not None else ''
        if old_text is not None:
            if not old_text or before.count(old_text) != 1:
                raise ValueError('精确替换必须恰好匹配一处非空文本；请先读取文件。')
            content = before.replace(old_text, new_text, 1)
        if not isinstance(content, str) or len(content.encode('utf-8')) > MAX_FILE:
            raise ValueError('写入内容必须是 1 MiB 内的文本。')
        if content == before and original is not None:
            return {'status': 'unchanged', 'path': str(p)}
        diff = ''.join(difflib.unified_diff(before.splitlines(True), content.splitlines(True), fromfile=str(p), tofile=str(p)))
        accepted=self.approve('持久记忆更新',str(p),diff) if memory else self.request('文件修改',p,diff)
        if not accepted:
            self.audit('write_denied', str(p))
            return {'status': 'denied', 'path': str(p)}
        with WRITE_LOCK:
            if not memory:
                self.check(str(p), True)
            no_links(p)
            current = p.read_bytes() if p.exists() else None
            if current != original:
                raise RuntimeError('文件在确认期间发生变化，本次未写入；请重新读取并审阅。')
            backup = None
            if original is not None:
                backup = self.root / 'data' / 'backups' / (uuid.uuid4().hex + '.bak')
                backup.parent.mkdir(parents=True, exist_ok=True)
                backup.write_bytes(original)
            p.parent.mkdir(parents=True, exist_ok=True)
            no_links(p.parent)
            tmp = p.with_name('.' + p.name + '.' + uuid.uuid4().hex + '.tmp')
            try:
                data = content.encode('utf-8')
                if original and original.startswith(b'\xef\xbb\xbf'):
                    data = b'\xef\xbb\xbf' + data
                tmp.write_bytes(data)
                no_links(p)
                os.replace(tmp, p)
            finally:
                tmp.unlink(missing_ok=True)
            result = {'status': 'written', 'path': str(p), 'backup': str(backup) if backup else None,
                      'sha256': hashlib.sha256(data).hexdigest()}
            self.audit('write', json.dumps(result, ensure_ascii=False))
            return result

    def _check_move_dest(self, source, dest):
        # Destination must stay inside an authorized directory, never above its source.
        dest = Path(dest)
        if not dest.is_absolute() or '..' in dest.parts:
            raise PermissionError('请提供已授权目录内的绝对路径。')
        if str(dest).startswith(('\\\\', '//')) or ':' in str(dest)[len(dest.drive):]:
            raise PermissionError('不支持网络路径、设备路径或 NTFS 备用数据流。')
        no_links(dest)
        dest = dest.resolve()
        if dest.is_dir():dest=dest/source.name
        if inside(dest, source) or inside(source,dest):
            raise PermissionError('目标不能位于源目录内部。')
        try:
            self.check(str(dest), True)
        except PermissionError:
            return None
        if source.drive.lower()!=dest.drive.lower():raise ValueError('暂只支持同卷移动。')
        return dest

    def create_directory(self, path):
        self.check(path, True)
        detail = f'在 {path} 创建文件夹（含中间层级）。'
        if not self.request('创建文件夹', path, detail):
            self.audit('mkdir_denied', str(path))
            return {'status': 'denied', 'path': str(path)}
        p = self.check(str(path), True)
        p.mkdir(parents=True, exist_ok=True)
        self.audit('mkdir', json.dumps({'path': str(p)}, ensure_ascii=False))
        return {'status': 'created', 'path': str(p)}

    def _inventory(self,path):
        paths=[path]
        if path.is_dir():
            for current,dirs,files in os.walk(path,followlinks=False):
                for name in dirs+files:
                    p=Path(current)/name;self.check(str(p),True);paths.append(p)
                    if len(paths)>10000:raise ValueError('一次删除最多 10000 项，请缩小范围。')
        result={}
        for p in paths:
            self.check(str(p),True);s=p.stat()
            result[str(p)]=(s.st_mode,s.st_size,s.st_mtime_ns,s.st_ino)
        return result

    def _delete(self,path,directory):
        p=self.check(str(path),True)
        if any(p==Path(r['path']).resolve() for r in self.rules):raise PermissionError('不能删除授权根目录本身。')
        if (directory and not p.is_dir()) or (not directory and not p.is_file()):raise ValueError('目标类型不符或不存在。')
        before=self._inventory(p)
        if sum(v[1] for v in before.values() if stat.S_ISREG(v[0]))>512*1024*1024:raise ValueError('一次删除备份最多 512 MiB。')
        title='删除文件夹' if directory else '删除文件'
        detail='删除前会复制完整备份到 data/backups/deleted。\n'+'\n'.join(list(before)[:100])+f'\n共 {len(before)} 项。'
        if not self.request(title,p,detail):return {'status':'denied','path':str(p)}
        with WRITE_LOCK:
            self.check(str(p),True)
            if self.cancelled():return {'status':'denied','path':str(p)}
            if self._inventory(p)!=before:raise RuntimeError('目标在确认期间变化，请重新检查。')
            backup=self.root/'data/backups/deleted'/uuid.uuid4().hex
            backup.mkdir(parents=True)
            if directory:shutil.copytree(p,backup/p.name)
            else:shutil.copy2(p,backup/p.name)
            (backup/'restore.json').write_text(json.dumps({'original':str(p),'backup':str(backup/p.name)},ensure_ascii=False),encoding='utf-8')
            if self._inventory(p)!=before:raise RuntimeError('备份期间目标变化，本次未删除。')
            if directory:shutil.rmtree(p)
            else:p.unlink()
        result={'status':'deleted','path':str(p),'backup':str(backup/p.name),'items':len(before)}
        self.audit('rmdir' if directory else 'delete_file',json.dumps(result,ensure_ascii=False))
        return result

    def delete_directory(self,path):return self._delete(path,True)
    def delete_file(self,path):return self._delete(path,False)

    def move(self, source, destination):
        src = self.check(str(source), True)
        dest = self._check_move_dest(src, destination)
        if dest is None:
            return {'status': 'denied', 'path': str(destination), 'reason': '目标目录未授权写入。'}
        detail = f'将 {src} 移动到 {dest}（同卷改名移动；目标已存在时会被拒绝）。'
        if not self.request('移动文件/文件夹', src, detail,other=dest):
            self.audit('move_denied', f'{src} -> {dest}')
            return {'status': 'denied', 'source': str(src), 'destination': str(dest)}
        with WRITE_LOCK:
            self.check(str(src),True);self.check(str(dest),True)
            if any(src==Path(r['path']).resolve() for r in self.rules):raise PermissionError('不能移动授权根目录。')
            if not src.exists():
                raise RuntimeError('源已不存在，本次未移动。')
            if dest.exists():
                raise ValueError('目标已存在，请换一个名称；避免覆盖。')
            os.rename(src, dest)
        self.audit('move', json.dumps({'source': str(src), 'destination': str(dest)}, ensure_ascii=False))
        return {'status': 'moved', 'source': str(src), 'destination': str(dest)}

def schema(name, description, props, required):
    return {'name': name, 'description': description, 'input_schema': {'type': 'object', 'properties': props, 'required': required, 'additionalProperties': False}}

S = {'type': 'string'}
FILE_SCHEMAS = [
    schema('list_files', '列出角色已授权目录的直接子项，不递归。必须用绝对路径。', {'path': S}, ['path']),
    schema('read_file', '读取已授权的 UTF-8 文本，最大 1 MiB。', {'path': S}, ['path']),
    schema('search_files', '在已授权目录搜索文本，跳过常见依赖目录，最多 1500 文件/100 命中。', {'path': S, 'query': S}, ['path', 'query']),
    schema('write_file', '新建或覆盖 UTF-8 文件，必须在可写目录；用户将审阅差异。优先 edit_file。', {'path': S, 'content': S}, ['path', 'content']),
    schema('edit_file', '精确替换一处文本并展示差异；old_text 必须唯一匹配。', {'path': S, 'old_text': S, 'new_text': S}, ['path', 'old_text', 'new_text']),
    schema('create_directory', '在可写目录内新建文件夹（可含中间层级）。', {'path': S}, ['path']),
    schema('delete_directory', '删除授权目录内的子文件夹及内容，删除前完整备份；信任工作区自动批准。', {'path': S}, ['path']),
    schema('delete_file', '删除授权可写目录内的文件，删除前备份；信任工作区自动批准。', {'path': S}, ['path']),
    schema('move', '移动文件或文件夹；目标必须在可写目录内，目标已存在会被拒绝。', {'source': S, 'destination': S}, ['source', 'destination']),
]
MEMORY_SCHEMAS = [
    schema('memory_read', '读取当前角色的持久记忆，同一角色所有会话共享。', {}, []),
    schema('memory_write', '更新当前角色持久记忆；保留其他有效事实和来源，用户确认后保存。', {'content': S}, ['content']),
]
