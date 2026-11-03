"""Explicit registry of trusted host plugins; no dynamic third-party execution."""
PLUGINS = {
    'time-context': {'name': '时间上下文', 'version': '1.1.0',
                     'description': '把本轮日期与时间加入模型背景，不显示气泡。'},
    'daypart-greetings': {'name': '时段寒暄', 'version': '1.0.0',
                         'description': '本地规则和文案：每时段首次寒暄，凌晨可重复催睡；不调用 LLM。'},
}

def enabled(config, role, plugin):
    return config.get('roles', {}).get(role, {}).get('native_plugins', {}).get(plugin, True)
