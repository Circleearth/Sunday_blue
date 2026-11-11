"""A small per-turn capability router, using existing tools and plugin contracts.

Identity is not a permission grant. Deterministic @references/keywords activate
allowed bindings; ambiguous semantic selection uses a normal model tool call.
"""
import copy
import re
from .native_plugins import enabled
from .plugin_runtime import discover

BUILTINS = {'files': '授权目录的文件读写', 'memory': '本角色已确认记忆（写入需审阅）',
            'mcp': '该角色已绑定的 MCP 服务（启动和调用需审阅）',
            'collaboration': '受控协作记录（决定、待办与完成状态需确认）',
            'activity': '现实记录与专注统计（只读）', 'duties': '当前固定职责的数据管理与交接'}
ALWAYS = {'plugin:time-context', 'plugin:daypart-greetings'}
RESPONSIBILITIES = {
    'kia': '默认负责记录、归档、信息提取与初步分类；不要把记录自动升级为完整规划或已确认决定。',
    'rui': '默认负责跨模块信息汇总、优先级判断、规划、复盘与策略建议；建议不等于用户已确认决定。',
    'mia': '默认负责日常聊天、陪伴与情绪交流；不要把日常交流强制转成任务管理。',
    'red': '负责运动领域的监督与执行建议。', 'ewa': '负责饮食领域的监督与执行建议。',
    'luna': '负责睡眠领域的监督与执行建议。', 'loluns': '负责学习领域的监督与执行建议。',
}


def allowed_catalog(root, config, role):
    config = config | {'_plugin_root': str(root)}
    cfg = config['roles'][role]
    result = {name: label for name, label in BUILTINS.items()
              if config['features'].get(name, name in ('collaboration','activity'))
              and cfg.get('capabilities', {}).get(name, role in ('rui','kia') if name=='activity' else name != 'collaboration')}
    from .modules.duties import assigned
    if assigned(root,role) and config['features'].get('duties',True) and cfg.get('capabilities',{}).get('duties',True):result['duties']=BUILTINS['duties']
    else:result.pop('duties',None)
    if 'mcp' in result and not any(s.get('enabled') and role in s.get('roles', []) for s in config.get('mcp_servers', [])):
        result.pop('mcp')
    from .modules.duties import effective_extensions
    bound=effective_extensions(root,role)
    for name in dict.fromkeys(cfg.get('skills', [])+bound['skills']):
        result['skill:' + name] = name + '（已授权 Skill）'
    for name in dict.fromkeys(cfg.get('plugins', [])):
        result['prompt:' + name] = name + '（已授权提示词模块）'
    for pid, meta in discover(root).items():
        if meta.get('module_only'):continue
        if enabled(config, role, pid, meta):
            result['plugin:' + pid] = (meta.get('name', pid) + '：' + meta.get('description', ''))[:160]
    return result


class TurnCapabilities:
    def __init__(self, root, config, role, user_text=''):
        self.root, self.base, self.role = root, copy.deepcopy(config), role
        self.catalog = allowed_catalog(root, config, role)
        self.active = set()
        policies = config['roles'][role].get('capability_loading', {})
        from .modules.duties import effective_extensions
        bound=effective_extensions(root,role)
        self.bound=bound
        deferred={'skill:'+name for name in bound['skills'] if name not in config['roles'][role].get('skills',[])}|{'plugin:'+name for name in bound['plugins']}
        for key in self.catalog:
            default={'mode':'on_demand','keywords':'工作,任务,运动,饮食,睡眠,精力,记录,整理,复盘,学习,汇总,手机,屏幕'} if key=='duties' else {'mode':'on_demand'} if key in deferred else {}
            spec = policies.get(key,default)
            keywords = [s.strip() for s in spec.get('keywords', '').split(',') if s.strip()]
            explicit = re.search(r'(?<!\w)@' + re.escape(key) + r'(?![\w:-])', user_text)
            if (key in ALWAYS or spec.get('mode', 'always') == 'always' or explicit
                    or any(k.casefold() in user_text.casefold() for k in keywords)):
                self.active.add(key)

    def activate(self, capability):
        if capability not in self.catalog:
            raise PermissionError('角色未获授权使用此能力；只能在设置中由用户授权。')
        self.active.add(capability)
        return {'status': 'activated', 'capability': capability, 'note': '下次模型请求可用；权限与审阅规则保持不变。'}

    def snapshot(self):
        config = copy.deepcopy(self.base)
        role = config['roles'][self.role]
        for key in BUILTINS:
            config['features'][key] = key in self.active
        from .modules.duties import effective_extensions
        bound=effective_extensions(self.root,self.role)
        role['skills'] = [name for name in dict.fromkeys(role.get('skills', [])+bound['skills']) if 'skill:' + name in self.active]
        role['plugins'] = [name for name in dict.fromkeys(role.get('plugins', [])) if 'prompt:' + name in self.active]
        role['native_plugins'] = {pid: 'plugin:' + pid in self.active for pid in discover(self.root)}
        return config

    def loader_tool(self):
        available = {key: value for key, value in self.catalog.items() if key not in self.active}
        if not available:
            return []
        return [{'name': 'activate_capability',
                 'description': '按本次任务需要加载已授权能力。每次只加载需要的一项；不要为了聊天加载全部能力。可选：'
                                + '；'.join(k + ' — ' + v for k, v in available.items()),
                 'input_schema': {'type':'object', 'properties': {'capability': {'type':'string', 'enum':list(available)}},
                                  'required':['capability']}}]
