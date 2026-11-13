"""Bounded daily companion context. Network work never runs on the Qt thread."""
import threading
import time
import uuid
from datetime import datetime
from difflib import SequenceMatcher
from .life_state import ZONE
from PySide6.QtCore import QObject,Signal
from ..models import RoleProvider
from ..personas import read_persona
from ..storage import plain


class FocusDialogue(QObject):
    ready=Signal(str,str,str,bool)
    def __init__(self,hub):
        super().__init__(hub);self.hub=hub;self.session='';self.history=[];self.calls=0
        self.used=0;self.last=0;self.busy=False;self.offline=False;self.cancel=threading.Event()
        self.request_id='';self.ready.connect(self.receive);self.response_reasons={}
        with hub.db.connect() as c:c.execute('CREATE TABLE IF NOT EXISTS focus_feedback_trace(id INTEGER PRIMARY KEY,created TEXT,role TEXT,source TEXT,reason TEXT)')
    def reset(self,key):
        self.cancel.set();self.cancel=threading.Event();self.session=key;self.history=[]
        self.calls=0;self.used=0;self.last=0;self.busy=False;self.offline=False;self.request_id=''
    def fallback(self,role,event,end,reason="local"):
        self.trace(role,"fallback",reason)
        if self.busy:
            self.cancel.set();self.cancel=threading.Event();self.request_id='';self.busy=False
        text=self.local_reply(event,end)
        self.remember(role,event,text,'fallback')
        self.hub.feedback.emit(role,text)
        if end:self.reset('')
    def respond(self,role,key,event,end=False,guidance=''):
        if key!=self.session:
            if self.busy:
                _,previous,_=self._pending;self.hub.feedback.emit(self._pending_role,previous)
            self.reset(key)
        today=datetime.now(ZONE).date().isoformat();self.cache_key='focus_words:'+role+':'+today
        cached=self.hub.db.get(self.cache_key,{})
        self.history=cached.get('history',[])[-12:]
        now=time.monotonic();config=self.hub.config.snapshot()
        if not self.hub.focus.options().get('llm_feedback',True) or self.busy or self.offline and now-self.last<60 or now-self.last<10:
            reason='disabled' if not self.hub.focus.options().get('llm_feedback',True) else 'busy_cancelled' if self.busy else 'failure_backoff' if self.offline and now-self.last<60 else 'cooldown'
            self.fallback(role,event,end,reason)
            return
        try:
            provider=RoleProvider(self.hub.root,role,config,self.cancel,purpose='focus_feedback')
            if not provider.config.get('model'):raise ValueError('No model')
            provider.config['stream']=False;provider.config['request_timeout']=(5,30)
            relation=next((r for r in self.hub.relations.list() if r['role_id']==role),{})
            system=('长期熟悉度：'+str(relation.get('affinity',50))+'；不要在回复中报分数。\n'+'\n'.join(name+'：'+value[:800] for name,value in read_persona(self.hub.root,role).items())+'\n'+self.hub.relations.context(role)+
                '\n你在番茄钟侧栏陪伴用户。按人格和当前情绪自然回应本次事件，用一句不超过60字的话，不说工具回执，不施压。只依据事件，不编造用户行为。')
            from .recovery import Recovery
            system+='\n'+guidance[:600]+'\n'+Recovery(self.hub.db).context()
            moment=datetime.now(ZONE);hour=moment.hour;part='凌晨' if hour<6 else '早上' if hour<11 else '中午' if hour<14 else '下午' if hour<18 else '晚上'
            state=self.hub.focus.status();record=(self.hub.focus.last_settlement or {}).get('record') or {}
            category=record.get('category') if end else state.get('category');category=category or state.get('category','专注')
            gap=round(moment.timestamp()-cached.get('at',moment.timestamp()))
            system+=f'\n当前时间 {moment.isoformat()}，{part}；活动类别：{category}；阶段：{state.get('phase', 'focus')}；计划时长：{state.get('duration',0)}秒；活动内容：{state.get("label") or record.get("label","")}；距上次陪伴 {gap} 秒。'
            system+='今天此角色首次陪伴，允许一句简短自然寒暄。' if not cached else '今天已陪伴过，不重复寒暄。'
            system+='不要提问、不要询问是否准备好、不布置额外任务。区别工作、学习、家务和休息语境。避免重复近期措辞。'
            messages=self.history[-12:]+[{'role':'user','content':event[:300]}]
            reserved=len((system+str(messages)).encode('utf-8'))+120
            if self.used+reserved>24000:raise ValueError('Budget')
            from .database import day
            daily=self.hub.db.get('focus_dialogue_budget',{})
            if daily.get('day')!=day():daily={'day':day(),'calls':0,'reserved':0}
            if daily['calls']>=60 or daily['reserved']+reserved>100000:raise ValueError('Daily budget')
            daily['calls']+=1;daily['reserved']+=reserved;self.hub.db.set('focus_dialogue_budget',daily)
        except Exception as exc:
            reason=str(exc) if type(exc) is ValueError and str(exc) in ('No model','Budget','Daily budget') else 'prepare:'+type(exc).__name__
            self.last=now;self.offline=True;self.fallback(role,event,end,reason)
            return
        self.calls+=1;self.used+=reserved;self.last=now;self.busy=True
        ticket=uuid.uuid4().hex;self.request_id=ticket;self.trace(role,'request','started')
        def work():
            failed=False
            try:
                blocks,_,_=provider.complete(system,messages,max_tokens=120)
                text=plain(blocks).strip()[:200]
                if not text or '?' in text or '？' in text:raise ValueError('UnwantedQuestion')
                if any(SequenceMatcher(None,text,m['content']).ratio()>.85 for m in messages if m['role']=='assistant'):raise ValueError('RepeatedReply')
            except Exception as exc:
                text=event;failed=True;self.response_reasons[ticket]=str(exc) if type(exc) is ValueError and str(exc) in ('UnwantedQuestion','RepeatedReply') else 'request:'+type(exc).__name__
            try:self.ready.emit(ticket,role,text,failed)
            except RuntimeError:pass
        self._pending=(key,event,end);self._pending_role=role
        threading.Thread(target=work,daemon=True,name='focus-dialogue').start()
    def receive(self,key,role,text,failed):
        reason=self.response_reasons.pop(key,'accepted')
        if key!=self.request_id:return
        self.trace(role,'fallback' if failed else 'llm',reason)
        self.busy=False;self.offline=failed
        _,event,end=self._pending
        if failed:text=self.local_reply(event,end)
        self.history=(self.history+[{'role':'user','content':event},{'role':'assistant','content':text}])[-12:]
        self.remember(role,event,text,'fallback' if failed else 'llm')
        self.hub.feedback.emit(role,text)
        if end:self.reset('')
    def trace(self,role,source,reason):
        try:
            with self.hub.db.connect() as c:
                c.execute('INSERT INTO focus_feedback_trace(created,role,source,reason) VALUES(?,?,?,?)',(datetime.now(ZONE).isoformat(),role,source,reason))
                c.execute('DELETE FROM focus_feedback_trace WHERE id NOT IN (SELECT id FROM focus_feedback_trace ORDER BY id DESC LIMIT 1000)')
        except Exception:pass  # Diagnostics must never alter the reply strategy.
    def local_reply(self,event,end=False):
        state=self.hub.focus.status();record=(self.hub.focus.last_settlement or {}).get('record') or {}
        category=record.get('category') if end else state.get('category');category=category or state.get('category','专注')
        phase=(self.hub.focus.last_settlement or {}).get('phase') if end else state.get('phase')
        if phase in ('short_break','long_break') or event.startswith('下班结算'):return event
        if state.get('state')=='paused':
            cue={'工作':'先放下手里的工作，喘口气。','学习':'学到的先放一放，让脑子缓一会儿。','家务':'收拾到这里，先歇歇手。'}.get(category,'先缓一会儿。')
        elif end:
            cue={'工作':'今天这份工作投入，也值得被认真看见。','学习':'学习告一段落，给脑子留一点消化时间。','家务':'生活被照顾了一点，也照顾一下自己。'}.get(category,'给自己一点放松的时间。')
        else:
            cue={'工作':'工作先按眼前这一件推进。','学习':'学到一点、弄懂一点，都算进展。','家务':'慢慢收拾，让生活轻一点。'}.get(category,'按自己的节奏来。')
        return event+' '+cue
    def remember(self,role,event,text,source):
        moment=datetime.now(ZONE);key='focus_words:'+role+':'+moment.date().isoformat()
        previous=self.hub.db.get(key,{}).get('history',[])
        self.hub.db.set(key,{'at':moment.timestamp(),'history':(previous+[{'role':'user','content':event[:300]},{'role':'assistant','content':text[:200]}])[-12:]})
        self.hub.db.set('focus_dialogue_status',{'source':source,'role':role,'at':moment.isoformat()})
        # Only recent daily side-panel context; never enters chat or long-term memory.
        cutoff=(moment.date().toordinal()-7)
        with self.hub.db.connect() as c:
            for row in c.execute("SELECT key FROM module_settings WHERE key LIKE 'focus_words:%'").fetchall():
                try:old=datetime.fromisoformat(row['key'][-10:]).date().toordinal()<=cutoff
                except ValueError:old=False
                if old:c.execute('DELETE FROM module_settings WHERE key=?',(row['key'],))
    def close(self):self.reset('')
