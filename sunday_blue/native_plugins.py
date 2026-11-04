"""Compatibility registry; plugins are discovered from external folders."""
from .plugin_runtime import discover,DEFAULT_ROOT
PLUGINS=discover()
def enabled(config,role,plugin):
    meta=discover(config.get('_plugin_root',DEFAULT_ROOT)).get(plugin)
    if not meta or meta.get('error'):return False
    return config.get('roles',{}).get(role,{}).get('native_plugins',{}).get(plugin,meta.get('default_enabled',False))
