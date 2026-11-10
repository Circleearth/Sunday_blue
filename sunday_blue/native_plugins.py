"""Compatibility registry; plugins are discovered from external folders."""
from .plugin_runtime import discover,DEFAULT_ROOT
PLUGINS=discover()
def enabled(config,role,plugin,meta=None):
    from .roles import require_role
    try: require_role(config.get('_plugin_root', DEFAULT_ROOT), role)
    except ValueError: return False
    if meta is None:meta=discover(config.get('_plugin_root',DEFAULT_ROOT)).get(plugin)
    if not meta or meta.get('error'):return False
    if meta.get('allowed_roles') and role not in meta['allowed_roles']:return False
    role_config=config.get('roles',{}).get(role,{})
    return role_config.get('native_plugins',{}).get(plugin,role_config.get('native_plugins_default',meta.get('default_enabled',False)))
