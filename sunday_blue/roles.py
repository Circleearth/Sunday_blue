"""Root-scoped role identity registry. Display names never become storage paths."""
import copy
import json
from pathlib import Path
import re
import threading
import uuid

LOCK = threading.RLock()
DEFAULT_ROLES = (
    ('rui', 'Rui', '统筹 · 规划与复盘', '#7cb7ff'),
    ('red', 'Red', '运动 · 训练管理', '#ee8e96'),
    ('ewa', 'Ewa', '饮食 · 营养规划', '#deb889'),
    ('luna', 'Luna', '睡眠 · 安静陪伴', '#b4a0e5'),
    ('loluns', 'Loluns', '学习 · 成长计划', '#8dcbbb'),
    ('kia', 'Kia', '记录 · 提取与归档', '#c3bcaa'),
    ('mia', 'Mia', '日常 · 陪伴与交流', '#96c4d3'),
    ('ticktick', 'TickTick', '任务 · 日程执行', '#cbb779'),
    ('mubu', 'Mubu', '大纲 · 思路整理', '#afaed9'),
)


class RoleRegistry:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.path = self.root / 'data/roles.json'

    def read(self):
        from .files import no_links
        no_links(self.path)
        if not self.path.exists():
            return {'version': 1, 'roles': [dict(id=r, name=n, description=d, color=c, state='active')
                                          for r, n, d, c in DEFAULT_ROLES]}
        data = json.loads(self.path.read_text(encoding='utf-8'))
        if data.get('version') != 1 or not isinstance(data.get('roles'), list):
            raise ValueError('角色注册文件版本或格式不支持；请从备份恢复，不能重置为默认角色。')
        seen = set()
        for r in data['roles']:
            if (not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', r['id']) or r['id'] in seen
                    or r['state'] not in ('active', 'archived', 'deleting', 'deleted')
                    or not isinstance(r['name'], str) or not r['name'].strip()
                    or not re.fullmatch(r'#[0-9a-fA-F]{6}', r['color'])):
                raise ValueError('角色注册文件含无效或重复身份。')
            seen.add(r['id'])
        return data

    def initialize(self):
        from .storage import atomic_json
        with LOCK:
            if not self.path.exists():
                atomic_json(self.path, self.read())

    def records(self, states=('active',)):
        return [copy.deepcopy(r) for r in self.read()['roles'] if r['state'] in states]

    def get(self, rid, active=False):
        record = next((r for r in self.read()['roles'] if r['id'] == rid), None)
        if record is None or record['state'] == 'deleted' or (active and record['state'] != 'active'):
            raise ValueError('角色不存在或已停用，请刷新角色列表。')
        return copy.deepcopy(record)

    def update(self, rid, **fields):
        from .storage import atomic_json
        if not set(fields) <= {'name', 'description', 'color', 'state'}:
            raise ValueError('角色 ID 不可修改')
        with LOCK:
            data = self.read()
            record = next(r for r in data['roles'] if r['id'] == rid)
            if 'name' in fields:
                fields['name'] = self.validate_name(fields['name'])
            if 'state' in fields and fields['state'] not in ('active','archived','deleting','deleted'):
                raise ValueError('无效角色状态')
            record.update(fields)
            atomic_json(self.path, data)

    @staticmethod
    def validate_name(name):
        name = str(name).strip()
        if not name or len(name) > 40 or any(ord(c) < 32 for c in name):
            raise ValueError('显示名称需为 1–40 个可见字符。')
        return name

    def create(self, name, description='独立角色'):
        from .storage import atomic_json
        from .files import no_links
        name = self.validate_name(name)
        rid = 'role_' + uuid.uuid4().hex
        with LOCK:
            data = self.read()
            # Publish the identity only after initial files are ready. Orphaned files
            # after a crash are inert, never auto-discovered as roles.
            folder = self.root / 'personas' / rid
            no_links(folder)
            folder.mkdir(parents=True)
            initial = {'identity.md': '你是独立角色。显示名称由宿主提供；用户是委托者，有权自行决定。',
                       'personality.md': '尊重用户意愿；不编造共同经历。',
                       'voice.md': '自然、清楚地表达；不机械重复身份。',
                       'relationships.md': '角色关系不授予访问其他角色私人记忆的权限。'}
            for filename, value in initial.items():
                (folder / filename).write_text(value + '\n', encoding='utf-8')
            memory = self.root / 'data/memory' / rid / 'long_term.md'
            no_links(memory)
            memory.parent.mkdir(parents=True)
            memory.write_text('# 已确认记忆\n\n暂无已确认的用户事实。\n', encoding='utf-8')
            (self.root / 'assets/roles' / rid).mkdir(parents=True, exist_ok=True)
            data['roles'].append(dict(id=rid, name=name, description=str(description)[:120],
                                      color='#96c4d3', state='active'))
            atomic_json(self.path, data)
        return rid


def list_roles(root=None, include_archived=False):
    if root is None:
        from .storage import root_path
        root = root_path()
    states = ('active', 'archived') if include_archived else ('active',)
    return [(r['id'], r['name'], r['description'], r['color']) for r in RoleRegistry(root).records(states)]


def require_role(root, role, active=True):
    return RoleRegistry(root).get(role, active=active)


class LegacyRoles:
    """Read-only compatibility for external plugins; new code must pass its root."""
    def __iter__(self):
        return iter(list_roles())
    def __len__(self):
        return len(list_roles())
    def __getitem__(self, index):
        return list_roles()[index]
