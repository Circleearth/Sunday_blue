"""Shared notification channels, reusing QQ transport without changing its daemon."""
import importlib.util
import re
import threading
from pathlib import Path
from PySide6.QtCore import QObject,Signal

class ReminderDelivery(QObject):
    result=Signal(str,bool)
    def __init__(self,hub):
        super().__init__(hub);self.hub=hub;self.active=set();self.result.connect(self.finished)
    def tick(self):
        for item in self.hub.planner.due():
            if item['local_status']=='pending':
                self.hub.planner.mark(item['id'],'local','sent')
                self.hub.reminder_alarm.play('focus',self.hub.focus.options()|self.hub.db.get('reminder_sound',{'sound_enabled':True,'volume':65,'sounds':{'focus':''}}))
                self.hub.failed.emit('提醒：'+item['title'])
                parent=self.hub.parent();icon=getattr(getattr(parent,'tray',None),'icon',None)
                if icon and icon.isVisible():icon.showMessage('Sunday Blue 提醒',item['title'])
            if item['qq_status']=='pending' and item['id'] not in self.active:
                self.active.add(item['id']);self.hub.planner.mark(item['id'],'qq','sending')
                cfg=self.hub.db.get('shared_qq',{})
                threading.Thread(target=self.send,args=(item,cfg),daemon=True).start()
    def send(self,item,cfg):
        success=False
        try:
            profile=cfg.get('profile','qqbot');openid=cfg.get('openid','')
            if not re.fullmatch(r'[A-Za-z0-9_-]+',profile) or not re.fullmatch(r'[A-Za-z0-9_-]+',openid):raise ValueError('QQ channel not configured')
            path=self.hub.root/'extensions/plugins/qq-reminders/daemon/run.py'
            spec=importlib.util.spec_from_file_location('sunday_shared_qq_transport',path)
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            transport={'http_proxy':cfg.get('proxy','')};creds=module._creds(profile)
            if not creds:raise ValueError('QQ credentials missing')
            token=module._token(creds,transport)
            success=module._qq_send(creds,token,openid,item['title'],transport)
        except Exception:pass
        try:self.result.emit(item['id'],bool(success))
        except RuntimeError:pass
    def finished(self,rid,success):
        self.active.discard(rid);self.hub.planner.mark(rid,'qq','sent' if success else 'failed')
        self.hub.changed.emit('planner')
        if not success:self.hub.failed.emit('QQ 提醒未确认送达，请在提醒页检查渠道并手动重试。')

    def _transport(self):
        path=self.hub.root/'extensions/plugins/qq-reminders/daemon/run.py'
        if not path.exists():
            # tests build an empty source root; the package's own repository keeps the plugin
            path=Path(__file__).resolve().parents[2]/'extensions/plugins/qq-reminders/daemon/run.py'
        spec=importlib.util.spec_from_file_location('sunday_shared_qq_transport',str(path))
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module

    def diagnose(self):
        """Read-only channel check: shared config, DSH credentials and token fetch."""
        cfg=self.hub.db.get('shared_qq',{})
        result={'openid_ok':bool(str(cfg.get('openid','')).strip()),'creds_ok':False,'token_ok':False,'error':''}
        if not result['openid_ok']:result['error']='shared_qq 未配置接收者 openid';return result
        module=self._transport()
        creds=module._creds(str(cfg.get('profile','qqbot')))
        if not creds:result['error']='未找到 %s 的 DSH 凭据（~/.dsh/profiles/%s/cordis.patch.yml）'%(cfg.get('profile','qqbot'),cfg.get('profile','qqbot'));return result
        result['creds_ok']=True
        try:
            module._token(creds,{'http_proxy':str(cfg.get('proxy',''))});result['token_ok']=True
        except Exception as exc:
            result['error']=f'token 获取失败：{exc}'
        return result

    def test_send(self,text='🟢 Sunday Blue 试发消息：收到即说明主动提醒链路可用'):
        cfg=self.hub.db.get('shared_qq',{})
        module=self._transport()
        creds=module._creds(str(cfg.get('profile','qqbot')))
        if not creds:raise ValueError('未找到 %s 的 DSH 凭据'%cfg.get('profile','qqbot'))
        token=module._token(creds,{'http_proxy':str(cfg.get('proxy',''))})
        ok=module._qq_send(creds,token,str(cfg.get('openid','')),text,{'http_proxy':str(cfg.get('proxy',''))})
        if not ok:raise ValueError('QQ 接口返回失败；看守护日志排查')
        return True
