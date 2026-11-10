"""Monthly real-reward allowance, reserved atomically with redemption."""
import calendar
from datetime import date,timedelta
from .database import stamp


def month_after(value):
    y,m=map(int,value.split('-'));return f'{y+int(m==12):04d}-{m%12+1:02d}'


class Allowance:
    def __init__(self,database,today=date.today):
        self.db,self.today=database,today
        with self.db.connect() as db:
            db.executescript("""CREATE TABLE IF NOT EXISTS allowance_policy (
                effective TEXT PRIMARY KEY,cents INTEGER,hours REAL,ratio REAL,changed_month TEXT);
                CREATE TABLE IF NOT EXISTS allowance_months (month TEXT PRIMARY KEY,grant_cents INTEGER);
                CREATE TABLE IF NOT EXISTS allowance_usage (redemption TEXT PRIMARY KEY,month TEXT,cents INTEGER);""")
            if not db.execute('SELECT 1 FROM allowance_policy').fetchone():
                db.execute('INSERT INTO allowance_policy VALUES(?,?,?,?,?)',(self.today().strftime('%Y-%m'),10000,50,.85,''))
    def _roll(self,db):
        current=self.today().strftime('%Y-%m')
        first=db.execute('SELECT min(effective) FROM allowance_policy').fetchone()[0]
        latest=db.execute('SELECT max(month) FROM allowance_months').fetchone()[0]
        cursor=month_after(latest) if latest else first
        while cursor<=current:
            policy=db.execute('SELECT * FROM allowance_policy WHERE effective<=? ORDER BY effective DESC LIMIT 1',(cursor,)).fetchone()
            db.execute('INSERT OR IGNORE INTO allowance_months VALUES(?,?)',(cursor,policy['cents']))
            cursor=month_after(cursor)
    def available(self,db):
        self._roll(db)
        return db.execute('SELECT COALESCE(sum(grant_cents),0) FROM allowance_months').fetchone()[0]-db.execute('SELECT COALESCE(sum(cents),0) FROM allowance_usage').fetchone()[0]
    def reserve(self,db,rid,cents):
        if self.available(db)<cents:raise ValueError('现实奖励月度额度不足（包含结转）；不影响金币余额。')
        db.execute('INSERT INTO allowance_usage VALUES(?,?,?)',(rid,self.today().strftime('%Y-%m'),cents))
    def status(self):
        current=self.today().strftime('%Y-%m');last=self.today().replace(day=1)-timedelta(days=1)
        with self.db.connect() as db:
            db.execute('BEGIN IMMEDIATE');available=self.available(db)
            policy=dict(db.execute('SELECT * FROM allowance_policy WHERE effective<=? ORDER BY effective DESC LIMIT 1',(current,)).fetchone())
            rows=[]
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='activity_records'").fetchone():
                rows=db.execute('SELECT day,seconds FROM activity_records WHERE day LIKE ?',(last.strftime('%Y-%m')+'%',)).fetchall()
            hours=sum(r['seconds'] for r in rows)/3600;days=len({r['day'] for r in rows});total=calendar.monthrange(last.year,last.month)[1]
            changed=bool(db.execute('SELECT 1 FROM allowance_policy WHERE changed_month=?',(current,)).fetchone())
            scheduled=db.execute('SELECT cents FROM allowance_policy WHERE effective=?',(month_after(current),)).fetchone()
            return policy|{'available_cents':available,'last_hours':hours,'last_days':days,'last_total':total,
                'can_change':hours>=policy['hours'] and days/total>policy['ratio'] and not changed,
                'changed':changed,'next_cents':scheduled['cents'] if scheduled else policy['cents']}
    def change(self,cents,hours=50,ratio=.85):
        if not 0<int(cents)<=10000000 or not 0<float(hours)<=744 or not .85<=float(ratio)<1:raise ValueError('额度或条件无效；活跃比例不能低于 85%。')
        # Serialize eligibility check and policy write, including monthly change limit.
        current=self.today().strftime('%Y-%m')
        status=self.status()
        if not status['can_change']:raise ValueError('需满足上月时长、活跃比例且当月未修改过。')
        with self.db.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM allowance_policy WHERE changed_month=?',(current,)).fetchone():raise ValueError('本月已修改过')
            db.execute('INSERT INTO allowance_policy VALUES(?,?,?,?,?)',(month_after(current),int(cents),float(hours),float(ratio),current))
