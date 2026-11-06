"""Directory plugin discovery and schema reader. Local Python plugins are trusted code."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import threading

DEFAULT_ROOT=Path(__file__).resolve().parents[1]
_modules={}
_catalogs={}
_catalog_lock=threading.RLock()

def discover(root=DEFAULT_ROOT):
    # Repeated per-role lookups used to reopen every manifest/schema dozens of
    # times per turn. Refresh on file changes, including immediate uninstall.
    root=Path(root).resolve()
    paths=sorted((root/'extensions/plugins').glob('*/plugin.json'))
    fingerprint=[]
    for path in paths:
        for file in (path,path.parent/'_conf_schema.json',path.parent/'main.py'):
            try:
                stat=file.stat();fingerprint.append((str(file),stat.st_mtime_ns,stat.st_size))
            except FileNotFoundError:
                fingerprint.append((str(file),None,None))
    fingerprint=tuple(fingerprint)
    with _catalog_lock:
        cached=_catalogs.get(root)
        if cached and cached[0]==fingerprint:return cached[1]
        result=_read_catalog(paths)
        _catalogs[root]=(fingerprint,result)
        return result

def _read_catalog(paths):
    result={}
    for path in paths:
        try:
            meta=json.loads(path.read_text(encoding='utf-8-sig'))
            pid=meta['id']
            if not re.fullmatch(r'[a-zA-Z0-9_-]+',pid) or pid!=path.parent.name:raise ValueError('目录名必须与 id 相同')
            if meta.get('api_version')!=1 or meta.get('entry')!='main.py':raise ValueError('需要 api_version=1 和 entry=main.py')
            meta['path']=path.parent
            schema=path.parent/'_conf_schema.json'
            meta['schema']=json.loads(schema.read_text(encoding='utf-8-sig')) if schema.exists() else {}
            if not isinstance(meta['schema'],dict) or any(not isinstance(s,dict) or 'type' not in s for s in meta['schema'].values()):raise ValueError('参数 schema 应为字段对象映射')
            if not (path.parent/'main.py').is_file():raise ValueError('缺少 main.py')
            result[pid]=meta
        except (ValueError,KeyError,OSError,TypeError,AttributeError) as exc:
            result[path.parent.name]={'name':path.parent.name,'version':'错误','description':str(exc),'error':str(exc),'schema':{},'path':path.parent}
    return result

def load(pid,root=DEFAULT_ROOT):
    meta=discover(root).get(pid)
    if not meta or meta.get('error'):raise ValueError(f'插件 {pid} 不可加载：{(meta or {}).get("error","未安装")}')
    path=meta['path']/'main.py'
    key=(str(path.resolve()),path.stat().st_mtime_ns)
    if key not in _modules:
        spec=importlib.util.spec_from_file_location('sunday_plugin_'+hashlib.sha256(str(key).encode()).hexdigest()[:16],path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        _modules[key]=module
    return _modules[key]

def parameters(config,role,pid,root=None):
    meta=discover(root or config.get('_plugin_root',DEFAULT_ROOT)).get(pid,{})
    values={k:spec.get('default') for k,spec in meta.get('schema',{}).items()}
    if pid=='daypart-greetings':values.update(config.get('greetings',{}))
    values.update(config.get('roles',{}).get(role,{}).get('plugin_settings',{}).get(pid,{}))
    return values

def system_context(root,config,role):
    from .native_plugins import enabled
    parts=[]
    for pid,meta in discover(root).items():
        if enabled(config,role,pid,meta):
            module=load(pid,root)
            if hasattr(module,'system_context'):
                parts.append(module.system_context(parameters(config,role,pid,root)))
    return '\n'.join(p for p in parts if p)


def turn_hooks(root, config, role, hook, *args, on_error=lambda pid, exc: None):
    """Optional conversation hooks. Failure must not lose a user's conversation."""
    from .native_plugins import enabled
    results = []
    for pid, meta in discover(root).items():
        if meta.get('error') or not enabled(config, role, pid, meta):
            continue
        try:
            callback = getattr(load(pid, root), hook, None)
            if callback:
                result = callback(root, config, role, *args)
                if isinstance(result, str) and result:
                    results.append(result)
        except Exception as exc:
            on_error(pid, exc)
    return '\n\n'.join(results)
