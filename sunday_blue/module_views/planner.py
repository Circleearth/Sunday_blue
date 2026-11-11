"""Shared reminders, calendar and check-ins. UI calls services only."""
from datetime import date
from PySide6.QtCore import Qt,QDate,QDateTime,QThread,Signal
from PySide6.QtGui import QTextCharFormat,QColor,QPen,QPainter
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QListWidget,QListWidgetItem,
    QPushButton,QDialog,QFormLayout,QLineEdit,QComboBox,QCheckBox,QDateTimeEdit,QMessageBox,
    QInputDialog,QCalendarWidget,QPlainTextEdit,QSplitter)
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
        from PySide6.QtWidgets import QTabWidget
        super().__init__(parent);self.hub=hub;layout=QVBoxLayout(self);layout.setContentsMargins(28,24,28,24);layout.setSpacing(16)
        header=QHBoxLayout();title=QLabel('提醒');title.setObjectName('title');header.addWidget(title);header.addStretch()
        settings=QPushButton('提醒设置');settings.clicked.connect(self.qq);header.addWidget(settings)
        add=QPushButton('新建提醒');add.setObjectName('primary');add.clicked.connect(self.add);header.addWidget(add);layout.addLayout(header)
        note=QLabel('把要记得的事留在这里。电脑和 QQ 按所选渠道提醒；共享提醒需要应用保持运行。');note.setWordWrap(True);note.setObjectName('muted');layout.addWidget(note)
        self.overview=QLabel();layout.addWidget(self.overview)
        tabs=QTabWidget();self.tabs=tabs;self._reminder_theme=None;layout.addWidget(tabs,1)
        upcoming=QWidget();up=QVBoxLayout(upcoming);up.setContentsMargins(0,16,0,0);tabs.addTab(upcoming,'提醒列表')
        filters=QHBoxLayout();self.search=QLineEdit();self.search.setPlaceholderText('搜索提醒…');filters.addWidget(self.search,1)
        self.filter=QComboBox()
        for label,key in [('进行中','active'),('已停用 / 结束','inactive'),('全部提醒','all')]:self.filter.addItem(label,key)
        filters.addWidget(self.filter);up.addLayout(filters)
        self.items=QListWidget();self.items.setWordWrap(True);self.items.setSpacing(5);up.addWidget(self.items,1)
        self.empty=QLabel('暂无提醒。点击右上角「新建提醒」安排一件事。');self.empty.setObjectName('muted');up.addWidget(self.empty)
        row=QHBoxLayout();self.toggle_button=QPushButton('暂停提醒');self.toggle_button.clicked.connect(self.toggle);row.addWidget(self.toggle_button)
        self.edit_button=QPushButton('编辑时间与内容');self.edit_button.clicked.connect(self.edit);row.addWidget(self.edit_button);row.addStretch();up.addLayout(row)
        history_page=QWidget();hp=QVBoxLayout(history_page);hp.setContentsMargins(0,16,0,0);tabs.addTab(history_page,'投递记录')
        desc=QLabel('保留最近 100 次提醒。QQ「已接受」表示接口已确认，不代表客户端已读。');desc.setWordWrap(True);desc.setObjectName('muted');hp.addWidget(desc)
        self.history=QListWidget();self.history.setWordWrap(True);self.history.setSpacing(5);hp.addWidget(self.history,1)
        self.retry_button=QPushButton('重试所选 QQ 投递');self.retry_button.clicked.connect(self.retry);hp.addWidget(self.retry_button,alignment=Qt.AlignmentFlag.AlignLeft)
        self.items.currentItemChanged.connect(self.update_actions);self.history.currentItemChanged.connect(self.update_actions)
        self.search.textChanged.connect(self.refresh);self.filter.currentIndexChanged.connect(self.refresh)
        hub.changed.connect(lambda *_:self.refresh());self.refresh()
    def update_actions(self,*args):
        item=self.items.currentItem();r=item.data(Qt.ItemDataRole.UserRole) if item else {}
        editable=bool(r) and not r.get('legacy');self.toggle_button.setEnabled(editable);self.edit_button.setEnabled(editable)
        self.toggle_button.setText('暂停提醒' if r.get('enabled') else '启用提醒')
        item=self.history.currentItem();r=item.data(Qt.ItemDataRole.UserRole) if item else {}
        self.retry_button.setEnabled(r.get('qq_status') in ('failed','sending') and r.get('id') not in self.hub.reminder_delivery.active)
    @staticmethod
    def display_time(value):
        from datetime import datetime
        try:return datetime.fromisoformat(value).astimezone().strftime('%m月%d日 %H:%M')
        except (ValueError,TypeError):return str(value)
    def refresh(self,*args):
        theme=self.hub.config.value.get('ui_theme','dark')
        if self._reminder_theme!=theme:
            from .reminder_settings import style_reminders
            style_reminders(self.tabs,[self.items,self.history],theme);self._reminder_theme=theme
        selected=self.items.currentItem();rid=selected.data(Qt.ItemDataRole.UserRole)['id'] if selected else None
        selected=self.history.currentItem();hid=selected.data(Qt.ItemDataRole.UserRole)['id'] if selected else None
        pos=self.items.verticalScrollBar().value();hpos=self.history.verticalScrollBar().value()
        rows=self.hub.planner.schedules()+self.hub.planner.legacy_qq()
        self.overview.setText(f"{sum(bool(r['enabled']) for r in rows)} 个进行中 · QQ {'已配置' if self.hub.db.get('shared_qq',{}).get('openid') else '未配置，可在提醒设置中连接'}")
        if getattr(self.hub,'recovery',None) and self.hub.recovery.protected():self.overview.setText(self.overview.text()+' · 保护中：非紧急提醒暂缓，记录保留')
        self.items.clear();query=self.search.text().strip().casefold();scope=self.filter.currentData()
        repeats={'once':'仅一次','daily':'每天','weekly':'每周'}
        for r in rows:
            if scope=='active' and not r['enabled'] or scope=='inactive' and r['enabled']:continue
            if query and query not in r['title'].casefold():continue
            source=' · 原 QQ 插件（只读）' if r.get('legacy') else ''
            channels=' / '.join(c for c,on in [('电脑',r['local']),('QQ',r['qq'])] if on)
            item=QListWidgetItem(f"{r['title']}\n{self.display_time(r['next_due'])} · {repeats.get(r['repeat'],r['repeat'])} · {channels}{source}"+(' · 已停用 / 结束' if not r['enabled'] else ''))
            item.setData(Qt.ItemDataRole.UserRole,r);self.items.addItem(item)
            if r['id']==rid:self.items.setCurrentItem(item)
        self.empty.setVisible(self.items.count()==0);self.items.verticalScrollBar().setValue(pos)
        self.history.clear();details=self.hub.reminder_delivery.details()
        labels={'sent':'已接受','pending':'待发送','sending':'发送中 / 回执未确认','failed':'失败 / 未确认','off':'未启用','missed':'已过期，未补发'}
        for r in self.hub.planner.history():
            detail=details.get(r['id'],{});error=detail.get('error','')
            local='已提醒' if r['local_status']=='sent' else labels.get(r['local_status'],r['local_status'])
            text=f"{r['title']}\n{self.display_time(r['due'])} · 电脑：{local} · QQ：{labels.get(r['qq_status'],r['qq_status'])}"
            if error:text+='\n'+error
            item=QListWidgetItem(text);item.setData(Qt.ItemDataRole.UserRole,r);self.history.addItem(item)
            if r['id']==hid:self.history.setCurrentItem(item)
        self.history.verticalScrollBar().setValue(hpos);self.update_actions()
    def edit(self):
        item=self.items.currentItem()
        if item and not item.data(Qt.ItemDataRole.UserRole).get('legacy'):self.add(item.data(Qt.ItemDataRole.UserRole))
    def add(self,record=None):
        record=record if isinstance(record,dict) else None
        dlg=QDialog(self);dlg.setWindowTitle('编辑提醒' if record else '新建提醒');dlg.setMinimumWidth(440);form=QFormLayout(dlg)
        title=QLineEdit();due=QDateTimeEdit(QDateTime.currentDateTime().addSecs(300));due.setCalendarPopup(True)
        repeat=QComboBox()
        for name,key in [('一次','once'),('每天','daily'),('每周','weekly')]:repeat.addItem(name,key)
        local=QCheckBox('电脑提示音');local.setChecked(True);qq=QCheckBox('QQ bot 提醒')
        for name,w in [('内容',title),('时间',due),('重复',repeat),('',local),('',qq)]:form.addRow(name,w)
        if record:
            title.setText(record['title']);due.setDateTime(QDateTime.fromString(record['next_due'],Qt.DateFormat.ISODate));repeat.setCurrentIndex(repeat.findData(record['repeat']));local.setChecked(bool(record['local']));qq.setChecked(bool(record['qq']))
        urgent=QCheckBox('紧急事项：恢复或疲劳期间仍提醒');urgent.setChecked(bool(record and self.hub.planner.urgent(record['id'])));form.addRow(urgent)
        error=QLabel();error.setWordWrap(True);form.addRow(error)
        save=QPushButton('保存');save.setObjectName('primary');form.addRow(save)
        def persist():
            try:
                args=(title.text(),due.dateTime().toPython().astimezone().isoformat(),repeat.currentData(),local.isChecked(),qq.isChecked())
                if record:self.hub.planner.update(record['id'],*args);rid=record['id']
                else:rid=self.hub.planner.add(*args)
                self.hub.planner.set_urgent(rid,urgent.isChecked())
                self.hub.changed.emit('planner');dlg.accept()
            except ValueError as exc:error.setText(str(exc))
        save.clicked.connect(persist);dlg.exec()
    def toggle(self):
        item=self.items.currentItem()
        if item:
            r=item.data(Qt.ItemDataRole.UserRole)
            if r.get('legacy'):QMessageBox.information(self,'原 QQ 提醒','此条由原 QQ 插件管理，请在原插件中调整；这里仅汇总展示。');return
            self.invoke(lambda:self.hub.planner.enable(r['id'],not r['enabled']))
    def qq(self):
        from .reminder_settings import ReminderSettings
        dialog=getattr(self,'settings_dialog',None)
        if dialog is not None:
            dialog.show();dialog.raise_();dialog.activateWindow();return
        self.settings_dialog=ReminderSettings(self.hub,self)
        self.settings_dialog.destroyed.connect(self._settings_closed)
        self.settings_dialog.show()
    def _settings_closed(self):self.settings_dialog=None
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
