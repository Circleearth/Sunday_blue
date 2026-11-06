"""Four editable personality sections; only explicit user settings can write them."""
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import uuid
from .files import WRITE_LOCK, no_links
from .storage import ROLE_IDS, atomic_json

SECTIONS = (
    ('identity.md', '身份内核', '是谁、核心气质与不能随意改变的边界。只有你能修改。'),
    ('personality.md', '性格与反应', '如何看待事情、如何关心你、遇到压力和分歧时怎样反应。'),
    ('voice.md', '说话方式', '语气、句式、称呼和对话示例。'),
    ('relationships.md', '角色关系', '角色间的关系和互动风格；设定不等于真实经历，也不授予工具权限。'),
)
FILENAMES = {item[0] for item in SECTIONS}


def read_persona(root, role):
    if role not in ROLE_IDS:
        raise ValueError('未知角色')
    result = {}
    for filename, *_ in SECTIONS:
        path = Path(root) / 'personas' / role / filename
        no_links(path)
        result[filename] = path.read_text(encoding='utf-8') if path.exists() else ''
    return result


def persona_text(root, role):
    return '\n\n'.join(text for text in read_persona(root, role).values() if text.strip())


def save_persona(root, role, before, after):
    root = Path(root).resolve()
    if role not in ROLE_IDS or set(after) != FILENAMES:
        raise ValueError('人格字段不完整或包含未知文件')
    if not after['identity.md'].strip():
        raise ValueError('身份内核不能为空')
    if any(not isinstance(value, str) or len(value.encode('utf-8')) > 65536 for value in after.values()):
        raise ValueError('每个人格栏目最多 64 KiB')
    if before == after:
        return None
    with WRITE_LOCK:
        if read_persona(root, role) != before:
            raise RuntimeError('人格文件已被其他窗口或编辑器修改，请重新打开后编辑。')
        version = datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8]
        backup = root / 'data/persona_versions' / role / (version + '.json')
        no_links(backup)
        atomic_json(backup, {'role': role, 'created': datetime.now().isoformat(),
                             'before': before, 'after': after,
                             'sha256': {name: hashlib.sha256(value.encode()).hexdigest() for name,value in after.items()}})
        written = []
        try:
            for filename, value in after.items():
                if value == before[filename]:
                    continue
                path = root / 'personas' / role / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                no_links(path)
                original = path.read_bytes() if path.exists() else None
                temp = path.with_name('.' + filename + '.' + version + '.tmp')
                try:
                    temp.write_text(value, encoding='utf-8', newline='')
                    os.replace(temp, path)
                finally:
                    temp.unlink(missing_ok=True)
                written.append((path, original))
        except Exception:
            for path, original in reversed(written):
                if original is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_bytes(original)
            raise
        return backup


def previous_persona(root, role):
    if role not in ROLE_IDS:
        raise ValueError('未知角色')
    versions = sorted((Path(root) / 'data/persona_versions' / role).glob('*.json'), reverse=True)
    if not versions:
        raise ValueError('还没有保存过的人格版本')
    no_links(versions[0])
    record = json.loads(versions[0].read_text(encoding='utf-8'))
    if record['role'] != role or set(record['before']) != FILENAMES:
        raise ValueError('版本记录无效')
    return record['before']
