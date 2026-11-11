"""Shared reminders, calendar and check-ins. UI calls services only."""
from datetime import date
from PySide6.QtCore import Qt,QDate,QDateTime,QThread,Signal
from PySide6.QtGui import QTextCharFormat,QColor,QPen,QPainter
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QListWidget,QListWidgetItem,
    QPushButton,QDialog,QFormLayout,QLineEdit,QComboBox,QCheckBox,QDateTimeEdit,QMessageBox,
    QInputDialog,QCalendarWidget,QPlainTextEdit,QSplitter,QFileDialog)
from ..modules.organizer import CATEGORIES
from ..design_system import tokens

class DayCalendar(QCalendarWidget):
    def __init__(self,config):
        super().__init__();self.config=config;self.marked=set()
    def paintCell(self,painter,rect,day):
        t=tokens(self.config.value.get('ui_theme','dark'));painter.save();painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(rect,QColor(t['surface']));cell=rect.adjusted(5,4,-5,-4)
        selected=day==self.selectedDate();today=day==QDate.currentDate()
        painter.setBrush(QColor(t['accent'] if selected else t['surface']))
        painter.setPen(QPen(QColor(t['accent']),1) if today and not selected else Qt.PenStyle.NoPen)
        painter.drawRoundedRect(cell,8,8)
        painter.setPen(QColor('#ffffff' if selected else t['text'] if day.month()==self.monthShown() else t['text_subtle']))
        painter.drawText(cell,Qt.AlignmentFlag.AlignCenter,str(day.day()))
        if day.toString('yyyy-MM-dd') in self.marked:
            painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor('#ffffff' if selected else t['accent']))
            painter.drawEllipse(cell.center().x()-2,cell.bottom()-9,4,4)
        painter.restore()

class BasePage(QWidget):
    def invoke(self,fn):
        try:result=fn();self.refresh();self.hub.changed.emit('planner');return result
        except Exception as exc:QMessageBox.warning(self,'未完成',str(exc))

class RemindersPage(BasePage):
    def __init__(self,hub,parent=None):
        super().__init__(parent);self.hub=hub;layout=QVBoxLayout(self);layout.setContentsMargins(28,24,28,24)
        title=QLabel('提醒 · 给未来的自己');title.setObjectName('title');layout.addWidget(title)
        note=QLabel('共享提醒不属于任何角色。重复提醒保留每次历史；本页本机提醒需软件进程运行。');note.setWordWrap(True);layout.addWidget(note)
        self.items=QListWidget();layout.addWidget(self.items,2)
        row=QHBoxLayout()
        for name,fn in [('添加提醒',self.add),('启用 / 停用',self.toggle),('QQ 渠道',self.qq),('电脑提示音',self.sound),('刷新',self.refresh)]:
            b=QPushButton(name);b.clicked.connect(fn);row.addWidget(b)
        layout.addLayout(row);layout.addWidget(QLabel('投递历史 · 失败 / 中断可手动重试 QQ，可能存在已送达但未确认的情况'))
        self.history=QListWidget();layout.addWidget(self.history,1)
        retry=QPushButton('重试所选 QQ 投递');retry.clicked.connect(self.retry);layout.addWidget(retry)
        hub.changed.connect(lambda *_:self.refresh());self.refresh()
    def refresh(self):
        selected=self.items.currentItem();rid=selected.data(Qt.ItemDataRole.UserRole)['id'] if selected else None
        self.items.clear()
        for r in self.hub.planner.schedules()+self.hub.planner.legacy_qq():
            item=QListWidgetItem(('原 QQ 插件 · ' if r.get('legacy') else '')+f"{'启用' if r['enabled'] else '停用/结束'} · {r['title']}\n{r['next_due']} · {r['repeat']} · {'电脑 ' if r['local'] else ''}{'QQ' if r['qq'] else ''}")
            item.setData(Qt.ItemDataRole.UserRole,r);self.items.addItem(item)
            if r['id']==rid:self.items.setCurrentItem(item)
        self.history.clear()
        labels={'sent':'已发送','pending':'待发送','sending':'待确认回执','failed':'失败','off':'未启用','missed':'过期保留'}
        for r in self.hub.planner.history():
            item=QListWidgetItem(f"{r['due']} · {r['title']} · 电脑 {labels.get(r['local_status'],r['local_status'])} / QQ {labels.get(r['qq_status'],r['qq_status'])}")
            item.setData(Qt.ItemDataRole.UserRole,r);self.history.addItem(item)
    def add(self):
        dlg=QDialog(self);dlg.setWindowTitle('添加共享提醒');form=QFormLayout(dlg)
        title=QLineEdit();due=QDateTimeEdit(QDateTime.currentDateTime().addSecs(300));due.setCalendarPopup(True)
        repeat=QComboBox()
        for name,key in [('一次','once'),('每天','daily'),('每周','weekly')]:repeat.addItem(name,key)
        local=QCheckBox('电脑提示音');local.setChecked(True);qq=QCheckBox('QQ bot 提醒')
        for name,w in [('内容',title),('时间',due),('重复',repeat),('',local),('',qq)]:form.addRow(name,w)
        save=QPushButton('保存');save.clicked.connect(dlg.accept);form.addRow(save)
        if dlg.exec():self.invoke(lambda:self.hub.planner.add(title.text(),due.dateTime().toPython().astimezone().isoformat(),repeat.currentData(),local.isChecked(),qq.isChecked()))
    def toggle(self):
        item=self.items.currentItem()
        if item:
            r=item.data(Qt.ItemDataRole.UserRole)
            if r.get('legacy'):QMessageBox.information(self,'原 QQ 提醒','此条由原 QQ 插件管理，请在原插件中调整；这里仅汇总展示。');return
            self.invoke(lambda:self.hub.planner.enable(r['id'],not r['enabled']))
    def sound(self):
        from ..modules.focus_preferences import import_sound
        choice,ok=QInputDialog.getItem(self,'电脑提示音','选择提醒声音',['默认音效','选择 MP3 / WAV','试听当前声音'],0,False)
        if not ok:return
        config=self.hub.focus.options()|self.hub.db.get('reminder_sound',{'sound_enabled':True,'volume':65,'sounds':{'focus':''}})
        if choice=='试听当前声音':self.hub.reminder_alarm.play('focus',config);return
        path=''
        if choice=='选择 MP3 / WAV':
            source,_=QFileDialog.getOpenFileName(self,'选择提醒声音','','音频 (*.mp3 *.wav)')
            if not source:return
            path=self.invoke(lambda:import_sound(self.hub.root,source))
            if not path:return
        volume,ok=QInputDialog.getInt(self,'提醒音量','音量（0 静音）',config['volume'],0,100)
        if ok:self.hub.db.set('reminder_sound',{'sound_enabled':True,'volume':volume,'sounds':{'focus':path}})

    def qq(self):
        value=self.hub.db.get('shared_qq',{})
        if not value:
            # first-time setup: borrow the channel that the per-role QQ plugin already has working
            for rid,rv in (self.hub.config.value.get('roles') or {}).items():
                ps=(rv.get('plugin_settings') or {}).get('qq-reminders') or {}
                if ps.get('qq_openid'):
                    value={'profile':ps.get('dsh_profile','qqbot'),'openid':ps['qq_openid'],'proxy':ps.get('http_proxy','')}
                    break
        dlg=QDialog(self);dlg.setWindowTitle('共享 QQ 渠道');form=QFormLayout(dlg)
        profile=QLineEdit(value.get('profile','qqbot'));openid=QLineEdit(value.get('openid',''));proxy=QLineEdit(value.get('proxy',''))
        for title,w in [('现有 bot profile',profile),('接收者 openid',openid),('代理（可空）',proxy)]:form.addRow(title,w)
        form.addRow(QLabel('复用已绑定 QQ bot 凭据，不修改原插件或角色配置。'))
        status=QLabel();status.setObjectName('muted');status.setWordWrap(True);form.addRow(status)
        row=QHBoxLayout()
        def save_channel():
            self.hub.db.set('shared_qq',{'profile':profile.text().strip(),'openid':openid.text().strip(),'proxy':proxy.text().strip()})
            self.refresh();dlg.accept()
        save=QPushButton('保存');save.clicked.connect(save_channel);row.addWidget(save)
        check=QPushButton('检查连通')
        def run_check():
            st=self.hub.reminder_delivery.diagnose()
            status.setText(self._diagnose_text(st))
        check.clicked.connect(run_check)
        sendtest=QPushButton('试发一条')
        def run_test():
            sendtest.setEnabled(False);check.setEnabled(False);save.setEnabled(False)
            try:
                status.setText('正在试发一条消息到你的 QQ（需网络，约 10 秒）…')
                ok=self.invoke(lambda:self.hub.reminder_delivery.test_send())
                status.setText('试发成功：你的 QQ 应已收到一条测试消息。' if ok is not None else '试发失败，见上方提示；到点的提醒会自动挂起重试。')
            finally:
                sendtest.setEnabled(True);check.setEnabled(True);save.setEnabled(True)
        sendtest.clicked.connect(run_test)
        row.addWidget(check);row.addWidget(sendtest);row.addStretch();form.addRow(row)
        self.invoke(lambda:status.setText(self._diagnose_text(self.hub.reminder_delivery.diagnose()))) if self.hub.db.get('shared_qq') else status.setText('尚未保存共享 QQ 渠道；可点「检查连通」先看凭据与网络。')
        dlg.exec()
    def _diagnose_text(self,st):
        return ('接收者 %s · DSH 凭据 %s · 连通 %s%s')%(
            '已配置' if st['openid_ok'] else '缺失','有效' if st['creds_ok'] else '缺失',
            'OK' if st['token_ok'] else '未通过',f'（{st["error"]}）' if st['error'] else '')
    def retry(self):
        item=self.history.currentItem()
        if not item:return
        r=item.data(Qt.ItemDataRole.UserRole)
        if r['qq_status'] in ('failed','sending') and r['id'] not in self.hub.reminder_delivery.active:
            if QMessageBox.question(self,'重试 QQ','上次可能已送达但未确认，重试可能重复。继续？')==QMessageBox.StandardButton.Yes:
                self.invoke(lambda:self.hub.planner.mark(r['id'],'qq','pending'))

class CalendarPage(BasePage):
    def __init__(self,hub,parent=None):
        super().__init__(parent);self.hub=hub;layout=QVBoxLayout(self);layout.setContentsMargins(28,24,28,24)
        title=QLabel('日历 · 每一天都有迹可循');title.setObjectName('title');layout.addWidget(title)
        split=QSplitter();self.calendar=DayCalendar(hub.config);self.calendar.setGridVisible(False);self.calendar.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        split.addWidget(self.calendar);panel=QWidget();right=QVBoxLayout(panel);self.summary=QLabel();self.summary.setWordWrap(True);right.addWidget(self.summary)
        self.agenda=QListWidget();self.agenda.setWordWrap(True);right.addWidget(self.agenda);split.addWidget(panel);layout.addWidget(split,2)
        self.search=QLineEdit();self.search.setPlaceholderText('检索整理记录（留空显示所选日期）');self.search.textChanged.connect(self.refresh);layout.addWidget(self.search)
        self.records=QListWidget();self.records.setWordWrap(True);layout.addWidget(self.records,1)
        row=QHBoxLayout()
        for title,fn in [('归档当日日历',self.archive_day),('写完整日记 / 记录',self.capture),('分类目录',self.new_category),('分类并确认',self.organize),('撤销整理',self.undo)]:
            b=QPushButton(title);b.clicked.connect(fn);row.addWidget(b)
        layout.addLayout(row);self.calendar.selectionChanged.connect(self.refresh);self.calendar.currentPageChanged.connect(self.refresh);hub.changed.connect(lambda *_:self.refresh());self.refresh()
    def refresh(self,*args):
        day=self.calendar.selectedDate().toString('yyyy-MM-dd');self.agenda.clear()
        t=tokens(self.hub.config.value.get('ui_theme','dark'))
        self.calendar.setStyleSheet(f"QCalendarWidget QWidget {{background:{t['surface']};color:{t['text']};}} QCalendarWidget QToolButton {{background:{t['surface_raised']};color:{t['text']};padding:8px;}} QCalendarWidget QAbstractItemView {{selection-background-color:{t['accent']};selection-color:white;}}")
        self.calendar.setDateTextFormat(QDate(),QTextCharFormat())
        mark=QTextCharFormat();mark.setBackground(QColor(t['accent_soft']));mark.setForeground(QColor(t['text']))
        month=f'{self.calendar.yearShown():04d}-{self.calendar.monthShown():02d}'
        self.calendar.marked=set(self.hub.calendar_days(month));self.calendar.updateCells()
        rows=self.hub.calendar_records(day)
        seconds=sum(r['seconds'] for r in rows);checks=self.hub.planner.checkins(day)
        self.summary.setText(f"{day}\n有效专注 {seconds/3600:.1f} 小时 · 完成 {sum(r['done'] for r in checks)} / {len(checks)} 个打卡 · 当日 +{self.hub.calendar_coins(day)} 金币")
        for r in rows:self.agenda.addItem(f"专注 · {r['category']} · {r['seconds']/60:.0f} 分钟 · {r['label']}")
        for r in self.hub.planner.history(day):self.agenda.addItem('提醒 · '+r['title'])
        for r in self.hub.planner.on_day(day):self.agenda.addItem('待提醒 · '+r['title'])
        for r in self.hub.dida.tasks():
            if r['due'][:10]==day:self.agenda.addItem('滴答 · '+r['title'])
        for r in checks:self.agenda.addItem(('已打卡 · ' if r['done'] else '未记录 · ')+r['title'])
        if not self.agenda.count():self.agenda.addItem('这一天还没有活动记录；未记录不代表未完成。')
        self.records.clear()
        for r in self.hub.organizer.search(self.search.text(),None if self.search.text() else day):
            item=QListWidgetItem(f"{r['category']} · {r['title']} · {r['status']}\n{r['body'][:500]}");item.setData(Qt.ItemDataRole.UserRole,r);self.records.addItem(item)
    def archive_day(self):
        import json
        day=self.calendar.selectedDate().toString('yyyy-MM-dd')
        payload={'date':day,'focus':self.hub.calendar_records(day),'reminders':self.hub.planner.history(day),
            'checkins':self.hub.planner.checkins(day),'dida':[r for r in self.hub.dida.tasks() if r['due'][:10]==day]}
        self.invoke(lambda:self.hub.organizer.capture(day+'｜完整日历记录',json.dumps(payload,ensure_ascii=False,indent=2),'日记完整记录',day,'calendar',True))

    def capture(self):
        title,ok=QInputDialog.getText(self,'完整日记 / 记录','标题（日期、主题、相关项目）：')
        if not ok:return
        body,ok=QInputDialog.getMultiLineText(self,'完整记录','完整内容：')
        if ok:self.invoke(lambda:self.hub.organizer.capture(title,body,'日记完整记录',self.calendar.selectedDate().toString('yyyy-MM-dd'),confirmed=True))
    def new_category(self):
        title,ok=QInputDialog.getText(self,'新建可复用分类','先复用已有分类；确需新增时，填写稳定且边界明确的名称：')
        if ok:self.invoke(lambda:self.hub.organizer.add_category(title))

    def organize(self):
        item=self.records.currentItem()
        if not item:return
        r=item.data(Qt.ItemDataRole.UserRole);category,ok=QInputDialog.getItem(self,'分类并确认','选择分类；不明确时保留收件箱',self.hub.organizer.categories(),0,False)
        if ok:self.invoke(lambda:self.hub.organizer.organize(r['id'],category,confirm=True))
    def undo(self):
        item=self.records.currentItem()
        if item:self.invoke(lambda:self.hub.organizer.undo(item.data(Qt.ItemDataRole.UserRole)['id']))

class SyncJob(QThread):
    outcome=Signal(str)
    def __init__(self,service,parent,task=None):super().__init__(parent);self.service=service;self.task=task
    def run(self):
        try:
            if self.task:
                message=self.service.complete(self.task['id'],self.task['due'],self.task.get('etag') or '')
                try:self.service.sync()
                except Exception:message+=' 列表刷新未成功，稍后可手动同步。'
                self.outcome.emit(message)
            else:self.outcome.emit(f'同步完成：{self.service.sync()} 条，历史记录已保留。')
        except Exception as exc:self.outcome.emit(str(exc) if isinstance(exc,ValueError) else '同步失败：'+type(exc).__name__)

class CheckinsPage(BasePage):
    def __init__(self,hub,parent=None):
        from PySide6.QtWidgets import QTabWidget
        super().__init__(parent);self.hub=hub;self.job=None
        layout=QVBoxLayout(self);layout.setContentsMargins(28,24,28,24);layout.setSpacing(14)
        title=QLabel('把今天的事情，一件件完成。');title.setObjectName('title');layout.addWidget(title)
        tabs=QTabWidget();layout.addWidget(tabs)
        remote_page=QWidget();remote_layout=QVBoxLayout(remote_page);tabs.addTab(remote_page,'滴答清单')
        note=QLabel('勾选任务即同步完成到滴答清单。循环任务只完成当前一期；不支持在这里撤销完成或删除。')
        note.setWordWrap(True);note.setObjectName('muted');remote_layout.addWidget(note)
        row=QHBoxLayout();self.query=QLineEdit();self.query.setPlaceholderText('搜索任务或清单…');row.addWidget(self.query,1)
        self.scope=QComboBox()
        for label,key in [('未完成','open'),('今天 / 逾期','today'),('已完成','done'),('全部缓存','all')]:self.scope.addItem(label,key)
        row.addWidget(self.scope);self.projects=QComboBox();self.projects.addItem('全部清单','');row.addWidget(self.projects);remote_layout.addLayout(row)
        self.summary=QLabel();remote_layout.addWidget(self.summary)
        self.remote=QListWidget();self.remote.setWordWrap(True);remote_layout.addWidget(self.remote,1)
        self.sync_status=QLabel('点击同步读取滴答清单。');self.sync_status.setWordWrap(True);remote_layout.addWidget(self.sync_status)
        buttons=QHBoxLayout();self.auth_button=QPushButton('配置 API 口令');self.auth_button.clicked.connect(self.auth);buttons.addWidget(self.auth_button)
        self.sync_button=QPushButton('同步滴答清单');self.sync_button.setObjectName('primary');self.sync_button.clicked.connect(self.sync);buttons.addWidget(self.sync_button)
        remote_layout.addLayout(buttons)
        local_page=QWidget();local_layout=QVBoxLayout(local_page);tabs.addTab(local_page,'本地打卡')
        local_layout.addWidget(QLabel('这里的打卡保存在 Sunday_Blue，不会创建滴答任务。'))
        self.items=QListWidget();local_layout.addWidget(self.items)
        for title,fn in [('添加打卡',self.add),('确认今天已完成',self.check)]:
            button=QPushButton(title);button.clicked.connect(fn);local_layout.addWidget(button)
        self.remote.itemChanged.connect(self.complete_checked)
        self.query.textChanged.connect(self.refresh);self.scope.currentIndexChanged.connect(self.refresh);self.projects.currentIndexChanged.connect(self.refresh)
        hub.changed.connect(lambda *_:self.refresh());self.refresh()
    def auth(self):
        token,ok=QInputDialog.getText(self,'官方滴答授权','API 口令（dp_ 开头，本机加密保存）：',QLineEdit.EchoMode.Password)
        if ok:self.invoke(lambda:self.hub.dida.configure_api(token))
    def complete_checked(self,item):
        if self.job or item.checkState()!=Qt.CheckState.Checked:return
        task=item.data(Qt.ItemDataRole.UserRole)
        if not task or task['status']==2:return
        # Display success only after an authoritative result, not on the initial click.
        self.remote.blockSignals(True);item.setCheckState(Qt.CheckState.Unchecked);self.remote.blockSignals(False)
        self.run_job(task)
    def sync(self):self.run_job()
    def run_job(self,task=None):
        if self.job:return
        self.job=SyncJob(self.hub.dida,self,task);self.sync_button.setEnabled(False);self.auth_button.setEnabled(False);self.remote.setEnabled(False)
        self.sync_status.setText('正在同步完成到滴答…' if task else '正在同步滴答清单…')
        self.job.outcome.connect(self.sync_status.setText)
        def finished():
            job=self.job;self.job=None;self.hub.jobs.pop('dida-sync',None);job.deleteLater()
            self.sync_button.setEnabled(True);self.auth_button.setEnabled(True);self.remote.setEnabled(True);self.refresh();self.hub.changed.emit('planner')
        self.job.finished.connect(finished);self.hub.jobs['dida-sync']=self.job
        self.job.cancel=__import__('threading').Event();self.job.start()
    def refresh(self,*args):
        from datetime import date,datetime
        rows=self.hub.dida.tasks();projects=sorted({r['project'] for r in rows})
        if [self.projects.itemData(i) for i in range(1,self.projects.count())]!=projects:
            selected=self.projects.currentData();self.projects.blockSignals(True);self.projects.clear();self.projects.addItem('全部清单','')
            for name in projects:self.projects.addItem(name,name)
            self.projects.setCurrentIndex(max(0,self.projects.findData(selected)));self.projects.blockSignals(False)
        query=self.query.text().strip().casefold();scope=self.scope.currentData();project=self.projects.currentData();today=date.today().isoformat()
        self.remote.blockSignals(True);position=self.remote.verticalScrollBar().value();self.remote.clear();shown=0
        for r in rows:
            done=r['status']==2
            if scope=='open' and r['status'] not in (0,1) or scope=='done' and not done:continue
            if scope=='today' and (done or not r['due'] or r['due'][:10]>today):continue
            if project and r['project']!=project:continue
            if query and query not in (r['title']+' '+r['project']).casefold():continue
            due=r['due'][:10] or '未设日期';recurrence=' · 循环任务' if r['repeat'] else ''
            item=QListWidgetItem(f"{r['title']}\n{r['project']} · {due}{recurrence}");item.setData(Qt.ItemDataRole.UserRole,r)
            item.setToolTip(f"{r['title']}\n{r['due']}\n{'已完成' if done else '勾选后同步完成到滴答'}")
            writable=self.hub.dida.official_enabled() and r.get('project_id') and r.get('kind')!='NOTE'
            item.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable|(Qt.ItemFlag.ItemIsUserCheckable if writable and r['status'] in (0,1) else Qt.ItemFlag.NoItemFlags))
            item.setCheckState(Qt.CheckState.Checked if done else Qt.CheckState.Unchecked);self.remote.addItem(item);shown+=1
        self.remote.verticalScrollBar().setValue(position);self.remote.blockSignals(False)
        self.summary.setText(f"显示 {shown} 项 · 未完成 {sum(r['status'] in (0,1) for r in rows)} 项 · 最近同步 {self.hub.db.get('dida_last_sync','尚未同步')}")
        self.items.clear()
        for r in self.hub.planner.checkins():
            item=QListWidgetItem(('✓ 已完成  ' if r['done'] else '○ 未记录  ')+r['title']);item.setData(Qt.ItemDataRole.UserRole,r);self.items.addItem(item)
    def add(self):
        title,ok=QInputDialog.getText(self,'新打卡','项目名称：')
        if ok:self.invoke(lambda:self.hub.planner.add_checkin(title))
    def check(self):
        item=self.items.currentItem()
        if item:self.invoke(lambda:self.hub.planner.check(item.data(Qt.ItemDataRole.UserRole)['id']))
