"""Independent eye/focus estimation from observed intervals, never a medical measurement."""
import sys,time
from datetime import datetime,timedelta
from .life_state import ZONE
from .database import stamp
from .life import number
from .notices import notify
MODES={'auto':'自动（日间累积 / 夜间按活动）','screen':'持续用眼（阅读 / 视频）','paper':'纸面学习（仍用眼）','rest':'离屏休息','paused':'暂停估算'}

def input_active():
 if sys.platform!='win32':return None
 import ctypes
 from ctypes import wintypes
 class LASTINPUTINFO(ctypes.Structure):_fields_=[('cbSize',wintypes.UINT),('dwTime',wintypes.DWORD)]
 info=LASTINPUTINFO();info.cbSize=ctypes.sizeof(info)
 if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):return None
 # Unsigned arithmetic also handles the ~49-day counter wrap.
 idle=(ctypes.windll.kernel32.GetTickCount()-info.dwTime)&0xffffffff
 return idle<60000 and bool(ctypes.windll.user32.GetForegroundWindow())

class Attention:
 def __init__(self,db,clock=time.monotonic):
  self.db=db;self.clock=clock;self.anchor=clock();self.last_mode='未开始';self._seconds=0;self.new_alert=0
  with db.connect() as c:c.executescript('''CREATE TABLE IF NOT EXISTS attention_state(id INTEGER PRIMARY KEY,eye REAL,focus REAL,band INTEGER,last_alert TEXT,created TEXT,updated TEXT);
   CREATE TABLE IF NOT EXISTS attention_days(day TEXT PRIMARY KEY,screen_seconds REAL DEFAULT 0,rest_seconds REAL DEFAULT 0,paper_seconds REAL DEFAULT 0,eye REAL,focus REAL);
   CREATE TABLE IF NOT EXISTS attention_capacity(day TEXT PRIMARY KEY,spent REAL NOT NULL DEFAULT 0);
   CREATE TABLE IF NOT EXISTS eye_daily_load(day TEXT PRIMARY KEY,minutes REAL NOT NULL DEFAULT 0);
   CREATE TABLE IF NOT EXISTS attention_sleep(day TEXT PRIMARY KEY,hours REAL);
   ''')
  with db.connect() as c:
   created=c.execute('INSERT OR IGNORE INTO attention_state VALUES(1,0,100,0,NULL,?,?)',(stamp(),stamp())).rowcount
   c.execute('CREATE TABLE IF NOT EXISTS attention_boundaries(day TEXT PRIMARY KEY,before REAL,after REAL)')
   if created:
    now=datetime.now(ZONE);cycle=now.date() if now.hour>=9 else now.date()-timedelta(days=1)
    c.execute('INSERT OR IGNORE INTO attention_boundaries VALUES(?,0,0)',(cycle.isoformat(),))
  if not db.get('attention_rest_half_v1',False):
   saved=db.get('attention_options',{})
   if 'rest_focus' in saved:saved['rest_focus']=max(.01,saved['rest_focus']/2);db.set('attention_options',saved)
   db.set('attention_rest_half_v1',True)
  if not db.get('attention_eye_rest_v2',False):
   saved=db.get('attention_options',{});saved['rest_eye']=max(3.5,saved.get('rest_eye',.65)*5);saved['rest_eye']=min(20,saved['rest_eye']);db.set('attention_options',saved);db.set('attention_eye_rest_v2',True)
 def options(self):return {'mode':'auto','intensity':'medium','eye_rate':.35,'focus_rate':.18,'rest_eye':3.5,'rest_focus':.25,'sleep_eye':7,'sleep_focus':6,'light_threshold':60,'high_threshold':80,'cooldown_minutes':60,'night_start':'22:00','night_end':'09:00','focus_eye_bonus':.15}|self.db.get('attention_options',{})
 def configure(self,values):
  o=self.options()|values
  if o['mode'] not in MODES or o['intensity'] not in ('low','medium','high'):raise ValueError('请选择有效模式和强度')
  for key,lo,hi in [('eye_rate',.05,2),('focus_eye_bonus',0,2),('focus_rate',.01,1),('rest_eye',.05,20),('rest_focus',.01,2),('sleep_eye',0,20),('sleep_focus',0,20),('light_threshold',10,90),('high_threshold',20,99),('cooldown_minutes',15,240)]:o[key]=number(o[key],lo,hi,key)
  if o['light_threshold']>=o['high_threshold']:raise ValueError('轻提醒阈值必须小于高提醒阈值')
  for key in ('night_start','night_end'):
   try:o[key]=datetime.strptime(o[key],'%H:%M').strftime('%H:%M')
   except (ValueError,TypeError):raise ValueError('夜间时间请用 HH:mm')
  if o['night_start']==o['night_end']:raise ValueError('夜间开始与结束不能相同')
  self.db.set('attention_options',o);self.anchor=self.clock();self._seconds=0
 def status(self):
  with self.db.connect() as c:r=dict(c.execute('SELECT * FROM attention_state WHERE id=1').fetchone())
  with self.db.connect() as c:spent=c.execute('SELECT spent FROM attention_capacity WHERE day=?',(datetime.now(ZONE).date().isoformat(),)).fetchone()
  with self.db.connect() as c:load=c.execute('SELECT minutes FROM eye_daily_load WHERE day=?',(datetime.now(ZONE).date().isoformat(),)).fetchone()
  return r|{'eye_floor':min(20,(load[0] if load else 0)*.02),'focus_cap':max(0,100-(spent[0] if spent else 0)/2),'source':self.last_mode,'mode':self.options()['mode']}
 def tick(self,focus=None,active=None,now=None):
  self.new_alert=0
  self.daily_boundary(now)
  current=self.clock();seconds=max(0,current-self.anchor);self.anchor=current
  if seconds>30:return # Resume/restart/offline time is not presumed observed or restful.
  self._seconds+=seconds
  if self._seconds<5:return
  seconds=self._seconds;self._seconds=0;now=now or datetime.now(ZONE);o=self.options();mode=o['mode'];active=input_active() if active is None else active
  focus=focus or {};working=focus.get('state')=='running' and focus.get('phase','focus')=='focus'
  clock=now.astimezone(ZONE).strftime('%H:%M');night=clock>=o['night_start'] or clock<o['night_end'] if o['night_start']>o['night_end'] else o['night_start']<=clock<o['night_end']
  if mode=='auto':mode='screen' if active or working or '09:00'<=clock<'22:00' else 'rest' if active is False and (night or focus.get('state')=='running' and not working) else 'paused'
  # Mouse/keyboard use contradicts an explicit rest interval: never recover while interacting.
  elif mode=='rest' and active:mode='screen'
  self.last_mode={'screen':'正在用眼','paper':'纸面学习（仍用眼）','rest':'有效离屏休息','paused':'未计入 / 等待明确活动'}[mode]
  if mode=='paused':return
  with self.db.connect() as c:
   c.execute('BEGIN IMMEDIATE');r=c.execute('SELECT * FROM attention_state WHERE id=1').fetchone();eye=r['eye'];power=r['focus'];minutes=seconds/60;scale={'low':.7,'medium':1,'high':1.4}[o['intensity']]
   if mode=='screen':eye+=minutes*(o['eye_rate']*scale+(o['focus_eye_bonus'] if working and focus.get('category') in ('工作','学习') else 0));power-=minutes*o['focus_rate']*scale
   elif mode=='paper':eye+=minutes*o['eye_rate']*.7;power-=minutes*o['focus_rate']
   else:eye-=minutes*o['rest_eye'];power+=minutes*o['rest_focus']
   consumed=max(0,r['focus']-max(0,power));daykey=now.astimezone(ZONE).date().isoformat()
   c.execute('INSERT INTO attention_capacity VALUES(?,?) ON CONFLICT(day) DO UPDATE SET spent=spent+excluded.spent',(daykey,consumed))
   spent=c.execute('SELECT spent FROM attention_capacity WHERE day=?',(daykey,)).fetchone()[0];cap=max(0,100-spent/2)
   if working and focus.get('category') in ('工作','学习') and mode in ('screen','paper'):
    c.execute('INSERT INTO eye_daily_load VALUES(?,?) ON CONFLICT(day) DO UPDATE SET minutes=minutes+excluded.minutes',(daykey,minutes))
   load=c.execute('SELECT minutes FROM eye_daily_load WHERE day=?',(daykey,)).fetchone();floor=min(20,(load[0] if load else 0)*.02)
   eye=max(floor,min(100,eye));power=max(0,min(cap,power));band=r['band']
   if eye<o['light_threshold']-10:band=0
   level=2 if eye>=o['high_threshold'] else 1 if eye>=o['light_threshold'] else 0
   last=datetime.fromisoformat(r['last_alert']) if r['last_alert'] else None
   if level>band and (level==2 and band==1 or not last or (now-last).total_seconds()>=o['cooldown_minutes']*60):
    key='attention:'+str(level)+':'+now.isoformat();notify(c,key,f"视疲劳估计 {eye:.0f}%："+('建议离屏休息；恢复后再继续。可在生活恢复站选择离屏休息。' if level==2 else '可以稍作远眺，调整一下节奏。'),level==2,True,now.isoformat());band=level;self.new_alert=level
    c.execute('UPDATE attention_state SET last_alert=? WHERE id=1',(now.isoformat(),))
   c.execute('UPDATE attention_state SET eye=?,focus=?,band=?,updated=? WHERE id=1',(eye,power,band,stamp()))
   # Attribute observed slices around midnight without duplicating a source interval.
   start=now-timedelta(seconds=seconds)
   while start<now:
    end=min(now,(start+timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0));span=(end-start).total_seconds();column={'screen':'screen_seconds','rest':'rest_seconds','paper':'paper_seconds'}[mode]
    c.execute('INSERT OR IGNORE INTO attention_days(day) VALUES(?)',(start.astimezone(ZONE).date().isoformat(),));c.execute(f'UPDATE attention_days SET {column}={column}+?,eye=?,focus=? WHERE day=?',(span,eye,power,start.astimezone(ZONE).date().isoformat()));start=end
 def daily_boundary(self,now=None):
  now=(now or datetime.now(ZONE)).astimezone(ZONE);today=now.date().isoformat()
  with self.db.connect() as c:
   c.execute('CREATE TABLE IF NOT EXISTS attention_boundaries(day TEXT PRIMARY KEY,before REAL,after REAL)')
   c.execute('BEGIN IMMEDIATE');r=c.execute('SELECT * FROM attention_state WHERE id=1').fetchone()
   if now.hour>=9 and not c.execute('SELECT 1 FROM attention_boundaries WHERE day=?',(today,)).fetchone():
    # First install starts from its configured baseline. Offline catch-up applies once, not once per missed day.
    previous=(now.date()-timedelta(days=1)).isoformat();old=c.execute('SELECT eye FROM attention_days WHERE day=?',(previous,)).fetchone()
    base=old['eye'] if old and old['eye'] is not None else r['eye']
    rate=.1 if base<20 else .2 if base<50 else .3 if base<80 else .5
    after=round(base*rate,2)
    c.execute('INSERT INTO attention_boundaries VALUES(?,?,?)',(today,base,after));c.execute('UPDATE attention_state SET eye=?,band=0 WHERE id=1',(after,))
   if now.hour>=22:
    current=c.execute('SELECT eye FROM attention_state WHERE id=1').fetchone()[0]
    if current>50:notify(c,'attention-night:'+today,f'22点视疲劳检查：当前估计 {current:.0f}%，建议离屏休息。',True,True,now.isoformat())
 @staticmethod
 def apply_sleep(c,day,hours,quality=1):
  if hours is None or hours<=0 or not c.execute("SELECT 1 FROM sqlite_master WHERE name='attention_state'").fetchone():return
  today=datetime.now(ZONE).date()
  if day not in (today.isoformat(),(today-timedelta(days=1)).isoformat()):return
  if c.execute('SELECT 1 FROM attention_sleep WHERE day=?',(day,)).fetchone():return
  # Conservatively discount already counted rest across the reported night, never double-credit it.
  next_day=(datetime.fromisoformat(day)+timedelta(days=1)).date().isoformat()
  counted=c.execute('SELECT COALESCE(sum(rest_seconds),0)/3600 FROM attention_days WHERE day IN (?,?)',(day,next_day)).fetchone()[0]
  hours=max(0,min(hours,10)*quality-counted)
  import json
  cfg=c.execute("SELECT value FROM module_settings WHERE key='attention_options'").fetchone();o=json.loads(cfg[0]) if cfg else {}
  spent=c.execute('SELECT spent FROM attention_capacity WHERE day=?',(today.isoformat(),)).fetchone();cap=max(0,100-(spent[0] if spent else 0)/2)
  load=c.execute('SELECT minutes FROM eye_daily_load WHERE day=?',(today.isoformat(),)).fetchone();floor=min(20,(load[0] if load else 0)*.02)
  c.execute('INSERT INTO attention_sleep VALUES(?,?)',(day,hours));c.execute('UPDATE attention_state SET eye=max(?,eye-?),focus=min(?,focus+?),updated=? WHERE id=1',(floor,hours*o.get('sleep_eye',7),cap,hours*o.get('sleep_focus',6),stamp()))
 def sleep(self,day,hours):
  with self.db.connect() as c:c.execute('BEGIN IMMEDIATE');self.apply_sleep(c,day,hours)
 def days(self):
  with self.db.connect() as c:return [dict(r) for r in c.execute('SELECT * FROM attention_days ORDER BY day DESC LIMIT 14')]
