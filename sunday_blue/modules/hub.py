"""Qt orchestration only. Domain services own data; this owns timers and jobs."""
import json
import threading
from PySide6.QtCore import QObject,QThread,QTimer,Signal
from .database import ModuleDB,stamp
from .rewards import Rewards
from .focus import Focus
from .relations import Relations
from .social import Social
from ..roles import list_roles


class SocialJob(QThread):
    error=Signal(str)
    def __init__(self,action,parent=None):
        super().__init__(parent);self.cancel=threading.Event();self.action=action
    def run(self):
        try:self.action(self.cancel)
        except Exception as exc:
            if not self.cancel.is_set():self.error.emit(str(exc))


class ModuleHub(QObject):
    changed=Signal(str)
    feedback=Signal(str,str)
    failed=Signal(str)
    closed=Signal()
    focus_completed=Signal(object)

    def __init__(self,config,store,parent=None,start_timer=True):
        super().__init__(parent)
        self.root,self.config,self.store=config.root,config,store
        self.db=ModuleDB(self.root);self.rewards=Rewards(self.db)
        from .focus_alarm import FocusAlarm
        self.focus_alarm=FocusAlarm(self.root,self)
        self.focus_alarm.problem.connect(self.failed.emit)
        self.focus=Focus(self.db,self._focus_changed,on_complete=self._focus_completed);self.relations=Relations(self.db)
        self.social=Social(self.db,config,self.changed.emit);self.jobs={};self._last_event=0
        self.social.can_interrupt=lambda:self.focus.status()['state']!='running'
        self.timer=QTimer(self);self.timer.setInterval(5000);self.timer.timeout.connect(self.tick)
        self.focus_timer=QTimer(self);self.focus_timer.setInterval(1000);self.focus_timer.timeout.connect(self._focus_tick)
        self.changed.connect(self._on_changed)
        if start_timer:self.timer.start();self.focus_timer.start()

    def _focus_tick(self):
        try:self.focus.checkpoint()
        except Exception as exc:self.failed.emit(str(exc))

    def _focus_completed(self,result):
        from PySide6.QtWidgets import QApplication,QWidget
        from .focus_preferences import PHASES
        self.focus_alarm.play(result['phase'],self.focus.options())
        self.focus_completed.emit(result)
        parent=self.parent()
        if isinstance(parent,QWidget):
            QApplication.alert(parent,5000)
            icon=getattr(getattr(parent,'tray',None),'icon',None)
            if icon and icon.isVisible():icon.showMessage('番茄钟 · '+PHASES[result['phase']]+'结束',result['feedback'])

    def _focus_changed(self,module,text=''):
        self.relations.project()
        status=self.focus.status();role=status['role_id']
        if status['state']=='idle' and self.focus.last_settlement and self.focus.last_settlement.get('record'):
            role=self.focus.last_settlement['record']['role_id']
        self.changed.emit(module)
        if text:self.feedback.emit(role,text)

    def _on_changed(self,module):
        if module=='private':self._deliver_private()

    def busy_groups(self):return set(self.jobs)

    def busy_roles(self):
        roles=set()
        for gid in self.jobs:roles.update(self.social.group(gid)['members'])
        status=self.focus.status()
        if status['state']=='running':roles.add(status['role_id'])
        return roles

    def _launch(self,gid,action):
        if gid in self.jobs:raise ValueError('这个群正在回复，请稍候或停止当前回复。')
        job=SocialJob(action,self);self.jobs[gid]=job
        job.error.connect(self.failed.emit)
        def finished():
            self.jobs.pop(gid,None);self.changed.emit('social');self._deliver_private();job.deleteLater()
        job.finished.connect(finished);job.start();self.changed.emit('social')

    def send_group(self,gid,text):
        if gid in self.jobs:raise ValueError('群聊正在回复')
        mid=self.social.post(gid,text)
        self._launch(gid,lambda cancel:self.social.generate(gid,mid,cancel))

    def summarize_group(self,gid):self._launch(gid,lambda cancel:self.social.summarize(gid,cancel))

    def retry_group(self,gid):
        messages=[m for m in self.social.messages(gid) if m['kind'] in ('user','event')]
        if not messages:raise ValueError('还没有可以继续的话题。')
        self._launch(gid,lambda cancel:self.social.generate(gid,messages[-1]['id'],cancel))

    def cancel_group(self,gid):
        if gid in self.jobs:self.jobs[gid].cancel.set()

    def tick(self):
        try:
            self.focus.checkpoint();self.relations.project();self.social.sync_memories();self._deliver_private();self._plugin_events()
            with self.db.connect() as db:seq=db.execute('SELECT COALESCE(max(seq),0) FROM module_events').fetchone()[0]
            if seq!=self._last_event:self._last_event=seq;self.changed.emit('modules')
            if not self.jobs:
                followup=self.social.followup_candidate()
                candidate=None if followup else self.social.proactive_candidate(self.focus.status()['state']=='running')
                if followup:
                    self._launch(followup['group_id'],lambda cancel:self.social.followup(followup,cancel))
                elif candidate:
                    gid,trigger=candidate;self._launch(gid,lambda cancel:self.social.generate(gid,trigger,cancel))
        except Exception as exc:
            # Keep local clocks/records usable if an optional social component fails.
            self.failed.emit(str(exc))

    def _plugin_events(self):
        from ..plugin_runtime import discover,load
        from ..native_plugins import enabled
        config=self.config.snapshot()
        for event in self.db.events('plugin-feedback'):
            role=event['payload'].get('role_id')
            if role:
                for pid,meta in discover(self.root).items():
                    if meta.get('error') or not enabled(config,role,pid,meta):continue
                    try:
                        callback=getattr(load(pid,self.root),'on_module_event',None)
                        text=callback(self.root,config,role,event) if callback else None
                        if isinstance(text,str) and text.strip():self.feedback.emit(role,text[:1000])
                    except Exception as exc:self.failed.emit(f'模块插件 {pid} 反馈失败：{type(exc).__name__}；现实记录仍已保存。')
            with self.db.connect() as db:self.db.receipt(db,'plugin-feedback',event['event_key'])

    def _deliver_private(self):
        active={r[0] for r in list_roles(self.root)}
        with self.db.connect() as db:pending=[dict(r) for r in db.execute('SELECT * FROM private_followups WHERE delivered=0')]
        for item in pending:
            role=item['role']
            if role not in active:continue
            key='episode-followup:'+str(item['episode'])
            # Durable cross-database idempotency: chat insert + link commit together,
            # then mark the source outbox delivered. A crash between them is safe.
            with self.store.connect() as db:
                db.execute('CREATE TABLE IF NOT EXISTS module_message_links(source_key TEXT PRIMARY KEY,session TEXT,message INTEGER)')
                prior=db.execute('SELECT session FROM module_message_links WHERE source_key=?',(key,)).fetchone()
            if not prior:
                sessions=self.store.sessions(role)
                sid=sessions[0]['id'] if sessions else self.store.create(role,'会议后的关心')
                with self.store.connect() as db:
                    db.execute('BEGIN IMMEDIATE')
                    if not db.execute('SELECT 1 FROM module_message_links WHERE source_key=?',(key,)).fetchone():
                        cur=db.execute('INSERT INTO messages(session,role,content,created) VALUES(?,?,?,?)',(sid,'assistant',json.dumps(item['content'],ensure_ascii=False),stamp()))
                        db.execute('INSERT INTO module_message_links VALUES(?,?,?)',(key,sid,cur.lastrowid))
                        db.execute('UPDATE sessions SET updated=? WHERE id=?',(stamp(),sid))
            with self.db.connect() as db:db.execute('UPDATE private_followups SET delivered=1 WHERE episode=?',(item['episode'],))
            self.feedback.emit(role,'有一条会议后的关心，已放到私聊。')

    def diagnostics(self):
        with self.db.connect() as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='request_diagnostics'").fetchone():return []
            return [dict(r) for r in db.execute('SELECT * FROM request_diagnostics ORDER BY created DESC,rowid DESC LIMIT 30')]

    def close(self):
        self.timer.stop();self.focus_timer.stop();self.closed.emit();self.focus.pause();self.focus_alarm.stop()
        for job in self.jobs.values():job.cancel.set()
