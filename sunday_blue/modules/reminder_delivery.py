"""Shared notification delivery. Network work never runs on the Qt UI thread."""
import importlib.util
import re
import threading
import uuid
import socket
from datetime import datetime,timedelta
from pathlib import Path
from urllib.error import HTTPError,URLError
from urllib.parse import urlsplit
from PySide6.QtCore import QObject,Signal
from .database import stamp

class ReminderDelivery(QObject):
    result=Signal(str,bool)
    check_result=Signal(str,object)
    def __init__(self,hub):
        super().__init__(hub);self.hub=hub;self.active=set();self.closed=False
        self._module=None;self._module_lock=threading.Lock();self._check_busy=False
        self.result.connect(self.finished);hub.closed.connect(self.close)
        with hub.db.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS reminder_delivery_details (occurrence_id TEXT PRIMARY KEY,attempts INTEGER,updated TEXT,error TEXT)')
    def close(self):self.closed=True
    @staticmethod
    def validate(cfg):
        cfg={k:str(cfg.get(k,'')).strip() for k in ('profile','openid','proxy')};cfg['profile']=cfg['profile'] or 'qqbot'
        if not re.fullmatch(r'[A-Za-z0-9_-]+',cfg['profile']):raise ValueError('bot profile 只能包含字母、数字、下划线或横线')
        if not re.fullmatch(r'[A-Za-z0-9_-]+',cfg['openid']):raise ValueError('请填写有效的接收者 openid')
        if cfg['proxy']:
            try:
                url=urlsplit(cfg['proxy']);valid=url.scheme in ('http','https') and url.hostname and url.port!=0
            except ValueError:valid=False
            if not valid:raise ValueError('代理请使用 http:// 或 https:// 地址，或留空')
        return cfg
    @staticmethod
    def error_text(exc):
        if isinstance(exc,HTTPError):return f'QQ 服务返回 HTTP {exc.code}，请检查权限、接收者和主动消息额度。'
        if isinstance(exc,(TimeoutError,URLError)):return '网络超时或连接失败；发送结果可能未确认，请核对 QQ 后重试。'
        if isinstance(exc,ValueError):return str(exc)
        return 'QQ 渠道异常（'+type(exc).__name__+'），请检查配置或网络。'
    def _transport(self):
        with self._module_lock:
            if self._module is None:
                path=self.hub.root/'extensions/plugins/qq-reminders/daemon/run.py'
                if not path.exists():path=Path(__file__).resolve().parents[2]/'extensions/plugins/qq-reminders/daemon/run.py'
                spec=importlib.util.spec_from_file_location('sunday_shared_qq_transport',str(path))
                module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);self._module=module
            return self._module
    def _connect(self,cfg):
        cfg=self.validate(cfg);module=self._transport();creds=module._creds(cfg['profile'])
        if not creds:raise ValueError('未找到 bot profile 对应的 DSH 凭据')
        transport={'http_proxy':cfg['proxy']};token=module._token(creds,transport)
        if not isinstance(token,str) or not token.strip():raise ValueError('QQ 未返回有效访问令牌，请检查 bot 凭据')
        return module,creds,token,transport,cfg
    def diagnose(self,cfg=None):
        cfg=self.hub.db.get('shared_qq',{}) if cfg is None else cfg
        result={'openid_ok':False,'creds_ok':False,'token_ok':False,'error':''}
        try:
            cfg=self.validate(cfg);result['openid_ok']=True;module=self._transport();creds=module._creds(cfg['profile'])
            if not creds:raise ValueError('未找到 bot profile 对应的 DSH 凭据')
            result['creds_ok']=True;token=module._token(creds,{'http_proxy':cfg['proxy']})
            if not isinstance(token,str) or not token.strip():raise ValueError('QQ 未返回有效访问令牌')
            result['token_ok']=True
        except Exception as exc:result['error']=self.error_text(exc)
        return result
    def test_send(self,text='🟢 Sunday Blue 试发消息：收到即说明主动提醒链路可用',cfg=None):
        module,creds,token,transport,cfg=self._connect(self.hub.db.get('shared_qq',{}) if cfg is None else cfg)
        if not module._qq_send(creds,token,cfg['openid'],text,transport):raise ValueError('QQ 未确认接收，请核对 QQ 后再重试。')
        return True
    def start_check(self,cfg,send=False):
        if self.closed or self._check_busy:raise ValueError('已有渠道检查或试发进行中，请稍候')
        cfg=self.validate(cfg);key=uuid.uuid4().hex;self._check_busy=True
        def run():
            try:
                if send:
                    self.test_send(cfg=cfg);out={'ok':True,'message':'QQ 接口已接受测试消息，请到 QQ 核对。此结果不代表客户端已读。'}
                else:
                    st=self.diagnose(cfg);out={'ok':st['token_ok'],'message':('凭据和令牌验证通过；接收者是否可达请通过试发确认。' if st['token_ok'] else st['error'])}
            except Exception as exc:out={'ok':False,'message':self.error_text(exc)}
            finally:self._check_busy=False
            if not self.closed:
                try:self.check_result.emit(key,out)
                except RuntimeError:pass
        threading.Thread(target=run,daemon=True,name='shared-qq-check').start();return key
    def tick(self):
        if self.closed:return
        changed=False
        from .recovery import Recovery
        protection=Recovery(self.hub.db).protected()
        for item in self.hub.planner.due():
            if protection and not self.hub.planner.urgent(item['schedule_id']):continue
            if item['local_status']=='pending':
                self.hub.planner.mark(item['id'],'local','sent');changed=True
                self.hub.reminder_alarm.play('focus',self.hub.focus.options()|self.hub.db.get('reminder_sound',{'sound_enabled':True,'volume':65,'sounds':{'focus':''}}))
                self.hub.failed.emit('提醒：'+item['title'])
                parent=self.hub.parent();icon=getattr(getattr(parent,'tray',None),'icon',None)
                if icon and icon.isVisible():icon.showMessage('Sunday Blue 提醒',item['title'])
            if item['qq_status']=='pending' and item['id'] not in self.active and len(self.active)<2:
                self.active.add(item['id']);self.hub.planner.mark(item['id'],'qq','sending');changed=True
                cfg=self.hub.db.get('shared_qq',{})
                threading.Thread(target=self.send,args=(item,cfg),daemon=True,name='shared-qq-reminder').start()
        if changed:self.hub.changed.emit('planner')
    def send(self,item,cfg):
        success=False;error='';attempted=False
        try:
            if item.get('schedule_id')=='life-report':
                module,creds,token,transport,cfg=self._connect(cfg)
                if datetime.now().astimezone()>=datetime.fromisoformat(item['due'])+timedelta(days=1):raise ValueError('上报周期已过期，不再发送')
                attempted=True
                success=bool(module._qq_send(creds,token,cfg['openid'],item['title'],transport))
            else:success=self.test_send(item['title'],cfg)
        except Exception as exc:
            error=self.error_text(exc)
            if isinstance(exc,HTTPError) and exc.code in (401,403,429):attempted=False
            elif isinstance(exc,URLError) and (isinstance(exc.reason,(socket.gaierror,ConnectionRefusedError)) or getattr(exc.reason,'errno',None) in (10051,10065,10061,11001)):attempted=False
        # Persist before emitting: closing a dialog/app must not discard an arrived receipt.
        try:
            with self.hub.db.connect() as db:
                db.execute('UPDATE reminder_occurrences SET qq_status=? WHERE id=?',('sent' if success else 'unknown' if attempted else 'failed',item['id']))
                db.execute('INSERT INTO reminder_delivery_details VALUES(?,1,?,?) ON CONFLICT(occurrence_id) DO UPDATE SET attempts=attempts+1,updated=excluded.updated,error=excluded.error',(item['id'],stamp(),error))
        except Exception:success=False
        if not self.closed:
            try:self.result.emit(item['id'],bool(success))
            except RuntimeError:pass
    def finished(self,rid,success):
        self.active.discard(rid);self.hub.changed.emit('planner')
        if not success:self.hub.failed.emit('QQ 提醒未确认送达，请在提醒页查看原因，核对 QQ 后手动重试。')
    def details(self):
        with self.hub.db.connect() as db:return {r['occurrence_id']:dict(r) for r in db.execute('SELECT * FROM reminder_delivery_details')}
