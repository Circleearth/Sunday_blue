"""Life cockpit and grouped records; writes exclusively use existing domain services."""
import json
from PySide6.QtCore import Qt,QDate,QTimer
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QFormLayout,QLabel,QPushButton,QLineEdit,QPlainTextEdit,QComboBox,QCheckBox,QDoubleSpinBox,QDateEdit,QListWidget,QListWidgetItem,QTabWidget,QMessageBox,QScrollArea,QBoxLayout)
from .module_forms import ModulePage,button,clock_pair,hm_pair,spin,form_dialog,INTENSITY
from .life_widgets import StatusCard,MuscleMap,TrendChart,card,label,recovery_rows,RECOVERY_COLORS,RECOVERY_LABELS
from ..modules.life_state import MUSCLES,DEFAULT_PARTS
from ..art_assets import ArtworkSlot,asset_details
from ..numeric_inputs import NumberSpin as QSpinBox, DecimalSpin as QDoubleSpinBox

class LifePage(ModulePage):
    module='life'
    def __init__(self,hub,parent=None):
        super().__init__(parent);self.hub=hub;self.setObjectName('lifePage')
        layout=QVBoxLayout(self);layout.setContentsMargins(24,20,24,16);layout.setSpacing(14)
        head=QHBoxLayout();titles=QVBoxLayout();titles.addWidget(label('生活 · 恢复站','title'));self.state_note=label();titles.addWidget(self.state_note);head.addLayout(titles,1)
        button('补记昨天',lambda:self.open_daily(),head);button('记录运动',lambda:self.exercise_dialog(),head,True);layout.addLayout(head)
        self.tabs=QTabWidget();self.tabs.setObjectName('lifeTabs');layout.addWidget(self.tabs,1)
        recovery,rec=self.page('恢复站')
        self.cards_row=QBoxLayout(QBoxLayout.Direction.LeftToRight);self.cards_row.setSpacing(12);self.cards={};self.bars={}
        for key,title in [('physical','体力储备'),('focus','专注余量'),('eye_strain','视疲劳')]:
            w=StatusCard(title);self.cards[key]=w;self.bars[key]=w.bar;self.cards_row.addWidget(w,1)
        rec.addLayout(self.cards_row)
        controls=QHBoxLayout();self.attention_status=label();controls.addWidget(self.attention_status,1)
        button('离屏休息',lambda:self.attention_mode('rest'),controls);button('恢复自动',lambda:self.attention_mode('auto'),controls)
        from .attention_controls import settings
        button('状态参数',lambda:settings(self),controls);rec.addLayout(controls)

        self.main_row=QBoxLayout(QBoxLayout.Direction.LeftToRight);self.main_row.setSpacing(16);rec.addLayout(self.main_row)
        anatomy,an=card('肌群恢复地图');self.main_row.addWidget(anatomy,3)
        hint=label('点击部位查看最近训练 · 灰色表示资料不足');an.addWidget(hint)
        self.muscle_map=MuscleMap(hub.root);an.addWidget(self.muscle_map,1);self.muscle_map.selected.connect(self.select_muscle)
        parts=QGridLayout();self.part_buttons={}
        for i,name in enumerate(MUSCLES):
            w=QPushButton(name);w.setCheckable(True);w.clicked.connect(lambda checked=False,p=name:self.select_muscle(p));self.part_buttons[name]=w;parts.addWidget(w,i//3,i%3)
        an.addLayout(parts)
        legend=label('● 浅红 恢复　● 浅橙 谨慎　● 浅黄 基本恢复　● 浅绿 可考虑训练');an.addWidget(legend)
        button('人体底图 · 替换与提示词',lambda:asset_details(self,hub.root,'recovery_body'),an)
        side=QWidget();sb=QVBoxLayout(side);sb.setContentsMargins(0,0,0,0);sb.setSpacing(12);self.main_row.addWidget(side,2)
        advice,ad=card('今天，按自己的节奏');self.advice=label('','lifeAdvice');ad.addWidget(self.advice);self.training_advice=label();ad.addWidget(self.training_advice);sb.addWidget(advice)
        detail,de=card('部位详情');self.muscle_detail=label('选择人体区域或下方部位按钮。');de.addWidget(self.muscle_detail);sb.addWidget(detail)
        self.art=ArtworkSlot(hub.root,'recovery_scene');sb.addWidget(self.art);sb.addStretch()
        rec.addWidget(label('恢复颜色沿用现有逐日规则；强度与时长显示在详情中。所有状态仅供行为参考，不作为医学判断。'));rec.addStretch()
        daily,dl=self.page('生活上报');self.daily_index=1
        top,form_box=card('生活事实 · 默认记录昨天');form=QFormLayout();form.setSpacing(12);form_box.addLayout(form)
        self.day=QDateEdit(QDate.currentDate().addDays(-1));self.day.setCalendarPopup(True);self.day.setMaximumDate(QDate.currentDate());form.addRow('记录日期',self.day);dl.addWidget(top)
        sleep,sl=card('睡眠与恢复');sf=QFormLayout();sf.setSpacing(12);self.bed=clock_pair();self.wake=clock_pair();sf.addRow('入睡时间 *',self.bed);sf.addRow('起床时间 *',self.wake);sl.addLayout(sf);sl.addWidget(label('起床早于入睡时按跨日计算。两个时间均为必填。'));dl.addWidget(sleep)
        daily_row=QBoxLayout(QBoxLayout.Direction.LeftToRight);daily_row.setSpacing(12);self.daily_row=daily_row
        meal,ml=card('饮食与备注');self.meal=QPlainTextEdit();self.meal.setPlaceholderText('简单记下吃了什么，不需要精确到每一克');self.meal.setMaximumHeight(100);ml.addWidget(self.meal);self.note=QLineEdit();self.note.setPlaceholderText('其他想记下的事');ml.addWidget(self.note);daily_row.addWidget(meal,1)
        phone,ph=card('手机使用');pf=QFormLayout();self.phone_total=hm_pair();self.phone_fun=hm_pair();pf.addRow('总使用时长',self.phone_total);pf.addRow('其中娱乐',self.phone_fun);ph.addLayout(pf);ph.addWidget(label('未知可留空；娱乐时长包含在总时长内。'));daily_row.addWidget(phone,1);dl.addLayout(daily_row)
        save=QHBoxLayout();button('保存生活上报',self.save_daily,save,True);self.daily_status=label();save.addWidget(self.daily_status,1);dl.addLayout(save)
        house,hl=card('顺手完成一件家务');row=QHBoxLayout();self.house_title=QLineEdit();self.house_title.setPlaceholderText('例如整理桌面');row.addWidget(self.house_title);button('今日家务打卡',self.housework,row);hl.addLayout(row);dl.addWidget(house);dl.addStretch()
        exercise,ex=self.page('运动记录');top=QHBoxLayout();button('记录一场运动',lambda:self.exercise_dialog(),top,True);button('修改所选记录',self.edit_exercise,top);top.addStretch();self.exercise_summary=label();top.addWidget(self.exercise_summary);ex.addLayout(top)
        ex.addWidget(label('记录真实活动，温和积累成长。修改沿用原记录，金币按差额结算。'))
        self.exercises=QListWidget();self.exercises.setWordWrap(True);self.exercises.setMinimumHeight(300);self.exercises.itemDoubleClicked.connect(lambda *_:self.edit_exercise());ex.addWidget(self.exercises,1)
        activity,al=self.page('生活正计时');clock,cl=card('给日常留一段时间');self.activity_title=QLineEdit();self.activity_title.setPlaceholderText('这次做什么？例如散步、看书放松或玩游戏');cl.addWidget(self.activity_title)
        self.clock_label=label('00:00:00','lifeClock');self.clock_label.setAlignment(Qt.AlignmentFlag.AlignCenter);cl.addWidget(self.clock_label);self.clock_status=label();self.clock_status.setAlignment(Qt.AlignmentFlag.AlignCenter);cl.addWidget(self.clock_status)
        row=QHBoxLayout();row.addStretch();self.timer_buttons={}
        for key,title,fn in [('start','开始',lambda:self.invoke(lambda:self.hub.life_timer.start(self.activity_title.text()))),('pause','暂停',lambda:self.invoke(self.hub.life_timer.pause)),('resume','继续',lambda:self.invoke(self.hub.life_timer.resume)),('finish','结束并核对',self.finish_activity)]:self.timer_buttons[key]=button(title,fn,row,key=='start')
        row.addStretch();cl.addLayout(row);cl.addWidget(label('结束时可修正多计时长，并选择恢复性休息。与正在运行的番茄钟互斥。'));al.addWidget(clock)
        al.addWidget(label('最近活动','cardTitle'));self.activity_history=QListWidget();self.activity_history.setWordWrap(True);self.activity_history.setMinimumHeight(180);al.addWidget(self.activity_history,1)
        history,his=self.page('趋势与历史');trend,tl=card('近 7 天 · 状态趋势');tl.addWidget(label('体力（绿） · 专注（蓝） · 视疲劳（黄）　｜　统一归一到 0–100%'))
        self.trend=TrendChart();tl.addWidget(self.trend);tl.addWidget(label('按现有记录重新估计；不是医学测量，也不是历史状态快照。悬停查看每日数值。'));his.addWidget(trend)
        self.trend_summary=label();his.addWidget(self.trend_summary);self.daily_history=QListWidget();self.daily_history.setMinimumHeight(160);self.daily_history.itemDoubleClicked.connect(self.open_history_day);his.addWidget(self.daily_history);his.addStretch()
        private,pr=card('私人健康记录 · 仅本机保存')
        self.private_count=spin(0,100);self.private_minutes=spin(0,1440,'分钟');self.private_discomfort=QCheckBox('有疼痛或其他不适');self.private_impact=QCheckBox('影响睡眠、工作或日常生活');self.private_enabled=QCheckBox('本次填写 / 更新私人记录');self.private_limit=spin(self.hub.db.get('private_weekly_reference',7),99)
        pf=QFormLayout();pf.addRow(self.private_enabled);pf.addRow('当天次数',self.private_count);pf.addRow('总时间',self.private_minutes);pf.addRow('个人每周参考次数（非医学标准）',self.private_limit);pf.addRow(self.private_discomfort);pf.addRow(self.private_impact);pr.addLayout(pf);self.private_status=label();pr.addWidget(self.private_status);dl.insertWidget(dl.count()-1,private)
        from .reports import ReportsPage
        self.reports_page=ReportsPage(hub,self);self.tabs.addTab(self.reports_page,'结算报告')
        self.day.dateChanged.connect(self.load_daily);hub.changed.connect(self.on_changed)
        self.clock=QTimer(self);self.clock.setInterval(1000);self.clock.timeout.connect(self.clock_refresh);self.clock.start();hub.closed.connect(self.clock.stop)
        self.state_refresh=QTimer(self);self.state_refresh.setInterval(60000);self.state_refresh.timeout.connect(self.refresh_energy);self.state_refresh.start();hub.closed.connect(self.state_refresh.stop)
        self.selected_part='胸';self.load_daily();self.refresh()
    def page(self,title):
        page=QWidget();box=QVBoxLayout(page);box.setContentsMargins(4,16,4,8);box.setSpacing(14);scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(page);self.tabs.addTab(scroll,title);return page,box
    def open_daily(self):
        self.day.setDate(QDate.currentDate().addDays(-1));self.tabs.setCurrentIndex(self.daily_index)
    def open_history_day(self,item):
        self.day.setDate(QDate.fromString(item.data(Qt.ItemDataRole.UserRole),'yyyy-MM-dd'));self.tabs.setCurrentIndex(self.daily_index)
    def resizeEvent(self,event):
        super().resizeEvent(event);narrow=self.width()<820
        for row in (self.main_row,self.daily_row):row.setDirection(QBoxLayout.Direction.TopToBottom if narrow else QBoxLayout.Direction.LeftToRight)
        self.cards_row.setDirection(QBoxLayout.Direction.TopToBottom if self.width()<650 else QBoxLayout.Direction.LeftToRight)
    def select_muscle(self,part):
        self.selected_part=part
        for name,b in self.part_buttons.items():b.setChecked(name==part)
        r=next((r for r in self.muscle_rows if r['part']==part),None)
        if r:self.muscle_detail.setText(r['detail'])
    def on_changed(self,module):
        if module in ('life','focus','work','recovery','attention'):self.refresh()
    def attention_mode(self,mode):
        self.hub.attention.configure({'mode':mode});self.refresh_energy()
    def selected_day(self):return self.day.date().toString('yyyy-MM-dd')
    def load_daily(self,*args):
        row=self.hub.life.daily(self.selected_day()) or {};self.meal.setPlainText(row.get('meal') or '');self.note.setText(row.get('note') or '')
        self.bed.load(row.get('sleep_start'));self.wake.load(row.get('sleep_end'))
        self.phone_total.load(row.get('phone_total'));self.phone_fun.load(row.get('phone_fun'))
        private=self.hub.private_wellbeing.get(self.selected_day());self.private_enabled.setChecked(bool(private));self.private_count.setValue(private.get('count',0));self.private_minutes.setValue(private.get('minutes',0));self.private_discomfort.setChecked(bool(private.get('discomfort')));self.private_impact.setChecked(bool(private.get('impact')))
        self.refresh_private()
        self.daily_status.setText(('旧睡眠时长 '+str(row['sleep_hours'])+' 小时；填写新起止时间前保留。') if row.get('sleep_hours') is not None and not row.get('sleep_start') else '上报资料属于 '+self.selected_day())
    def refresh_private(self):
        r=self.hub.private_wellbeing.status(self.selected_day());self.private_status.setText(f"近7天 {r['week_count']} 次 / {r['week_minutes']:g} 分钟 · 近30天 {r['month_count']} 次\n"+r['note']);self.private_status.setStyleSheet('border-left:4px solid '+RECOVERY_COLORS[r['level']]+';padding-left:8px;')
    def save_daily(self):
        if self.bed.value() is None:QMessageBox.warning(self,'缺少数据','睡觉时间必填，请补上再上报。');return
        if self.wake.value() is None:QMessageBox.warning(self,'缺少数据','起床时间必填，请补上再上报。');return
        if self.private_enabled.isChecked() and self.private_count.value()==0 and self.private_minutes.value()>0:
            QMessageBox.warning(self,"请核对私人记录","次数为0时总时间应为0。");return
        old=self.hub.life.daily(self.selected_day())
        values=dict(meal=self.meal.toPlainText(),phone_total=self.phone_total.value(),phone_fun=self.phone_fun.value(),note=self.note.text(),
            screen_hours=old.get('screen_hours'),energy=old.get('energy'),sleep_hours=old.get('sleep_hours'),
            sleep_start=self.bed.value(),sleep_end=self.wake.value())
        result=self.invoke(lambda:self.hub.life.save_daily(self.selected_day(),**values))
        if result is not None:
            if self.private_enabled.isChecked():
                try:self.hub.private_wellbeing.save(self.selected_day(),self.private_count.value(),self.private_minutes.value(),self.private_discomfort.isChecked(),self.private_impact.isChecked())
                except Exception as exc:QMessageBox.warning(self,"生活已保存，私人记录保存失败",str(exc));return
                self.hub.db.set('private_weekly_reference',max(1,self.private_limit.value()));self.refresh_private()
            self.daily_status.setText(f"已保存 {self.selected_day()} · 睡眠 {result.get('sleep_hours','未知')} 小时；上传奖励不重复。")
            if self.selected_day()<QDate.currentDate().toString('yyyy-MM-dd'):
                rid=self.invoke(lambda:self.hub.reports.daily(self.selected_day()))
                if rid:self.hub.report_open.emit(rid)

    def housework(self):
        self.invoke(lambda:self.hub.life.housework(self.house_title.text()))
    def edit_exercise(self):
        item=self.exercises.currentItem()
        if item:self.exercise_dialog(item.data(Qt.ItemDataRole.UserRole))
    def exercise_dialog(self,row=None):
        row=row or {};dlg,form,error,buttons=form_dialog(self,'运动记录')
        day=QDateEdit(QDate.fromString(row['day'],'yyyy-MM-dd') if row else QDate.currentDate());day.setCalendarPopup(True);day.setMaximumDate(QDate.currentDate())
        kind=QComboBox();kind.setEditable(True);kind.addItems(['快走','慢跑','羽毛球','足球','骑行','力量训练','其他']);kind.setCurrentText(row.get('kind','快走'))
        minutes=spin(row.get('minutes',20),180,' 分钟');intensity=QComboBox()
        for key,label in INTENSITY.items():intensity.addItem(label,key)
        intensity.setCurrentIndex(max(0,intensity.findData(row.get('intensity','moderate'))))
        for label,w in [('日期',day),('运动类型',kind),('有效时长',minutes),('强度',intensity)]:form.addRow(label,w)
        parts=QWidget();pl=QHBoxLayout(parts);boxes={};existing=json.loads(row.get('muscles') or '[]')
        for name in MUSCLES:
            box=QCheckBox(name);box.setChecked(name in existing);boxes[name]=box;pl.addWidget(box)
        form.addRow('训练部位（可多选）',parts)
        buttons.accepted.connect(lambda:self.save_dialog(dlg,error,lambda:self.hub.life.exercise(kind.currentText(),minutes.value(),intensity.currentData(),day=day.date().toString('yyyy-MM-dd'),record_id=row.get('id'),muscles=[k for k,v in boxes.items() if v.isChecked()])));dlg.exec()
    def clock_refresh(self):
        self.hub.life_timer.checkpoint();state=self.hub.life_timer.status();seconds=int(state['elapsed'])
        self.clock_label.setText(f"{seconds//3600:02}:{seconds//60%60:02}:{seconds%60:02}")
        self.clock_status.setText(state.get('title','')+' · '+{'idle':'等待开始','running':'正在计时','paused':'已暂停'}.get(state['state'],state['state']))
        for key,b in self.timer_buttons.items():b.setEnabled(state['state']=={'start':'idle','pause':'running','resume':'paused'}.get(key,state['state']) if key!='finish' else state['state']!='idle')
        self.activity_title.setEnabled(state['state']=='idle')
    def finish_activity(self):
        self.hub.life_timer.pause();state=self.hub.life_timer.status()
        if state['state']=='idle':return
        dlg,form,error,buttons=form_dialog(self,'结算活动 · 保留原始计时')
        minutes=QDoubleSpinBox();minutes.setRange(0,state['elapsed']/60);minutes.setDecimals(2);minutes.setValue(state['elapsed']/60);form.addRow('调整后有效分钟',minutes)
        physical=QComboBox();focus=QComboBox()
        for w in (physical,focus):
            for label,key in [('低','low'),('中','medium'),('高','high')]:w.addItem(label,key)
        form.addRow('体力影响强度',physical);form.addRow('专注力影响强度',focus);rest=QCheckBox('这次是恢复性休息（增加恢复估计，而非扣减）');form.addRow(rest)
        buttons.accepted.connect(lambda:self.save_dialog(dlg,error,lambda:self.hub.life_timer.finish(minutes.value()*60,physical.currentData(),focus.currentData(),rest.isChecked())));dlg.exec()
    def refresh_energy(self):
        today=QDate.currentDate().toString('yyyy-MM-dd');r=self.hub.life.energy(today)
        self.cards['physical'].set_state(round(r['physical_value'],1),round(r['physical_cap'],1),r['physical'],'低于 40% 时，优先恢复再安排活动。')
        a=self.hub.attention.status();self.attention_status.setText(f"用眼估算 {a['eye']:.1f}% · {a['source']} · 休息只恢复视疲劳与专注")
        self.cards['focus'].set_state(round(r['focus_value'],1),r['focus_cap'],r['focus'],'留意连续投入后的余量，适时切换节奏。')
        self.cards['eye_strain'].set_state(r['eye_strain'],100,r['eye_strain'],'数值越低越轻松；较高时先离屏远眺。',True)
        self.state_note.setText(f"{today}  ·  工作 {r['work_minutes']:.0f} 分  /  学习 {r['study_minutes']:.0f} 分  /  运动 {r['exercise_minutes']:.0f} 分")
        recovering=self.hub.recovery.status().get('active')
        advice='正在恢复中。先放松，不急着开始下一项任务。' if recovering else '先离屏休息，再决定是否继续。' if r['focus']<45 or r['eye_strain']>=60 else '可以安排一段适量专注，结束后起身活动。'
        self.advice.setText(advice);self.advice.setToolTip('\n'.join(r['suggestions']))
        self.muscle_rows=recovery_rows(r['muscles'],self.hub.life.exercises(),today);self.muscle_map.set_rows(self.muscle_rows)
        ready=[x['part'] for x in self.muscle_rows if x['level']=='green'];rest=[x['part'] for x in self.muscle_rows if x['level'] in ('red','orange')]
        self.training_advice.setText('可考虑：'+('、'.join(ready) or '先补充运动记录')+'\n需要恢复：'+('、'.join(rest) or '暂无已知高负荷部位')+'\n'+('优先轻量散步或休息。' if recovering or r['physical']<45 else '从轻至中等强度开始，结合身体感受调整。'))
        for x in self.muscle_rows:
            b=self.part_buttons[x['part']];b.setToolTip(x['detail']);b.setStyleSheet(f"QPushButton {{border-bottom:3px solid {RECOVERY_COLORS[x['level']]};}} QPushButton:checked {{background:#e8edf3;color:#35445b;}}")
        self.select_muscle(self.selected_part);self.trend.set_rows(r['trend']);first,last=r['trend'][0],r['trend'][-1]
        self.trend_summary.setText(f"相较 6 天前：体力参考 {last['physical']-first['physical']:+g} · 专注参考 {last['focus']-first['focus']:+g} 百分点　｜　双击日期补记或修改")
        self.daily_history.clear()
        for day in reversed(r['trend']):
            daily=self.hub.life.daily(day['day']);text=f"{day['day']}　·　"+('已上报' if daily else '未上报')
            if daily:text+=f"　睡眠 {daily.get('sleep_hours') if daily.get('sleep_hours') is not None else '未知'} 小时"
            item=QListWidgetItem(text);item.setData(Qt.ItemDataRole.UserRole,day['day']);self.daily_history.addItem(item)
    def refresh(self,*args):
        selected=self.exercises.currentItem();rid=selected.data(Qt.ItemDataRole.UserRole)['id'] if selected else None;self.exercises.clear();rows=self.hub.life.exercises()
        for row in rows:
            parts=json.loads(row.get('muscles') or '[]') or DEFAULT_PARTS.get(row['kind'],[])
            item=QListWidgetItem(f"{row['kind']}　·　{row['minutes']:g} 分钟　·　{INTENSITY.get(row['intensity'])}强度　·　{row['coins']} 金币\n{row['day']}　｜　部位：{'、'.join(parts) or '未指定'}")
            item.setData(Qt.ItemDataRole.UserRole,row);self.exercises.addItem(item)
            if row['id']==rid:self.exercises.setCurrentItem(item)
        self.exercise_summary.setText(f'最近 {len(rows)} 条' if rows else '还没有运动记录')
        self.activity_history.clear()
        for row in self.hub.life_timer.history():self.activity_history.addItem(f"{row['title']}　·　{'恢复性休息' if row['rest'] else '日常活动'}\n{row['day']}　原始 {row['elapsed']/60:.1f} / 有效 {row['effective']/60:.1f} 分钟")
        self.refresh_energy();self.clock_refresh()
