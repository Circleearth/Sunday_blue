"""Display-only segmentation, font loading and tool failure summaries."""
import json
import math
import random
from pathlib import Path
import regex
from PySide6.QtGui import QFont, QFontDatabase

DEFAULTS = {'font_family': 'Microsoft YaHei UI', 'font_file': '', 'font_size': 12,
            'font_weight': 500, 'segmented': True, 'threshold': 150,
            'pattern': r'.*?[。？！~…]+|.+$', 'interval': 'random',
            'random_min': 1.5, 'random_max': 3.5, 'log_base': 10.0}
_font_cache = {}

def options(value):
    return DEFAULTS | value

def validate(value):
    c=options(value)
    if not 1 <= c['threshold'] <= 10000: raise ValueError('分段阈值应在 1–10000 之间。')
    if c['interval'] not in ('random','log'): raise ValueError('间隔方式只支持 random / log。')
    if not 0 <= c['random_min'] <= c['random_max'] <= 60: raise ValueError('随机间隔应满足 0 ≤ 最小值 ≤ 最大值 ≤ 60。')
    if not math.isfinite(c['log_base']) or c['log_base'] <= 1: raise ValueError('log 底数必须大于 1。')
    if len(c['pattern']) > 1000: raise ValueError('正则表达式过长。')
    try:
        regex.compile(c['pattern'])
    except regex.error as exc: raise ValueError('分段正则无效：'+str(exc)) from None
    return c

def segments(text, value):
    c=options(value)
    if not text.strip(): return []
    if not c['segmented'] or len(text) >= c['threshold']: return [text]
    try:
        parts=[];cursor=0
        for m in regex.finditer(c['pattern'],text,flags=regex.DOTALL,timeout=.025):
            if m.end() <= cursor: continue
            # Retain unmatched text and delimiters, including when regex has groups.
            parts.append(text[cursor:m.end()]);cursor=m.end()
        if cursor<len(text):parts.append(text[cursor:])
        return [p for p in parts if p.strip()] or [text]
    except (regex.error, TimeoutError):
        return [text]

def delay(text,value):
    c=options(value)
    return random.uniform(c['random_min'],c['random_max']) if c['interval']=='random' else math.log(max(1,len(text)),c['log_base'])

def chat_font(root,value):
    c=options(value);family=c['font_family']
    if c['font_file']:
        base=(Path(root)/'assets'/'fonts').resolve()
        p=(Path(root)/c['font_file']).resolve()
        if p.is_relative_to(base) and p.is_file():
            key=(str(p),p.stat().st_mtime_ns)
            if key not in _font_cache:
                fid=QFontDatabase.addApplicationFontFromData(p.read_bytes())
                _font_cache[key]=QFontDatabase.applicationFontFamilies(fid) if fid>=0 else []
            if _font_cache[key]:family=_font_cache[key][0]
    f=QFont(family,c['font_size']);f.setWeight(QFont.Weight(c['font_weight']))
    f.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    return f

def tool_failure(block):
    if block.get('type')!='tool_result': return ''
    raw=block.get('content','')
    try: obj=json.loads(raw) if isinstance(raw,str) else raw
    except ValueError: obj={}
    failed=block.get('is_error') or (isinstance(obj,dict) and (obj.get('error') or obj.get('isError') or obj.get('status') in ('failed','error','denied','unconfigured')))
    if not failed:return ''
    detail=(obj.get('error') or obj.get('status') or '外部工具返回错误') if isinstance(obj,dict) else str(raw)
    return '工具调用失败：'+str(detail)[:500]
