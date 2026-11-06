"""Offline upstream change inventory. Never replaces code or touches user data.

--record is only for maintainers after reviewing a new pinned snapshot.
--candidate points at an independently downloaded LivingMemory source checkout.
The report separates backend changes from UI/assets for future upgrades.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT/'extensions/plugins/livingmemory'


def hashes(path):
    return {str(p.relative_to(path)).replace('\\','/'): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(path.rglob('*')) if p.is_file()
            and not any(part in {'.git','__pycache__','node_modules'} for part in p.parts)
            and p.suffix != '.pyc'}


def differences(before, after):
    result = {'backend': [], 'ui': [], 'metadata': []}
    for name in sorted(set(before) | set(after)):
        if before.get(name) == after.get(name):
            continue
        kind = 'ui' if name.startswith(('pages/','static/')) else (
            'backend' if name.startswith(('core/','storage/')) or name in {'requirements.txt','main.py'} else 'metadata')
        result[kind].append({'path':name,'change': 'added' if name not in before else 'removed' if name not in after else 'changed'})
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--record', action='store_true')
    parser.add_argument('--candidate', type=Path)
    args = parser.parse_args()
    path = PLUGIN/'upstream-lock.json'
    if args.record:
        manifest = {
            'livingmemory': {'version':'2.9.1', 'commit':'1c6a471c9af9ae45a4ccb3a8cec5695c917de50b',
                'repository':'https://github.com/lxfight-s-Astrbot-Plugins/astrbot_plugin_livingmemory',
                'files':hashes(PLUGIN/'vendor/livingmemory')},
            'astrbot': {'repository':'https://github.com/AstrBotDevs/AstrBot',
                'source':'Local installed AstrBot vector database snapshot, 2026-11-06; no user configuration or data',
                'files':hashes(PLUGIN/'vendor/astrbot')}}
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        print('Recorded reviewed upstream snapshot.')
        return
    manifest = json.loads(path.read_text(encoding='utf-8'))
    if args.candidate:
        before = manifest['livingmemory']['files']
        after = hashes(args.candidate)
        # Only compare the components intentionally included in our snapshot.
        prefixes = ('core/','storage/','pages/','static/','.astrbot-plugin/')
        after = {k:v for k,v in after.items() if k in before or k.startswith(prefixes)}
        print(json.dumps(differences(before, after), ensure_ascii=False, indent=2))
    else:
        changes = {name:differences(info['files'],hashes(PLUGIN/'vendor'/name))
                   for name,info in manifest.items()}
        print(json.dumps(changes, ensure_ascii=False, indent=2))
        if any(items for value in changes.values() for items in value.values()):
            raise SystemExit(1)


if __name__ == '__main__':
    main()
