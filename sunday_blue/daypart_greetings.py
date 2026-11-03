"""Local conversation greetings. Never writes model messages or prompt instructions."""
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import sqlite3
from .native_plugins import enabled

PERIODS = ((0,5,'凌晨','凌晨了，先把休息放在心上。'),
           (5,8,'清晨','清晨好，今天慢慢开始。'),
           (8,11,'早上','早上好，新的一天见到你啦。'),
           (11,14,'中午','中午好，忙到现在辛苦了。'),
           (14,17,'下午','下午好，我们接着聊。'),
           (17,19,'傍晚','傍晚好，今天过得怎么样？'),
           (19,22,'晚上','晚上好，欢迎回来。'),
           (22,24,'夜间','夜间了，把节奏放慢一点吧。'))
VOICES = {'rui':'我在，慢慢说。','red':'今天也按自己的节奏来。',
          'ewa':'先照顾好自己，再处理事情。','luna':'不用着急，我听着。',
          'loluns':'我们一点一点来。','kia':'想整理的事，可以交给我。',
          'mia':'有什么想找的，我陪你理一理。',
          'ticktick':'需要整理任务时可以告诉我。','mubu':'需要整理思路时可以告诉我。'}
SLEEP = ('凌晨还在聊呀，给自己留点睡眠时间，聊完这一件就休息吧。',
         '又陪你说了一会儿。事情可以明天继续，先去睡一觉，好吗？',
         '凌晨的时间慢慢过去了，我再提醒一次：别忘了休息，醒来再继续也来得及。')

def period_at(moment):
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError('Local greeting time must include a timezone')
    return next(p for p in PERIODS if p[0] <= moment.hour < p[1])

class Greetings:
    def __init__(self,data):
        self.path=Path(data)/'plugins'/'daypart-greetings'/'state.sqlite3'

    @contextmanager
    def connection(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        db=sqlite3.connect(self.path,timeout=10)
        try:
            db.executescript('''CREATE TABLE IF NOT EXISTS seen (
                role TEXT, day TEXT, period TEXT, last REAL, count INTEGER,
                PRIMARY KEY(role,day,period));
                CREATE TABLE IF NOT EXISTS events (
                session TEXT, message INTEGER, text TEXT, created TEXT,
                PRIMARY KEY(session,message));''')
            with db:yield db
        finally:db.close()

    def on_message(self,config,role,sid,message_id,moment=None):
        if not enabled(config,role,'daypart-greetings'):return None
        current=moment or datetime.now().astimezone()
        _,_,period,greeting=period_at(current)
        day=current.date().isoformat();ts=current.timestamp()
        cfg=config.get('greetings',{})
        cooldown=max(0,int(cfg.get('night_interval_minutes',0)))*60
        repeat=cfg.get('night_repeat',True)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            existing=db.execute('SELECT text FROM events WHERE session=? AND message=?',(sid,message_id)).fetchone()
            if existing:return existing[0]
            seen=db.execute('SELECT last,count FROM seen WHERE role=? AND day=? AND period=?',(role,day,period)).fetchone()
            if seen and (period!='凌晨' or not repeat or ts-seen[0]<cooldown):return None
            count=seen[1] if seen else 0
            text=(SLEEP[count%len(SLEEP)] if period=='凌晨' else greeting)+' '+VOICES.get(role,'我在这里。')
            db.execute('INSERT INTO seen VALUES(?,?,?,?,?) ON CONFLICT(role,day,period) DO UPDATE SET last=excluded.last,count=excluded.count',
                       (role,day,period,ts,count+1))
            db.execute('INSERT INTO events VALUES(?,?,?,?)',(sid,message_id,text,current.isoformat()))
        return text

    def for_session(self,sid):
        if not self.path.exists():return {}
        with self.connection() as db:
            return dict(db.execute('SELECT message,text FROM events WHERE session=?',(sid,)))
