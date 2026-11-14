"""Game recovery score, not a medical sleep assessment."""
from datetime import datetime

def score_sleep(bed,wake):
    if not bed or not wake:raise ValueError('请填写入睡和起床时间')
    def minute(value):
        t=datetime.strptime(value,'%H:%M');return t.hour*60+t.minute
    b,w=minute(bed),minute(wake);hours=((w-b)%1440)/60
    if hours==0:raise ValueError('入睡与起床时间不能相同')
    def schedule(value,lo,hi):
        if lo<=value<=hi:return 1.0
        gap=min(min(abs(value-x),1440-abs(value-x)) for x in (lo,hi))
        return max(0,1-gap/240)
    duration=min(1,hours/8) if hours<=9 else max(0,1-(hours-9)/6)
    bs,ws=schedule(b,1350,1410),schedule(w,390,540)
    return dict(quality=round(.5*duration+.3*bs+.2*ws,4),bed=bs,wake=ws,duration=duration,hours=hours)
