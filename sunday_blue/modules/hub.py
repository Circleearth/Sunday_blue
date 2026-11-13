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
    report_open=Signal(str)
    rest_requested=Signal()
    navigate=Signal(str)
    changed=Signal(str)
    feedback=Signal(str,str)
    failed=Signal(str)
    closed=Signal()
    focus_completed=Signal(object)

    def __init__(self,config,store,parent=None,start_timer=True):
        super().__init__(parent)
        self.root,self.config,self.store=config.root,config,store
        self.db=ModuleDB(self.root);self.rewards=Rewards(self.db)
        from .planner import Planner
        from .organizer import Organizer
        self.planner=Planner(self.db);self.organizer=Organizer(self.db)
        from .work import Work
        from .life import Life
        from .duties import Duties
        self.work=Work(self.db);self.life=Life(self.db);self.duties=Duties(self.db)
        from .life_timer import LifeTimer
        self.life_timer=LifeTimer(self.db)
        from .recovery import Recovery
        self.recovery=Recovery(self.db)
        from .dida import Dida
        self.dida=Dida(self.db)
        from .focus_alarm import FocusAlarm
        self.focus_alarm=FocusAlarm(self.root,self)
        self.reminder_alarm=FocusAlarm(self.root,self)
        self.reminder_alarm.problem.connect(self.failed.emit)
        from .reminder_delivery import ReminderDelivery
        self.reminder_delivery=ReminderDelivery(self)
        self.focus_alarm.problem.connect(self.failed.emit)
        self.focus=Focus(self.db,self._focus_changed,on_complete=self._focus_completed);self.relations=Relations(self.db)
        from .learning import Learning
        from .contracts import Contracts
        from .attention import Attention
        self.learning=Learning(self.db);self.contracts=Contracts(self.db);self.attention=Attention(self.db)
        self._attention_display=None
        from .private_wellbeing import PrivateWellbeing
        from .reports import Reports
        self.private_wellbeing=PrivateWellbeing(self.db);self.reports=Reports(self)
        from .focus_dialogue import FocusDialogue
        self.focus_dialogue=FocusDialogue(self)
        self.social=Social(self.db,config,self.changed.emit);self.jobs={};self._last_event=0
        self.social.can_interrupt=lambda:self.focus.status()['state']!='running' and not self.recovery.protected()
        self.timer=QTimer(self);self.timer.setInterval(5000);self.timer.timeout.connect(self.tick)
        self.focus_timer=QTimer(self);self.focus_timer.setInterval(1000);self.focus_timer.timeout.connect(self._focus_tick)
        self.changed.connect(self._on_changed)
        if start_timer:self.timer.start();self.focus_timer.start()

    def end_work(self,minutes=60):
        state=self.focus.status()
        if state['state']!='idle':
            if state['category']!='工作':raise ValueError('请先结束当前非工作计时，再结算下班')
            self.db.set('focus_loop',{});self.focus.finish()
        previous=self.recovery.status().get('settlement_key')
        summary=self.recovery.end_work(minutes);self.changed.emit('recovery')
        if previous!=self.recovery.status().get('settlement_key'):
            from .focus_dialogue import FocusDialogue
            if not hasattr(self,'afterwork_dialogue'):
                self.afterwork_dialogue=FocusDialogue(self);self.closed.connect(self.afterwork_dialogue.close)
            director=next((s['role_id'] for s in self.duties.slots() if s['id']=='director'),None)
            if director:
                event=f"下班结算：今天记录了 {summary['minutes']} 分钟有效工作；新建任务：{', '.join(summary.get('created',[])) or '无'}；完成任务：{', '.join(summary['completed']) or '尚无确认完成的任务'}；已报告进展 {len(summary['progress'])} 项。今天的投入已经记下，接下来安心休息。"
                self.afterwork_dialogue.respond(director,'afterwork:'+self.recovery.status()['settlement_key'],event,True,guidance='这是下班恢复的回应，不是继续专注指令。具体认可真实成果，不编造成就；不派学习、运动或打卡任务，不用固定夸奖。')
        return summary

    def start_focus(self,category,label='',role_id='rui',phase='focus',duration=0,task_id=None):
        if self.focus.status()['state']!='idle':raise ValueError('已有计时正在进行')
        options=self.focus.options()
        self.db.set('focus_loop',{'category':category,'label':label,'role_id':role_id,
            'task_id':task_id,'remaining':options['max_rounds'],'enabled':options['auto_loop'] and phase=='focus'})
        return self.focus.start(category,label,role_id,phase,duration,task_id=task_id)

    def _continue_focus(self,result):
        chain=self.db.get('focus_loop',{})
        if not chain.get('enabled') or not result['completed_timer']:return
        if result['phase']=='focus':chain['remaining']-=1
        if chain['remaining']<=0:
            chain['enabled']=False;self.db.set('focus_loop',chain);return
        phase=self.focus.cycle()['next_phase'];self.db.set('focus_loop',chain)
        try:
            self.focus.start(chain['category'],chain['label'],chain['role_id'],phase,self.focus.options()[phase+'_minutes']*60,task_id=chain.get('task_id') if phase=='focus' else None)
            if phase=='focus' and chain.get('learning_unit'):self.learning.bind(self.focus.status()['id'],chain['learning_unit'])
        except Exception as exc:
            chain['enabled']=False;self.db.set('focus_loop',chain);self.failed.emit(str(exc))

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

        self._continue_focus(result)

    def _focus_changed(self,module,text=''):
        self.relations.project()
        status=self.focus.status();role=status['role_id']
        if hasattr(self,'attention') and status['state']=='running':self.attention.configure({'mode':'auto' if status['phase']=='focus' else 'rest'})
        if status['state']=='idle' and self.focus.last_settlement and self.focus.last_settlement.get('record'):
            role=self.focus.last_settlement['record']['role_id']
        if status['state']=='idle' and self.focus.last_settlement and not self.focus.last_settlement.get('completed_timer'):
            self.db.set('focus_loop',{})
        self.changed.emit(module)
        if text:
            result=self.focus.last_settlement or {}
            key=status['id'] or result.get('run_id','')
            self.focus_dialogue.respond(role,key,text,status['state']=='idle')

    def _on_changed(self,module):
        if module=='private':self._deliver_private()

    def busy_groups(self):return set(self.jobs)

    def busy_roles(self):
        roles=set()
        for gid in self.jobs:
            if gid!='dida-sync':roles.update(self.social.group(gid)['members'])
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
            self.life.state.settle();self.life.state.report_cycle()
            self.attention.tick(self.focus.status());self.contracts.tick()
            self.reports.due();self.reports.pump()
            if self.attention.new_alert==2:self.rest_requested.emit()
            a=self.attention.status();display=(round(a['eye']),round(a['focus']),a['source'])
            if display!=self._attention_display:self._attention_display=display;self.changed.emit('attention')
            self.life_timer.checkpoint()
            self.reminder_delivery.tick()
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

    def calendar_days(self,month):
        with self.db.connect() as db:return [r[0] for r in db.execute('SELECT DISTINCT day FROM activity_records WHERE day LIKE ?',(month+'%',))]

    def calendar_coins(self,day):
        with self.db.connect() as db:return db.execute("SELECT COALESCE(sum(c.amount),0) FROM coin_ledger c JOIN activity_records a ON c.reason='focus:'||a.id WHERE a.day=?",(day,)).fetchone()[0]

    def calendar_records(self,day):
        with self.db.connect() as db:return [dict(r) for r in db.execute('SELECT * FROM activity_records WHERE day=? ORDER BY started',(day,))]

    def diagnostics(self):
        with self.db.connect() as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='request_diagnostics'").fetchone():return []
            return [dict(r) for r in db.execute('SELECT * FROM request_diagnostics ORDER BY created DESC,rowid DESC LIMIT 30')]

    def close(self):
        self.timer.stop();self.focus_timer.stop();self.life_timer.pause();self.closed.emit();self.focus.pause();self.focus_alarm.stop();self.focus_dialogue.close();self.reminder_alarm.stop()
        for job in self.jobs.values():job.cancel.set()
