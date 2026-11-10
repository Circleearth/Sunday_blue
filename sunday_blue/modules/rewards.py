"""Transactional virtual coins and separately confirmed real-world budget."""
import uuid
from .database import stamp
from ..roles import require_role


class Rewards:
    def __init__(self, database):
        self.db=database
        with self.db.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS coin_ledger (
                id TEXT PRIMARY KEY, amount INTEGER NOT NULL, reason TEXT, created TEXT);
                CREATE TABLE IF NOT EXISTS real_budget (
                id TEXT PRIMARY KEY, cents INTEGER NOT NULL, note TEXT, created TEXT);
                CREATE TABLE IF NOT EXISTS rewards (
                id TEXT PRIMARY KEY,title TEXT,cost INTEGER,kind TEXT,minutes INTEGER,cents INTEGER,role_id TEXT);
                CREATE TABLE IF NOT EXISTS redemptions (
                id TEXT PRIMARY KEY,request_id TEXT UNIQUE,reward_id TEXT,title TEXT,cost INTEGER,
                kind TEXT,status TEXT,role_id TEXT,cents INTEGER,created TEXT);''')
            for r in [('rest20','娱乐 20 分钟',20,'leisure',20,0,None),('hobby30','兴趣时间 30 分钟',30,'leisure',30,0,None)]:
                db.execute('INSERT OR IGNORE INTO rewards VALUES(?,?,?,?,?,?,?)',r)

    def list(self):
        with self.db.connect() as db: return [dict(r) for r in db.execute('SELECT * FROM rewards ORDER BY cost,title')]

    def add(self,title,cost,kind='leisure',minutes=0,cents=0,role_id=None):
        title=str(title).strip();cost=int(cost);minutes=int(minutes);cents=int(cents)
        if not title or len(title)>100 or not 1<=cost<=100000 or kind not in ('leisure','budget','gift'):
            raise ValueError('请填写奖励名称、正整数金币和有效奖励类别。')
        if minutes<0 or cents<0: raise ValueError('时长和金额不能为负。')
        if kind=='budget' and cents<=0: raise ValueError('预算奖励必须填写实际金额。')
        if kind=='gift': require_role(self.db.root,role_id)
        rid=uuid.uuid4().hex
        with self.db.connect() as db: db.execute('INSERT INTO rewards VALUES(?,?,?,?,?,?,?)',(rid,title,cost,kind,minutes,cents,role_id))
        return rid

    @staticmethod
    def balance(db):
        return db.execute('SELECT COALESCE(sum(amount),0) FROM coin_ledger').fetchone()[0]

    def balances(self):
        with self.db.connect() as db:
            return {'coins':self.balance(db),'budget_cents':db.execute('SELECT COALESCE(sum(cents),0) FROM real_budget').fetchone()[0]}

    def redeem(self,reward_id,request_id):
        if not request_id or len(request_id)>100: raise ValueError('无效兑换编号')
        with self.db.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            previous=db.execute('SELECT * FROM redemptions WHERE request_id=?',(request_id,)).fetchone()
            if previous:return dict(previous)
            reward=db.execute('SELECT * FROM rewards WHERE id=?',(reward_id,)).fetchone()
            if not reward: raise ValueError('奖励不存在')
            if reward['kind']=='gift':require_role(self.db.root,reward['role_id'])
            if self.balance(db)<reward['cost']:raise ValueError('金币不足；休息不需要兑换，也不会扣关系。')
            rid=uuid.uuid4().hex
            db.execute('INSERT INTO coin_ledger VALUES(?,?,?,?)',(rid,-reward['cost'],'redeem:'+reward_id,stamp()))
            db.execute('INSERT INTO redemptions VALUES(?,?,?,?,?,?,?,?,?,?)',(rid,request_id,reward_id,reward['title'],reward['cost'],
                reward['kind'],'pending' if reward['kind']=='budget' else 'redeemed',reward['role_id'],reward['cents'],stamp()))
            result=dict(db.execute('SELECT * FROM redemptions WHERE id=?',(rid,)).fetchone())
            self.db.emit(db,'redeem:'+rid,'rewards.redeemed',result)
            return result

    def confirm_budget(self,redemption_id):
        # Called only by the explicit human confirmation UI, never an AI tool.
        with self.db.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM redemptions WHERE id=?',(redemption_id,)).fetchone()
            if not row or row['kind']!='budget':raise ValueError('不是预算兑换记录')
            if row['status']=='confirmed':return dict(row)
            available=db.execute('SELECT COALESCE(sum(cents),0) FROM real_budget').fetchone()[0]
            if available<row['cents']:raise ValueError('实际预算不足；请先核对或调整预算。金币与真实钱不互相换算。')
            db.execute('INSERT OR IGNORE INTO real_budget VALUES(?,?,?,?)',('redeem:'+redemption_id,-row['cents'],row['title'],stamp()))
            db.execute("UPDATE redemptions SET status='confirmed' WHERE id=?",(redemption_id,))
            return dict(db.execute('SELECT * FROM redemptions WHERE id=?',(redemption_id,)).fetchone())

    def adjust_budget(self,cents,note,request_id):
        cents=int(cents)
        if not note.strip() or not request_id:raise ValueError('请填写预算调整原因。')
        with self.db.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM real_budget WHERE id=?',(request_id,)).fetchone():return
            balance=db.execute('SELECT COALESCE(sum(cents),0) FROM real_budget').fetchone()[0]
            if balance+cents<0:raise ValueError('预算余额不能为负。')
            db.execute('INSERT INTO real_budget VALUES(?,?,?,?)',(request_id,cents,note[:200],stamp()))

    def history(self):
        with self.db.connect() as db: return [dict(r) for r in db.execute('SELECT * FROM redemptions ORDER BY created DESC,rowid DESC LIMIT 30')]
