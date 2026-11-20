"""Authoritative village state. Every exchange, command and due reward is atomic."""
import json
import random
import time
import uuid
from pathlib import Path

from ..modules.database import stamp


class Village:
    def __init__(self, db, clock=time.time, catalog=None):
        self.db, self.clock = db, clock
        source = catalog or Path(__file__).resolve().parents[2]/'assets/hamlet/game/catalog.json'
        self.catalog = json.loads(Path(source).read_text('utf8'))
        with db.connect() as c:
            c.execute('CREATE TABLE IF NOT EXISTS hamlet_receipts(id TEXT PRIMARY KEY,command TEXT,message TEXT)')
            c.execute('CREATE TABLE IF NOT EXISTS hamlet_ledger(id INTEGER PRIMARY KEY,world REAL,amount INTEGER,reason TEXT,source TEXT)')

    def _focus(self, c):
        row = c.execute("""SELECT COALESCE(SUM(r.elapsed),0),COALESCE(MAX(r.state='running'),0)
            FROM focus_runs r LEFT JOIN focus_timers t ON t.run_id=r.id
            WHERE COALESCE(t.phase,'focus')='focus'""").fetchone()
        return row[0], bool(row[1])

    def _state(self, c, wall, focus):
        row = c.execute("SELECT value FROM module_settings WHERE key='hamlet.v2'").fetchone()
        if row:
            return json.loads(row[0])
        legacy = c.execute("SELECT value FROM module_settings WHERE key='hamlet.v1'").fetchone()
        old = json.loads(legacy[0]) if legacy else {}
        bag = {k:old.get(k,0) for k in self.catalog['items']}
        # Legacy crops keep their accrued growth in the new inventory.
        bag['wheat'] += 2*sum(bool(p) for p in old.get('plots',[]))
        spent, coins = old.get('spent',0), old.get('coins',0)
        earned = self._balance(c,'work')
        debit = min(spent,max(0,earned))
        if debit:
            c.execute('INSERT INTO work_points VALUES(?,?,?,?)',('hamlet:v1',-debit,'旧谷地已使用积分',stamp()))
        s = dict(ready=[],barn=1,mastery={k:0 for k in self.catalog['classes']},wall=wall, focus=focus, world=0, cash=0, inventory=bag, plots=3, jobs=[],
                 xp=old.get('xp',0),floor=old.get('floor',1),bond=old.get('bond',0),
                 relic=old.get('relic',0),companions=old.get('enemies',0),gear=[],equipped='',
                 team=['swift'],auto=0,filter='all',log=[])
        if old.get('weapon',0):
            s['gear']=[dict(id='heritage',name='旧谷铁剑',power=old['weapon'],rare=False)]
            s['equipped']='heritage'
        self._money(c,s,24+max(0,coins-(spent-debit)),'迁居补给','hamlet:v1')
        self._save(c,s)
        return s

    @staticmethod
    def _balance(c, source):
        table={'coin':'coin_ledger','work':'work_points'}[source]
        return c.execute('SELECT COALESCE(sum(amount),0) FROM '+table).fetchone()[0]

    @staticmethod
    def _save(c,s):
        c.execute("INSERT OR REPLACE INTO module_settings VALUES('hamlet.v2',?)",(json.dumps(s,ensure_ascii=False),))

    @staticmethod
    def _money(c,s,amount,reason,source=''):
        if s['cash']+amount<0:
            raise ValueError('谷币不足，可去集市兑换或交付货物。')
        s['cash']+=amount
        c.execute('INSERT INTO hamlet_ledger(world,amount,reason,source) VALUES(?,?,?,?)',(s['world'],amount,reason,source))

    @staticmethod
    def _note(s,message):
        s['log']=(s['log']+[message])[-25:]
        return message

    def _schedule(self,c,s,key,when,plot=None):
        recipe=self.catalog['activities'][key]
        site=recipe['site']
        active=[j for j in s['jobs'] if self.catalog['activities'][j['key']]['site']==site]
        limit=s['plots'] if site=='farm' else s['barn'] if key=='pasture' else 1
        if site=='farm':active=active+s['ready']
        if key=='barn' and (s['barn']>=4 or any(j['key']=='barn' for j in active)):
            raise ValueError('羊舍已满级或正在扩建。')
        if len(active)>=limit:raise ValueError('这里正在作业，请等当前批次结束。')
        if key=='expand' and s['plots']>=8:raise ValueError('农田已全部开垦。')
        bag=s['inventory']
        if any(bag[k]<n for k,n in recipe['inputs'].items()):raise ValueError('所需材料不足，请查看配方。')
        self._money(c,s,-recipe['cost'],recipe['name'])
        for k,n in recipe['inputs'].items():bag[k]-=n
        job=dict(id=uuid.uuid4().hex,key=key,start=when,end=when+60*recipe['minutes'])
        if site=='farm':
            occupied={j['plot'] for j in active}
            if plot is None:plot=next(i for i in range(s['plots']) if i not in occupied)
            if plot not in range(s['plots']) or plot in occupied:raise ValueError('该田块无法播种')
            job['plot']=plot
        if key=='delve':
            job.update(team=list(s['team']),power=self.damage(s),floor=s['floor'])
            job['battle']=self._battle(s,job)
        s['jobs'].append(job)
        return recipe['name']+'已开始'

    @staticmethod
    def damage(s):
        weapon=next((g['power'] for g in s['gear'] if g['id']==s['equipped']),0)
        return (1+weapon+s['xp']//10+s['bond']//3)*(1+s['relic'])

    def _battle(self,s,job):
        level=job['floor'];team=job['team'];power=job['power']
        area,enemy,weak=self.catalog['areas'][(level-1)%len(self.catalog['areas'])]
        hp=3+2*level;stamina=4+len(team)*2
        rounds=[]
        equipped=next((g for g in s['gear'] if g['id']==s['equipped']),{})
        for turn in range(5):
            role=team[turn%len(team)]
            skill=self.catalog['skills'][role]
            damage=power+(skill['weak_bonus'] if role==weak else 0)+skill['every_third']*(turn%3==2)+min(5,s['mastery'][role]//4)
            if equipped.get('affix')==role:damage+=equipped['bonus']
            hp=max(0,hp-damage)
            if hp:stamina=max(0,stamina-max(0,1+level//3-skill['guard']))
            rounds.append(dict(role=role,skill=self.catalog['classes'][role][1],hit=damage,hp=hp,stamina=stamina))
            if not hp or not stamina:break
        return dict(area=area,enemy=enemy,rounds=rounds,won=not hp,hp=3+2*level,stamina=4+len(team)*2)

    def _equipment(self,s,rng,level):
        rare=rng.random()<0.23
        power=level+rng.randint(0,2)+(2 if rare else 0)
        if len(s['gear'])>=32 or (s['filter']=='rare' and not rare):
            s['inventory']['ore']+=2
            return '装备已分解为青铜矿 ×2'
        base=rng.choice(self.catalog['equipment'])
        piece=dict(base,id=uuid.UUID(int=rng.getrandbits(128)).hex,name=('星纹' if rare else '轻巧')+base['name'],power=power,rare=rare)
        s['gear'].append(piece)
        return f"{piece['name']} · 攻击 +{power}"

    def _resolve(self,c,s,j):
        key=j['key']; recipe=self.catalog['activities'][key];bag=s['inventory'];rng=random.Random(j['id'])
        if recipe['site']=='farm':
            s['ready'].append(j)
            self._note(s,recipe['name']+'成熟，可以收获')
            return
        for k,n in recipe['outputs'].items():bag[k]+=n
        detail='、'.join(self.catalog['items'][k]+' ×'+str(n) for k,n in recipe['outputs'].items())
        if key=='expand':s['plots']+=1;detail='新田地已开放'
        elif key=='barn':s['barn']+=1;detail='羊舍已扩建'
        elif key=='pasture':s['bond']+=1
        elif key=='mine' and rng.random()<.25:bag['crystal']+=1;detail+='、星辉晶 ×1'
        elif key=='weapon':detail=self._equipment(s,rng,1+s['floor']//4)
        elif key=='relic':s['relic']+=1;detail='圣遗物强化 +1'
        elif key in ('trade','dairy'):
            gain=10 if key=='trade' else 7
            self._money(c,s,gain,recipe['name'],j['id']);detail=f'谷币 +{gain}'
        elif key=='delve':
            level=j['floor'];area,enemy,weak=self.catalog['areas'][(level-1)%len(self.catalog['areas'])]
            battle=j['battle'];s['last_expedition']=j
            for role in j['team']:s['mastery'][role]+=1
            if battle['won']:
                s['floor']=level+1;s['xp']+=2;s['companions']+=int(level%3==1)
                bag['ore']+=2
                self._money(c,s,3,'远征战利品',j['id'])
                detail=f'{area} {level}层 · {enemy}已击败 · 矿石 ×2、谷币 +3'
                if rng.random()<.45:
                    event=rng.choice(self.catalog['events'])
                    bag[event['item']]+=event['count'];detail+=' · '+event['name']+'：'+self.catalog['items'][event['item']]+' ×'+str(event['count'])
                if rng.random()<.35:detail+=' · '+self._equipment(s,rng,1+level//3)
                if s['auto']>0:
                    if s['cash']>=recipe['cost']:
                        s['auto']-=1;self._schedule(c,s,'delve',j['end'])
                    else:s['auto']=0;detail+=' · 谷币不足，已回营'
            else:s['auto']=0;bag['ore']+=1;detail=f'{enemy}阻住去路，带回矿石 ×1。可调整装备与队伍。'
        s['xp']+=1
        self._note(s,recipe['name']+' · '+detail)

    def transact(self,action='view',arg='',request_id=None):
        with self.db.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            wall=self.clock();focus,running=self._focus(c)
            s=self._state(c,wall,focus)
            elapsed=max(0,wall-s['wall'])
            world=max(s['world'], elapsed*.1+.9*min(elapsed,max(0,focus-s['focus'])))
            dirty=False
            while s['jobs']:
                j=min(s['jobs'],key=lambda job:job['end'])
                if j['end']>world:break
                s['world']=j['end'];s['jobs'].remove(j);self._resolve(c,s,j);dirty=True
            s['world']=world
            message=''
            if action!='view':
                if not isinstance(request_id,str) or len(request_id)!=32:raise ValueError('缺少操作编号')
                command=json.dumps([action,arg],ensure_ascii=False)
                receipt=c.execute('SELECT command,message FROM hamlet_receipts WHERE id=?',(request_id,)).fetchone()
                if receipt:
                    if receipt[0]!=command:raise ValueError('操作编号已使用')
                    message=receipt[1]
                else:
                    message=self._command(c,s,action,arg,request_id)
                    c.execute('INSERT INTO hamlet_receipts VALUES(?,?,?)',(request_id,command,message));dirty=True
            if dirty:self._save(c,s)
            return dict(state=s,work=self._balance(c,'work'),coins=self._balance(c,'coin'),running=running,
                        damage=self.damage(s),message=message,catalog=self.catalog)

    def _command(self,c,s,action,arg,rid):
        if action=='start' and arg in self.catalog['activities']:
            return self._schedule(c,s,arg,s['world'])
        if action=='sow':
            crop,_,index=arg.partition(':')
            if crop not in self.catalog['activities'] or self.catalog['activities'][crop]['site']!='farm' or not index.isdecimal():
                raise ValueError('无效的作物或田块')
            return self._schedule(c,s,crop,s['world'],int(index))
        if action=='harvest':
            job=next((j for j in s['ready'] if j['id']==arg),None)
            if not job:raise ValueError('这块地还没有成熟作物')
            s['ready'].remove(job)
            recipe=self.catalog['activities'][job['key']]
            for k,n in recipe['outputs'].items():s['inventory'][k]+=n
            s['xp']+=1
            return self._note(s,recipe['name']+'已收进背包')
        if action=='exchange' and arg in ('work','coin'):
            if self._balance(c,arg)<1:raise ValueError('来源余额不足')
            table={'work':'work_points','coin':'coin_ledger'}[arg]
            c.execute('INSERT INTO '+table+' VALUES(?,?,?,?)',('hamlet:'+rid,-1,'雾铃谷兑换',stamp()))
            gain=3 if arg=='work' else 6
            self._money(c,s,gain,'兑换谷币','hamlet:'+rid)
            return f'兑换成功 · 谷币 +{gain}'
        if action=='auto' and arg in ('0','3','10','20'):
            s['auto']=int(arg);return '后续探索层数已更新'
        if action=='team':
            team=arg.split(',')
            if not 1<=len(team)<=min(3,1+s['companions']) or len(set(team))!=len(team) or any(k not in self.catalog['classes'] for k in team):raise ValueError('队伍人数超过已开放的位置，或成员重复。')
            s['team']=team;return '出战阵容已更新'
        if action=='equip' and any(g['id']==arg for g in s['gear']):
            s['equipped']=arg;return '装备已更换'
        if action=='filter' and arg in ('all','rare'):
            s['filter']=arg;return '掉落筛选已保存'
        if action=='dummy':return f"木桩测试 · 基础一击 {self.damage(s)} 点"
        raise ValueError('未知指令')
