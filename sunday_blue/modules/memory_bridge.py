"""Recent private/group continuity. Context remains owned by the speaking role."""
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import time
from ..storage import plain
from ..roles import require_role


def private_support(root,role,config,query):
    require_role(root,role)
    root=Path(root);parts=[];count=0
    path=root/'data/conversations.sqlite3'
    if path.exists():
        db=sqlite3.connect(path);db.row_factory=sqlite3.Row
        try:
            rows=db.execute('''SELECT m.role,m.content,m.created FROM messages m JOIN sessions s ON s.id=m.session
                WHERE s.role=? ORDER BY m.id DESC LIMIT 30''',(role,)).fetchall()
        finally:db.close()
        recent=[];used=0
        for row in rows:
            if time.time()-datetime.fromisoformat(row['created']).timestamp()>86400:continue
            content=json.loads(row['content'])
            if row['role']=='user' and not isinstance(content,str):continue
            text=plain(content).strip()
            if not text:continue
            text=text[:450]
            if used+len(text)>1800:break
            recent.append(('用户' if row['role']=='user' else '你')+'：'+text);used+=len(text);count+=1
            if count>=6:break
        if recent:parts.append('你与用户最近的私聊（仅属于你，用来理解近况，不逐字公开）：\n'+'\n'.join(reversed(recent)))
    confirmed=root/'data/memory'/role/'long_term.md'
    if confirmed.is_file():parts.append('你自己的已确认偏好与记忆：\n'+confirmed.read_text(encoding='utf-8')[:1400])
    from ..native_plugins import enabled
    status=f'最近私聊 {count} 条'
    if enabled(config,role,'livingmemory'):
        try:
            from ..plugin_runtime import load
            recalled=load('livingmemory',root).before_turn(root,config,role,'group-context',{'content':query[:2500]})
            if recalled:parts.append(recalled[:2200])
            status+=' · 长期记忆已检索'
        except Exception:
            status+=' · 长期记忆离线，仍保留近期衔接'
    return '\n\n'.join(parts),status
