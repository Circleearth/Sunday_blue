"""Shared schedules, immutable occurrences and idempotent check-ins."""
from datetime import datetime,timedelta,date
import uuid
from .database import stamp

class Planner:
    def __init__(self,db):
        self.db=db
        with db.connect() as conn:
            conn.executescript("""CREATE TABLE IF NOT EXISTS schedules (
                id TEXT PRIMARY KEY,title TEXT,next_due TEXT,repeat TEXT,local INTEGER,qq INTEGER,enabled INTEGER);
                CREATE TABLE IF NOT EXISTS reminder_occurrences (
                id TEXT PRIMARY KEY,schedule_id TEXT,due TEXT,title TEXT,local_status TEXT,qq_status TEXT,
                UNIQUE(schedule_id,due));
                CREATE TABLE IF NOT EXISTS checkins (id TEXT PRIMARY KEY,title TEXT,enabled INTEGER);
                CREATE TABLE IF NOT EXISTS checkin_history (checkin_id TEXT,day TEXT,created TEXT,PRIMARY KEY(checkin_id,day));""")
    def add(self,title,due,repeat='once',local=True,qq=False):
        title=str(title).strip();when=datetime.fromisoformat(due)
        if not title or len(title)>200 or repeat not in ('once','daily','weekly') or not(local or qq):raise ValueError('请填写标题、重复方式和提醒渠道')
        if when.tzinfo is None:when=when.astimezone()
        rid=uuid.uuid4().hex
        with self.db.connect() as db:db.execute('INSERT INTO schedules VALUES(?,?,?,?,?,?,1)',(rid,title,when.isoformat(),repeat,int(local),int(qq)))
        return rid
    def update(self,rid,title,due,repeat='once',local=True,qq=False):
        title=str(title).strip();when=datetime.fromisoformat(due)
        if not title or len(title)>200 or repeat not in ('once','daily','weekly') or not(local or qq):raise ValueError('请填写标题、重复方式和提醒渠道')
        if when.tzinfo is None:when=when.astimezone()
        with self.db.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT * FROM schedules WHERE id=?',(rid,)).fetchone()
            if not old:raise ValueError('提醒不存在')
            if db.execute('SELECT 1 FROM reminder_occurrences WHERE schedule_id=? AND due=?',(rid,when.isoformat())).fetchone():raise ValueError('这个时间的提醒已有投递记录，请选择新的提醒时间')
            db.execute('UPDATE schedules SET title=?,next_due=?,repeat=?,local=?,qq=? WHERE id=?',(title,when.isoformat(),repeat,int(local),int(qq),rid))
    def schedules(self):
        with self.db.connect() as db:return [dict(r) for r in db.execute('SELECT * FROM schedules ORDER BY next_due')]
    def legacy_qq(self):
        import sqlite3
        path=self.db.root/'data/plugins/qq-reminders/state.sqlite3'
        if not path.exists():return []
        conn=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True);conn.row_factory=sqlite3.Row
        try:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='rem'").fetchone():return []
            return [dict(r)|{'legacy':True,'title':r['text'],'next_due':r['next_fire'],'enabled':not r['done'],'local':False,'qq':True}
                for r in conn.execute('SELECT * FROM rem WHERE done=0 ORDER BY next_fire LIMIT 200')]
        finally:conn.close()

    def on_day(self,day):
        target=date.fromisoformat(day);result=[]
        for row in self.schedules():
            if not row['enabled']:continue
            first=datetime.fromisoformat(row['next_due']).date();gap=(target-first).days
            if gap>=0 and (gap==0 or row['repeat']=='daily' or row['repeat']=='weekly' and gap%7==0):result.append(row)
        return result

    def enable(self,rid,enabled):
        with self.db.connect() as db:db.execute('UPDATE schedules SET enabled=? WHERE id=?',(int(enabled),rid))
    def due(self,now=None):
        now=now or datetime.now().astimezone()
        with self.db.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            for row in db.execute('SELECT * FROM schedules WHERE enabled=1').fetchall():
                when=datetime.fromisoformat(row['next_due']);iterations=0
                while when<=now and iterations<366:
                    stale=now-when>timedelta(days=1)
                    db.execute('INSERT OR IGNORE INTO reminder_occurrences VALUES(?,?,?,?,?,?)',(uuid.uuid4().hex,row['id'],when.isoformat(),row['title'],
                        'missed' if stale else 'pending' if row['local'] else 'off','missed' if stale else 'pending' if row['qq'] else 'off'))
                    if row['repeat']=='once':db.execute('UPDATE schedules SET enabled=0 WHERE id=?',(row['id'],));break
                    when+=timedelta(days=1 if row['repeat']=='daily' else 7);iterations+=1
                    db.execute('UPDATE schedules SET next_due=? WHERE id=?',(when.isoformat(),row['id']))
            return [dict(r) for r in db.execute("SELECT * FROM reminder_occurrences WHERE local_status='pending' OR qq_status='pending' ORDER BY due LIMIT 20")]
    def mark(self,rid,channel,state):
        if channel not in ('local','qq') or state not in ('sent','pending','failed','sending'):raise ValueError('无效状态')
        with self.db.connect() as db:db.execute(f'UPDATE reminder_occurrences SET {channel}_status=? WHERE id=?',(state,rid))
    def history(self,day=None):
        with self.db.connect() as db:return [dict(r) for r in db.execute('SELECT * FROM reminder_occurrences WHERE (? IS NULL OR substr(due,1,10)=?) ORDER BY due DESC LIMIT 100',(day,day))]
    def add_checkin(self,title):
        title=title.strip()
        if not title or len(title)>100:raise ValueError('请填写打卡名称')
        with self.db.connect() as db:
            old=db.execute('SELECT id FROM checkins WHERE title=? AND enabled=1',(title,)).fetchone()
            if old:return old['id']
            rid=uuid.uuid4().hex;db.execute('INSERT INTO checkins VALUES(?,?,1)',(rid,title));return rid
    def checkins(self,day=None):
        day=day or date.today().isoformat()
        with self.db.connect() as db:return [dict(r) for r in db.execute('SELECT c.*,EXISTS(SELECT 1 FROM checkin_history h WHERE h.checkin_id=c.id AND h.day=?) AS done FROM checkins c WHERE enabled=1',(day,))]
    def check(self,rid,day=None):
        day=day or date.today().isoformat();date.fromisoformat(day)
        if day>date.today().isoformat():raise ValueError('不能提前确认未来打卡')
        with self.db.connect() as db:
            if not db.execute('SELECT 1 FROM checkins WHERE id=? AND enabled=1',(rid,)).fetchone():raise ValueError('打卡项目不存在')
            db.execute('INSERT OR IGNORE INTO checkin_history VALUES(?,?,?)',(rid,day,stamp()))
