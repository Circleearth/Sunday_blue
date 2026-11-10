"""Pure, retry-safe event plugin. No private history and no automatic model calls."""
from sunday_blue.plugin_runtime import parameters


def on_module_event(root,config,role,event):
    if event['kind']!='focus.completed' or event['payload'].get('role_id')!=role:
        return ''
    record=event['payload']
    closing=parameters(config,role,'focus-cheer',root)['closing']
    return f"{record['category']} {int(record['seconds']//60)} 分钟，记下了。{closing}"
