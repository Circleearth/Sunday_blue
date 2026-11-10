"""Separate durable affinity, decaying mood and an auditable relationship history."""
import json
import time
import uuid
from .database import day,stamp
from ..roles import list_roles,require_role


class Relations:
    def __init__(self,database):
        self.db=database
        with self.db.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS relationships (
                role_id TEXT PRIMARY KEY,affinity REAL,mood REAL,mood_at REAL,last_event TEXT);
                CREATE TABLE IF NOT EXISTS relationship_history (
                event_key TEXT,role_id TEXT,day TEXT,affinity_delta REAL,mood_delta REAL,note TEXT,
                PRIMARY KEY(event_key,role_id));''')

    @staticmethod
    def _mood(row,now):
        return row['mood']*(0.5**(max(0,now-row['mood_at'])/10800)) if row else 0

    def project(self):
        active={r[0] for r in list_roles(self.db.root)}
        for event in self.db.events('relations'):
            body=event['payload'];role=body.get('role_id')
            with self.db.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                if db.execute("SELECT 1 FROM module_receipts WHERE consumer='relations' AND event_key=?",(event['event_key'],)).fetchone():continue
                delta,mood=0,0
                if event['kind']=='focus.completed':delta,mood=1,8
                elif event['kind']=='rewards.redeemed' and body.get('kind')=='gift':delta,mood=1,5
                elif event['kind']=='activity.setback':delta,mood=-1,-6
                if role in active and (delta or mood):
                    row=db.execute('SELECT * FROM relationships WHERE role_id=?',(role,)).fetchone()
                    current=time.time();affinity=row['affinity'] if row else 50
                    history=db.execute('SELECT affinity_delta FROM relationship_history WHERE role_id=? AND day=?',(role,day())).fetchall()
                    positive=sum(max(0,r[0]) for r in history);negative=sum(min(0,r[0]) for r in history)
                    delta=min(delta,max(0,6-positive)) if delta>0 else max(delta,min(0,-1-negative))
                    # No records/absence event exists. Negative input is explicitly user-reported,
                    # one point per day maximum, never lowers affinity below 30.
                    value=max(30,min(100,affinity+delta));actual=value-affinity
                    mood_value=max(-15,min(30,self._mood(row,current)+(mood if actual else 0)))
                    note={'focus.completed':'一起见证了专注完成','rewards.redeemed':'收到了心意','activity.setback':'承认一次未达成，并给下一次留余地'}[event['kind']]
                    db.execute('INSERT INTO relationships VALUES(?,?,?,?,?) ON CONFLICT(role_id) DO UPDATE SET affinity=excluded.affinity,mood=excluded.mood,mood_at=excluded.mood_at,last_event=excluded.last_event',
                               (role,value,mood_value,current,note))
                    db.execute('INSERT OR IGNORE INTO relationship_history VALUES(?,?,?,?,?,?)',(event['event_key'],role,day(),actual,mood,note))
                self.db.receipt(db,'relations',event['event_key'])

    def list(self):
        self.project();result=[]
        with self.db.connect() as db:
            for rid,name,*_ in list_roles(self.db.root):
                row=db.execute('SELECT * FROM relationships WHERE role_id=?',(rid,)).fetchone();mood=self._mood(row,time.time())
                result.append(dict(role_id=rid,name=name,affinity=row['affinity'] if row else 50,mood=round(mood,1),
                    mood_label='轻快' if mood>4 else '有点低落，正在恢复' if mood<-3 else '平静',last_event=row['last_event'] if row else '慢慢熟悉，不急着证明什么'))
        return result

    def report_setback(self,role_id,note):
        require_role(self.db.root,role_id)
        if not str(note).strip():raise ValueError('请写下实际发生的情况，不根据缺少记录推断失败。')
        with self.db.connect() as db:
            self.db.emit(db,'setback:'+role_id+':'+day(),'activity.setback',{'role_id':role_id,'note':str(note)[:500]})
        self.project()

    def context(self,role):
        value=next((r for r in self.list() if r['role_id']==role),None)
        if not value:return ''
        return ('当前关系状态：'+value['mood_label']+'；最近共同经历：'+value['last_event']+
                '。用人格自然表达，不报分数，不要求送礼；休息与缺少记录不代表偷懒。')
