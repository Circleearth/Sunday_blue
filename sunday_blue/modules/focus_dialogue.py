"""Bounded, disposable focus dialogue. Network work never runs on the Qt thread."""
import threading
import time
import uuid
from PySide6.QtCore import QObject,Signal
from ..models import RoleProvider
from ..personas import read_persona
from ..storage import plain


class FocusDialogue(QObject):
    ready=Signal(str,str,str,bool)
    def __init__(self,hub):
        super().__init__(hub);self.hub=hub;self.session='';self.history=[];self.calls=0
        self.used=0;self.last=0;self.busy=False;self.offline=False;self.cancel=threading.Event()
        self.request_id='';self.ready.connect(self.receive)
    def reset(self,key):
        self.cancel.set();self.cancel=threading.Event();self.session=key;self.history=[]
        self.calls=0;self.used=0;self.last=0;self.busy=False;self.offline=False;self.request_id=''
    def fallback(self,role,event,end):
        if self.busy:
            self.cancel.set();self.cancel=threading.Event();self.request_id='';self.busy=False
        self.history=(self.history+[{'role':'user','content':event},{'role':'assistant','content':event}])[-4:]
        self.hub.feedback.emit(role,event)
        if end:self.reset('')
    def respond(self,role,key,event,end=False):
        if key!=self.session:
            if self.busy:
                _,previous,_=self._pending;self.hub.feedback.emit(self._pending_role,previous)
            self.reset(key)
        now=time.monotonic();config=self.hub.config.snapshot()
        if not self.hub.focus.options().get('llm_feedback',True) or self.busy or self.offline or self.calls>=4 or now-self.last<30:
            self.fallback(role,event,end)
            return
        try:
            provider=RoleProvider(self.hub.root,role,config,self.cancel,purpose='focus_feedback')
            if not provider.config.get('model'):raise ValueError('No model')
            provider.config['stream']=False;provider.config['request_timeout']=(4,6)
            relation=next((r for r in self.hub.relations.list() if r['role_id']==role),{})
            system=('长期熟悉度：'+str(relation.get('affinity',50))+'；不要在回复中报分数。\n'+'\n'.join(name+'：'+value[:800] for name,value in read_persona(self.hub.root,role).items())+'\n'+self.hub.relations.context(role)+
                '\n你在番茄钟侧栏陪伴用户。按人格和当前情绪自然回应本次事件，用一句不超过60字的话，不说工具回执，不施压。只依据事件，不编造用户行为。')
            messages=self.history[-4:]+[{'role':'user','content':event[:300]}]
            reserved=len((system+str(messages)).encode('utf-8'))+120
            if self.used+reserved>24000:raise ValueError('Budget')
            from .database import day
            daily=self.hub.db.get('focus_dialogue_budget',{})
            if daily.get('day')!=day():daily={'day':day(),'calls':0,'reserved':0}
            if daily['calls']>=24 or daily['reserved']+reserved>100000:raise ValueError('Daily budget')
            daily['calls']+=1;daily['reserved']+=reserved;self.hub.db.set('focus_dialogue_budget',daily)
        except Exception:
            self.offline=True;self.fallback(role,event,end)
            return
        self.calls+=1;self.used+=reserved;self.last=now;self.busy=True
        ticket=uuid.uuid4().hex;self.request_id=ticket
        def work():
            failed=False
            try:
                blocks,_,_=provider.complete(system,messages,max_tokens=120)
                text=plain(blocks).strip()[:200]
                if not text:raise ValueError('Empty')
            except Exception:text=event;failed=True
            try:self.ready.emit(ticket,role,text,failed)
            except RuntimeError:pass
        self._pending=(key,event,end);self._pending_role=role
        threading.Thread(target=work,daemon=True,name='focus-dialogue').start()
    def receive(self,key,role,text,failed):
        if key!=self.request_id:return
        self.busy=False;self.offline=failed
        _,event,end=self._pending
        self.history=(self.history+[{'role':'user','content':event},{'role':'assistant','content':text}])[-4:]
        self.hub.feedback.emit(role,text)
        if end:self.reset('')
    def close(self):self.reset('')
