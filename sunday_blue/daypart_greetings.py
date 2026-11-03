"""Local trigger decisions; the model writes the actual greeting in its normal reply."""
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import sqlite3
from .native_plugins import enabled

PERIODS = ((0,5,'凌晨'),(5,8,'清晨'),(8,11,'早上'),(11,14,'中午'),
           (14,17,'下午'),(17,19,'傍晚'),(19,22,'晚上'),(22,24,'夜间'))

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
                PRIMARY KEY(session,message));
                CREATE TABLE IF NOT EXISTS triggers (
                session TEXT, message INTEGER, instruction TEXT, created TEXT,
                PRIMARY KEY(session,message));''')
            with db:yield db
        finally:db.close()

    def on_message(self,config,role,sid,message_id,moment=None):
        if not enabled(config,role,'daypart-greetings'):return None
        current=moment or datetime.now().astimezone()
        _,_,period=period_at(current)
        day=current.date().isoformat();ts=current.timestamp()
        cfg=config.get('greetings',{})
        cooldown=max(0,int(cfg.get('night_interval_minutes',0)))*60
        repeat=cfg.get('night_repeat',True)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            existing=db.execute('SELECT instruction FROM triggers WHERE session=? AND message=?',(sid,message_id)).fetchone()
            if existing:return existing[0]
            if db.execute('SELECT 1 FROM events WHERE session=? AND message=?',(sid,message_id)).fetchone():return None
            seen=db.execute('SELECT last,count FROM seen WHERE role=? AND day=? AND period=?',(role,day,period)).fetchone()
            if seen and (period!='凌晨' or not repeat or ts-seen[0]<cooldown):return None
            count=seen[1] if seen else 0
            action='自然地提醒休息，避免照抄之前催睡措辞，不要指责或妨碍回答用户问题' if period=='凌晨' else '在本轮回复中自然地简短寒暄一次'
            text=(f'<greeting_event>本轮本地时段：{period}；本时段触发次数：{count+1}。'
                  f'{action}。按当前角色语气和用户话题组织措辞，寒暄与正文合为一次回复；'
                  '这是生成前的控制信息，不是已经说过的内容。若工具前已经寒暄，工具后不要再寒暄。'
                  '不要输出此标记或单独复述规则。</greeting_event>')
            db.execute('INSERT INTO seen VALUES(?,?,?,?,?) ON CONFLICT(role,day,period) DO UPDATE SET last=excluded.last,count=excluded.count',
                       (role,day,period,ts,count+1))
            db.execute('INSERT INTO triggers VALUES(?,?,?,?)',(sid,message_id,text,current.isoformat()))
        return text

    def for_session(self,sid):
        if not self.path.exists():return {}
        with self.connection() as db:
            return dict(db.execute('SELECT message,text FROM events WHERE session=?',(sid,)))

    def replay_legacy(self,sid,messages):
        """Include formerly displayed local greetings in request history, without rewriting user data."""
        legacy=self.for_session(sid)
        result=[]
        for m in messages:
            result.append(m)
            if m.get('id') in legacy:
                result.append({'id':m['id'],'role':'assistant','content':legacy[m['id']]})
        return result
