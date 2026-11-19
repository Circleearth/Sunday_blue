"""Apply scheduled Windows endpoint mute once per transition."""
from datetime import datetime

def synchronize(db, now=None, endpoint=None):
    now=now or datetime.now()
    working=now.weekday()<5 and 8<=now.hour<18
    key='work_audio_period'
    previous=db.get(key,None)
    if previous is working or (previous is None and not working):
        return
    if endpoint is None:
        from pycaw.pycaw import AudioUtilities
        device=AudioUtilities.GetSpeakers()
        if device is None:return
        endpoint=device.EndpointVolume
    if working:
        db.set('work_audio_owned',not bool(endpoint.GetMute()))
    endpoint.SetMute(int(working),None)
    if not working:db.set('work_audio_owned',False)
    db.set(key,working)


def release(db,endpoint=None):
    if not db.get('work_audio_owned',False):return
    if endpoint is None:
        from pycaw.pycaw import AudioUtilities
        device=AudioUtilities.GetSpeakers()
        if device is None:return
        endpoint=device.EndpointVolume
    endpoint.SetMute(0,None)
    db.set('work_audio_owned',False)
    db.set('work_audio_period',False)
