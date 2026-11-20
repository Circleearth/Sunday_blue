from datetime import date
BASE=[('06:30–06:40','起床、洗漱、喝水'),('06:40–08:00','CPA学习80分钟'),('08:00–08:20','早餐、整理、出门'),('12:40–13:30','午饭、午休'),('13:30–13:50','复现知识点20分钟'),('19:00–20:00','晚饭、洗澡、家务'),('22:00–22:30','放松、准备睡觉'),('22:30–次日06:30','睡眠窗口')]
EVENINGS=[ [('18:10–19:00','力量A：胸、背、核心'),('20:00–21:30','CPA专项练习'),('21:30–22:00','自由娱乐')], [('18:10–19:00','快走或轻有氧30分钟'),('20:00–22:00','副业：只推进一个可展示或销售的成果')], [('18:10–19:00','力量B：背、肩、核心'),('20:00–21:30','CPA学习'),('21:30–22:00','吉他或轻松娱乐')], [('18:10–19:00','有氧40分钟或羽毛球'),('20:00–21:30','CPA学习'),('21:30–22:00','娱乐与恢复')], [('18:10–19:00','力量C：胸、背、手臂、腿'),('20:00–20:30','职业发展、收入检查'),('20:30–22:00','摄影、技术、项目或娱乐')]]
def default_rows(slot, weekday):
    if slot==7:
        return [('午休空余','学习20分钟'),('18:10–20:00','机动时间'),('20:00–23:00','游戏或活动'),('23:00以后','洗漱、安静入睡')]
    if slot==8:
        return sorted([('07:20–08:00','学习40分钟'),('08:00–08:20','早餐、准备出门')]+[(t,v) for t,v in BASE if t>='12:00']+(EVENINGS[weekday] if weekday<5 else []))
    return sorted(BASE+EVENINGS[slot]) if slot<5 else []

def plan(db,day):
    target=date.fromisoformat(day)
    return default_rows(template_slot(db,target),target.weekday())

def template_slot(db, day):
    return {'late':7, 'after':8}.get(db.get('day_plan:'+day.isoformat(),'normal'),day.weekday())

def time_range(value):
    import re
    import unicodedata
    text=unicodedata.normalize('NFKC', value).strip()
    text=re.sub(r'(\d{1,2})\s*[点时]\s*(?:(\d{1,2})分?)?',lambda m:f"{m[1]}:{int(m[2] or 0):02}",text)
    clock=r'([01]?\d|2[0-3])\s*:\s*([0-5]\d)'
    match=re.fullmatch(clock+r'\s*(?:[-–—~至到]\s*(?:次日\s*)?([012]?\d)\s*:\s*([0-5]\d)|(以后|之后))',text)
    if match:
        h,m,eh,em,later=match.groups()
        if not later and (int(eh)>24 or (int(eh)==24 and int(em)!=0)):return None
        return int(h)*60+int(m), 1440 if later else int(eh)*60+int(em)
    return None

def active_plan(db, now):
    from datetime import timedelta
    for offset in (0,1):
        day=now.date()-timedelta(days=offset)
        slot=template_slot(db,day)
        raw=db.get('weekly_plan:'+str(slot),None)
        rows=plan(db,day.isoformat()) if raw is None else [line.split(' · ',1) for line in raw.splitlines()]
        minute=offset*1440+now.hour*60+now.minute
        for index,row in enumerate(rows):
            if len(row)!=2 or not row[1].strip():continue
            interval=time_range(row[0])
            if interval:
                start,end=interval
                if start<=minute<(end if end>start else end+1440):
                    return slot,index,row[1],day
    return template_slot(db,now.date()),None,'自由安排',now.date()

def current_plan(db,now):
    return active_plan(db,now)[2]
