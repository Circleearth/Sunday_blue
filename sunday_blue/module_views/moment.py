"""Current plan, continuation and transitions across existing desktop modules."""
from datetime import datetime
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QCheckBox,QComboBox,QDialog,QDialogButtonBox,QHBoxLayout,QInputDialog,
    QLabel,QMessageBox,QPlainTextEdit,QPushButton,QVBoxLayout,QWidget)
from ..modules.day_plan import current_plan
from .module_forms import button

class MomentPage(QWidget):
    def __init__(self,hub,parent=None):
        super().__init__(parent)
        self.hub=hub
        self.window_owner=parent
        box=QVBoxLayout(self)
        box.setContentsMargins(28,22,28,22)
        self.title=QLabel('此刻')
        self.title.setObjectName('title')
        box.addWidget(self.title)
        self.companion=QLabel()
        self.companion.setWordWrap(True)
        box.addWidget(self.companion)
        hub.feedback.connect(self.role_message)
        self.primary=button('开始',self.primary_action,box,True)
        self.plan=QLabel()
        self.state=QLabel()
        self.next=QLabel()
        for label in (self.plan,self.state,self.next):
            label.setWordWrap(True)
            box.addWidget(label)
        row=QHBoxLayout()
        box.addLayout(row)
        button('继续工作',lambda:self.launch('工作'),row,True)
        button('从学习断点开始',lambda:self.launch('学习'),row)
        button('学习卡住了',self.help_study,row)
        row=QHBoxLayout()
        box.addLayout(row)
        button('留下接续笔记',self.note,row)
        button('下班结算与休息',self.afterwork,row)
        button('校对当前感受',self.calibrate,row)
        self.office=QCheckBox('办公模式 · 隐藏生活插图')
        box.addWidget(self.office)
        from ..modules.phone_link import PhoneLink
        self.phone=PhoneLink(hub.db)
        hub.closed.connect(self.phone.stop)
        button('手机亮屏提醒 · 局域网连接',self.pair_phone,box)
        if hub.db.get('phone_enabled',False):
            try:self.phone.start()
            except (OSError,ValueError):pass
        self.office.setChecked(hub.db.get('office_mode',False))
        self.office.toggled.connect(self.office_mode)
        box.addStretch()
        self.timer=QTimer(self)
        self.timer.setInterval(30000)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        hub.closed.connect(self.timer.stop)
        self.audio_error=''
        hub.closed.connect(self.release_audio)
        self.refresh()

    def pair_phone(self):
        dlg=QDialog(self)
        dlg.setWindowTitle('SundayMobile 配对')
        box=QVBoxLayout(dlg)
        text=QPlainTextEdit()
        text.setReadOnly(True)
        box.addWidget(text)
        def enable():
            try:address=self.phone.start()
            except (OSError,ValueError) as exc:text.setPlainText(str(exc));return
            self.hub.db.set('phone_enabled',True)
            text.setPlainText(address+'\n'+self.hub.db.get('phone_token',''))
        def disable():
            self.phone.stop()
            self.hub.db.set('phone_enabled',False)
            text.setPlainText('连接已关闭。')
        button('启用并显示地址与配对码',enable,box)
        button('关闭手机连接',disable,box)
        if self.phone.server:enable()
        else:text.setPlainText('手机与电脑接入同一 Wi-Fi，在手机端填写地址和配对码。')
        dlg.exec()

    def role_message(self,role,text):
        from ..roles import list_roles
        names={r[0]:r[1] for r in list_roles(self.hub.root)}
        line=names.get(role,role)+'  ·  '+text
        self.companion.setText(line)
        if self.window_owner and hasattr(self.window_owner,'footer'):
            from PySide6.QtCore import Qt
            footer=self.window_owner.footer
            footer.setToolTip(line)
            footer.setText(footer.fontMetrics().elidedText(line,Qt.TextElideMode.ElideRight,440))

    def life_event(self):
        from ..modules.database import day
        h=self.hub
        if h.focus.status()['state']!='idle' or h.recovery.status()['active']:return
        with h.db.connect() as c:
            r=c.execute("SELECT kind,payload,event_key FROM module_events WHERE kind IN ('exercise.recorded','focus.completed') AND julianday(created)>=julianday('now','-30 minutes') ORDER BY seq DESC LIMIT 1").fetchone()
        if not r:return
        import json
        data=json.loads(r['payload'])
        if data.get('day')!=day():return
        if r['kind']=='exercise.recorded':
            slot='exercise'
            event=f"今天上报了{data.get('kind','运动')} {data.get('minutes',0)}分钟。"
        elif data.get('category')=='学习':
            slot='study'
            event=f"刚完成学习「{data.get('label','')}」，有效时间 {round(data.get('seconds',0)/60)} 分钟。"
        else:return
        key='quiet_followup:'+slot
        role=next((s['role_id'] for s in h.duties.slots() if s['id']==slot),None)
        if not role or h.db.get(key,'')==day():return
        h.db.set(key,day())
        h.focus_dialogue.respond(role,r['event_key'],event,True,guidance='根据事实，简短自然，不派任务。')

    def office_mode(self,on):
        from ..image_layouts import set_office_mode
        self.hub.db.set('office_mode',on)
        set_office_mode(self.hub.root,on)

    def showEvent(self,event):
        super().showEvent(event)
        self.refresh()

    def refresh(self):
        now=datetime.now()
        self.plan.setText(now.strftime('%m 月 %d 日   %H:%M')+'     '+current_plan(self.hub.db,now))
        current=current_plan(self.hub.db,now)
        in_focus=self.hub.focus.status()['state']!='idle'
        if in_focus:self.intent='focus'
        elif self.hub.recovery.status()['active']:self.intent='rest'
        elif any(k in current for k in ('学习','CPA','练习','复现')):self.intent='study'
        elif any(k in current for k in ('力量','有氧','运动','步行')):self.intent='exercise'
        elif now.weekday()<5 and 8<=now.hour<18 and current=='自由安排':self.intent='work'
        else:self.intent='plan'
        self.primary.setText({'work':'接上手头工作','study':'先学五分钟','rest':'进入安静休息','exercise':'打开运动记录','focus':'回到正在进行的专注','plan':'打开今天的安排'}[self.intent])
        a=self.hub.attention.status()
        active=self.hub.focus.status()
        self.state.setText(f"视疲劳估计 {a['eye']:.0f}%   ·   专注 {a['focus']:.0f}   ·   {a['source']}"+('   ·   '+active.get('label','') if active['state']!='idle' else ''))
        note=self.hub.db.get('continue_note','') or self.hub.work.day_note()
        work=self.hub.work.suggest()
        previous=self.hub.db.get('last_start:工作',{}).get('task_id')
        task=next((r for r in work if r['id']==previous),work[0] if work else None)
        hint=task['title'] if task else '选择一项轻松的小事'
        if self.intent=='study':
            uid=self.hub.db.get('last_study_unit','')
            unit=next((r for r in self.hub.learning.notebook_rows() if r['id']==uid),None)
            if unit:hint=unit['title']+(' · '+unit['questions'][:100] if unit.get('questions') else '')
        self.next.setText('接下来   '+(note or hint)+('\n系统静音未生效：'+self.audio_error if self.audio_error else ''))

    def note(self):
        text,ok=QInputDialog.getMultiLineText(self,'接续笔记','下一步做什么？可附题号、资料或卡住的地方。',self.hub.db.get('continue_note',''))
        if ok:self.hub.db.set('continue_note',text.strip());self.refresh()

    def primary_action(self):
        if self.intent=='study':self.launch('学习',300)
        elif self.intent=='work':self.launch('工作')
        elif self.intent=='rest':self.rest(5)
        else:self.hub.navigate.emit({'focus':'focus','plan':'plan','exercise':'exercise'}[self.intent])

    def launch(self,category,duration=None):
        h=self.hub
        if h.focus.status()['state']!='idle':h.navigate.emit('focus');return
        last=h.db.get('last_start:'+category,{})
        role=next((s['role_id'] for s in h.duties.slots() if s['id']==('study' if category=='学习' else 'director') and s['role_id']),None)
        if not role:h.navigate.emit('growth' if category=='学习' else 'work');return
        try:
            if category=='工作':
                rows=h.work.suggest()
                if not rows:h.navigate.emit('work');return
                task=next((r for r in rows if r['id']==last.get('task_id')),rows[0])
                h.start_focus(category,task['title'],role,duration=h.focus.options()['focus_minutes']*60,task_id=task['id'])
            else:
                units=[r for r in h.learning.notebook_rows() if r['kind']=='unit']
                if not units:h.navigate.emit('growth');return
                unit=next((r for r in units if r['id']==h.db.get('last_study_unit','')),units[0])
                h.start_focus(category,unit['title'],role,duration=duration or h.focus.options()['focus_minutes']*60)
                h.learning.bind(h.focus.status()['id'],unit['id'])
                h.db.set('focus_loop',h.db.get('focus_loop',{})|{'learning_unit':unit['id']})
            h.navigate.emit('focus')
        except ValueError as exc:QMessageBox.information(self,'启动专注',str(exc))

    def help_study(self):
        choice,ok=QInputDialog.getItem(self,'调整学习节奏','此刻更适合哪一种？',['留下断点，短暂休息','把目标缩成一道题','回到知识点换一题'],0,False)
        if not ok:return
        if choice.startswith('留下'):
            self.note()
            run=self.hub.focus.status()
            if run['state']=='running' and run['category']=='学习':self.hub.focus.pause()
            self.rest(3)
        elif choice.startswith('把'):
            self.hub.db.set('continue_note','只做一道题，写下第一步。');self.refresh()
            QMessageBox.information(self,'下一步','先读一道题，只写下第一步。完成后再决定是否继续。')
        else:self.hub.navigate.emit('growth')

    def calibrate(self):
        dlg=QDialog(self)
        dlg.setWindowTitle('核对状态估计')
        box=QVBoxLayout(dlg)
        a=self.hub.attention.status()
        box.addWidget(QLabel(f"当前估计　视疲劳 {a['eye']:.0f}%　专注 {a['focus']:.0f}"))
        eyes=QComboBox();eyes.addItems(['眼睛感觉 · 跳过','轻松','有些累','很累'])
        focus=QComboBox();focus.addItems(['专注感觉 · 跳过','容易投入','一般','难以集中'])
        mode=QComboBox()
        from ..modules.attention import MODES
        for key,title in MODES.items():mode.addItem(title,key)
        mode.setCurrentIndex(mode.findData(a['mode']))
        for field in (eyes,focus,mode):box.addWidget(field)
        with self.hub.db.connect() as c:
            c.execute('CREATE TABLE IF NOT EXISTS attention_observations(at TEXT PRIMARY KEY,eyes TEXT,concentration TEXT,estimated_eye REAL,estimated_focus REAL)')
            history=c.execute('SELECT * FROM attention_observations ORDER BY at DESC LIMIT 4').fetchall()
        for r in history:
            box.addWidget(QLabel(f"{r['at'][:16]}　眼 {r['estimated_eye']:.0f} / {r['eyes'] or '未评'}　专注 {r['estimated_focus']:.0f} / {r['concentration'] or '未评'}"))
        button('保存',dlg.accept,box)
        if dlg.exec():
            if eyes.currentIndex() or focus.currentIndex():
                with self.hub.db.connect() as c:
                    c.execute('INSERT INTO attention_observations VALUES(?,?,?,?,?)',(datetime.now().isoformat(),eyes.currentText() if eyes.currentIndex() else '',focus.currentText() if focus.currentIndex() else '',a['eye'],a['focus']))
            self.hub.attention.configure({'mode':mode.currentData()})
            self.refresh()

    def afterwork(self):
        try:summary=self.hub.end_work(30)
        except ValueError as exc:QMessageBox.information(self,'工作结算',str(exc));return
        a=self.hub.attention.status()
        minutes=10 if a['eye']>=60 or a['focus']<35 else 5
        accomplishments='、'.join(summary['completed'][:3])
        if not accomplishments and summary.get('created'):
            accomplishments='新建了'+ '、'.join(summary['created'][:3])
        text=f"投入 {summary['minutes']} 分钟，完成 {len(summary['completed'])} 项，记录 {len(summary['progress'])} 项进展。"
        if accomplishments:text+='\n'+accomplishments
        answer=QMessageBox.question(self,'今天的工作已记下',text+f"\n进入 {minutes} 分钟离屏休息？")
        if answer==QMessageBox.StandardButton.Yes:self.rest(minutes)

    def rest(self,minutes):
        from time import monotonic
        h=self.hub
        previous=h.attention.options()['mode']
        h.attention.configure({'mode':'rest'})
        dlg=QDialog(self)
        dlg.setWindowTitle('离屏休息')
        box=QVBoxLayout(dlg)
        label=QLabel()
        box.addWidget(label)
        button('提前回来',dlg.reject,box)
        end=monotonic()+minutes*60
        def update():
            seconds=max(0,round(end-monotonic()))
            label.setText(f'暂时放下手里的事   {seconds//60:02}:{seconds%60:02}')
            if not seconds:dlg.accept()
        timer=QTimer(dlg);timer.timeout.connect(update);timer.start(500);update()
        finished=dlg.exec()
        h.attention.configure({'mode':previous})
        with h.db.connect() as c:
            key='rest-return:'+datetime.now().isoformat()
            h.db.emit(c,key,'rest.returned',{'early':not bool(finished),'minutes':minutes,'remaining':max(0,round(end-monotonic()))})
        self.refresh()

    def release_audio(self):
        from ..modules.work_audio import release
        try:release(self.hub.db)
        except (OSError,ImportError,AttributeError):pass

    def tick(self):
        now=datetime.now()
        import sys
        if sys.platform=='win32':
            from ..modules.work_audio import synchronize
            try:
                synchronize(self.hub.db,now)
                self.audio_error=''
            except (OSError,ImportError,AttributeError) as exc:self.audio_error=str(exc)
        if self.isVisible():self.refresh()
        if 9<=now.hour<22:self.life_event()
        if now.weekday()>=5:return
        if 18<=now.hour<21 and self.hub.db.get('evening_offer','')!=now.date().isoformat():
            with self.hub.db.connect() as c:
                worked=c.execute("SELECT 1 FROM activity_records WHERE category='工作' AND day=? LIMIT 1",(now.date().isoformat(),)).fetchone()
            run=self.hub.focus.status()
            working=run['state']!='idle' and run['category']=='工作'
            if (worked or working) and not self.hub.recovery.status()['active'] and (working or run['state']=='idle'):
                self.hub.db.set('evening_offer',now.date().isoformat())
                self.evening=QMessageBox(QMessageBox.Icon.Information,'下班后',('结束当前工作计时，结算并安排休息？' if working else '今天的工作已有记录。现在结算并安排休息？'),QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,self.window_owner)
                self.evening.finished.connect(lambda result:self.afterwork() if result==QMessageBox.StandardButton.Yes else None)
                self.evening.open()
        if now.hour!=17 or now.minute<55:return
        key='wrap_prompt_day'
        if self.hub.db.get(key,'')==now.date().isoformat():return
        self.hub.db.set(key,now.date().isoformat())
        dlg=QDialog(self.window_owner)
        dlg.setWindowTitle('下班前五分钟')
        box=QVBoxLayout(dlg)
        box.addWidget(QLabel('给下一次开始留一句话'))
        draft=QPlainTextEdit(self.hub.db.get('continue_note',''))
        box.addWidget(draft)
        draft.textChanged.connect(lambda:self.hub.db.set('continue_note',draft.toPlainText()))
        button('记好了',dlg.accept,box)
        dlg.finished.connect(lambda result:self.wrap_float() if not result else None)
        dlg.show()
        self.wrap_dialog=dlg
        QTimer.singleShot(300000,dlg,lambda:dlg.reject() if dlg.isVisible() else None)

    def wrap_float(self):
        ball=QPushButton('✎  收尾笔记',None)
        ball.setWindowFlags(Qt.WindowType.Tool|Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.FramelessWindowHint)
        bounds=self.screen().availableGeometry()
        ball.adjustSize();ball.move(bounds.right()-ball.width()-16,bounds.bottom()-ball.height()-16)
        ball.clicked.connect(lambda:(ball.close(),self.note()))
        self.hub.closed.connect(ball.close)
        ball.show()
        QTimer.singleShot(600000,ball.close)
        self.float_button=ball
