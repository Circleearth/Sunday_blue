"""Role-level connection overrides and bounded, content-free request diagnostics."""
import copy
import json
import sqlite3
import time
import uuid
from .provider import Provider
from .modules.database import ModuleDB,stamp


def resolve_api(config,role,purpose='chat'):
    api=copy.deepcopy(config['api'])
    profile=config.get('roles',{}).get(role,{}).get('model_profile',{})
    if profile.get('enabled'):
        for key in ('protocol','base_url','model','auth','max_tokens','context_limit','key_encrypted'):
            if key in profile:api[key]=profile[key]
        mode=profile.get('reasoning','off')
        api['thinking_budget']=0;api.pop('reasoning_effort',None)
        if mode=='anthropic_budget':
            if api['protocol']!='anthropic':raise ValueError('当前接口不是 Anthropic，不能使用其思考预算参数。')
            budget=int(profile.get('thinking_budget',1024))
            if budget<1024 or budget>=int(api['max_tokens']):raise ValueError('思考预算需至少 1024，且小于最大输出。')
            api['thinking_budget']=budget
        elif mode=='openai_effort':
            if api['protocol']!='openai':raise ValueError('当前接口不是 OpenAI 兼容接口。')
            effort=profile.get('reasoning_effort','medium')
            if effort not in ('low','medium','high'):raise ValueError('未知推理强度')
            api['reasoning_support']='openai_effort';api['reasoning_effort']=effort
        elif mode!='off':raise ValueError('未知推理参数模式')
    if purpose in ('social','focus_feedback'):
        api['thinking_budget']=0;api.pop('reasoning_effort',None)
        if profile.get('enabled') and profile.get('light_model','').strip():api['model']=profile['light_model'].strip()
    return api


class RoleProvider(Provider):
    def __init__(self,root,role,config,cancel=None,purpose='chat'):
        super().__init__(resolve_api(config,role,purpose),cancel)
        self.root,self.role,self.purpose=root,role,purpose

    def complete(self,*args,**kwargs):
        started=time.monotonic();usage={};error=''
        try:
            result=super().complete(*args,**kwargs);usage=result[1];return result
        except Exception as exc:
            # Do not log arbitrary upstream text, request bodies, keys or headers.
            error=type(exc).__name__;raise
        finally:
            try:self._record(started,usage,error,kwargs.get('max_tokens'))
            except (OSError,sqlite3.Error):pass  # Diagnostic failure must not lose a reply.

    def _record(self,started,usage,error,max_tokens):
        if self.purpose=='focus_feedback' and self.cancel.is_set():return
        database=ModuleDB(self.root)
        with database.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS request_diagnostics (
                id TEXT PRIMARY KEY,role TEXT,model TEXT,protocol TEXT,purpose TEXT,
                elapsed REAL,usage TEXT,error TEXT,reasoning TEXT,created TEXT)''')
            mode='anthropic_budget' if self.config.get('thinking_budget') else self.config.get('reasoning_effort','off')
            if mode=='anthropic_budget' and (max_tokens or self.config['max_tokens'])<=self.config['thinking_budget']:
                mode='off_output_budget'
            db.execute('INSERT INTO request_diagnostics VALUES(?,?,?,?,?,?,?,?,?,?)',
                (uuid.uuid4().hex,self.role,self.config.get('model',''),self.config['protocol'],self.purpose,
                 round(time.monotonic()-started,3),json.dumps(usage),error,mode,stamp()))
