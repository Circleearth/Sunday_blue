"""Shared notification channels, reusing QQ transport without changing its daemon."""
import importlib.util
import re
import threading
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
