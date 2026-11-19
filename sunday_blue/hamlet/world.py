"""Persistent village economy. Work points are read-only income from the work ledger."""
import json
import time

class Village:
    def __init__(self, db, clock=time.time):
        self.db = db
        self.clock = clock

    def _load(self, conn):
        row = conn.execute("SELECT value FROM module_settings WHERE key='hamlet.v1'").fetchone()
        state = json.loads(row[0]) if row else dict(spent=0, coins=0, wheat=0, ore=0, weapon=0,
            xp=0, floor=1, relic=0, bond=0, plots=[0,0,0], enemies=0)
        earned = conn.execute('SELECT COALESCE(SUM(amount),0) FROM work_points').fetchone()[0]
        return state, earned

    @staticmethod
    def damage(s):
        return (1 + s['weapon'] + s['xp']//8 + s['bond']//3) * (1 + s['relic'])

    def view(self):
        with self.db.connect() as c:
            s, earned = self._load(c)
        return s | {'balance': earned - s['spent'] + s['coins'], 'damage': self.damage(s)}

    def act(self, action, plot=0):
        with self.db.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            s, earned = self._load(c)
            if action == 'field':
                if not 0 <= plot < len(s['plots']): raise ValueError('田地不存在')
                ready = s['plots'][plot]
                if ready and ready > self.clock(): raise ValueError('麦穗还在生长。')
                if ready:
                    s['plots'][plot] = 0
                    s['wheat'] += 2
                    s['xp'] += 1
                    message = '收获麦穗 ×2，可用来喂养伙伴。'
                else:
                    if earned + s['coins'] <= s['spent']: raise ValueError('播种需要 1 工作积分。')
                    s['spent'] += 1
                    s['plots'][plot] = self.clock() + 60
                    message = '播下雾麦，一分钟后成熟。'
            elif action == 'forge':
                if s['ore'] < 2: raise ValueError('锻造需要两枚矿石。')
                s['ore'] -= 2
                s['weapon'] += 1
                message = '锻造完成，木桩可检验新伤害。'
            elif action == 'feed':
                if not s['enemies'] or not s['wheat']: raise ValueError('先探索遗迹结识苔灵，再带一束麦穗来。')
                s['wheat'] -= 1
                s['bond'] += 1
                message = '苔灵蹭蹭你的手。每三点羁绊增加一点基础伤害。'
            elif action == 'dungeon':
                damage = self.damage(s)
                won = damage >= s['floor']
                s['ore'] += 1
                s['xp'] += 1
                if won:
                    s['enemies'] += 1
                    s['coins'] += 1
                    s['floor'] += 1
                    if s['floor'] % 4 == 0: s['relic'] += 1
                message = '探索成功，找到矿石、村币与苔灵。' if won else '暂时撤退，带回一枚矿石。可在铁匠铺强化。'
            elif action == 'dummy':
                return f"木桩承受 {self.damage(s)} 点伤害。"
            else:
                raise ValueError('未知操作')
            c.execute("INSERT OR REPLACE INTO module_settings VALUES('hamlet.v1',?)", (json.dumps(s),))
            return message
