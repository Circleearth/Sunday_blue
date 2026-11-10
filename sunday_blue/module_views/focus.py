from datetime import datetime
from PySide6.QtCore import QTimer,Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QLineEdit,
    QPushButton,QListWidget,QListWidgetItem,QMessageBox,QSpinBox,QProgressBar)
from ..roles import list_roles


def _hm(iso):
    try:return datetime.fromisoformat(iso).astimezone().strftime('%m-%d %H:%M')
    except Exception:return ''


class FocusPage(QWidget):
    def __init__(self,hub,parent=None):
        super().__init__(parent);self.hub=hub
        layout=QVBoxLayout(self);layout.setContentsMargins(32,24,32,24);layout.setSpacing(14)
        title=QLabel('把注意力，放回现实。');title.setObjectName('title');layout.addWidget(title)
        note=QLabel('专注超过 2 分钟才生成有效记录。暂停、休息与缺席不扣分。');note.setObjectName('muted');layout.addWidget(note)
        row=QHBoxLayout();self.category=QComboBox();self.category.setEditable(True);self.category.addItems(hub.focus.categories());row.addWidget(self.category)
        self.label=QLineEdit();self.label.setPlaceholderText('这次想做什么？（可选）');row.addWidget(self.label,1)
        self.roles=QComboBox()
        for rid,name,*_ in list_roles(hub.root):self.roles.addItem(name,rid)
        row.addWidget(self.roles);self.target=QSpinBox();self.target.setRange(1,240);self.target.setValue(25);self.target.setSuffix(' 分钟目标');row.addWidget(self.target);layout.addLayout(row)
        hint=QLabel('目标仅提醒；点击「结束并结算」才记录有效。');hint.setObjectName('section');layout.addWidget(hint)
        center=QHBoxLayout();self.avatar=QLabel();self.avatar.setFixedSize(96,96);center.addWidget(self.avatar)
        self.clock=QLabel('00:00');self.clock.setObjectName('title');center.addWidget(self.clock);center.addStretch();layout.addLayout(center)
        self.progress=QProgressBar();self.progress.setRange(0,100);layout.addWidget(self.progress)
        row=QHBoxLayout();self.start=QPushButton('开始专注');self.start.setObjectName('primary');self.start.clicked.connect(self.begin);row.addWidget(self.start)
        self.pause=QPushButton('暂停');self.pause.clicked.connect(self.toggle);row.addWidget(self.pause)
        self.finish=QPushButton('结束并结算');self.finish.clicked.connect(self.settle);row.addWidget(self.finish);layout.addLayout(row)
        self.stats=QLabel();self.stats.setWordWrap(True);layout.addWidget(self.stats)
        self.feed=QListWidget();self.feed.setMaximumHeight(170);layout.addWidget(self.feed)
        layout.addWidget(QLabel('最近的现实记录 · 最多显示最近 30 条'));self.records=QListWidget();layout.addWidget(self.records,1)
        hub.feedback.connect(self.feedback);hub.changed.connect(lambda *_:self.refresh(True));self.roles.currentIndexChanged.connect(self.art)
        self.timer=QTimer(self);self.timer.setInterval(1000);self.timer.timeout.connect(self.refresh);hub.closed.connect(self.timer.stop)
        self.timer.start();self.refresh(True);self.art()

    def art(self):
        role=str(self.roles.currentData())
        path=self.hub.root/'assets/roles'/role/'avatar.png'
        pix=QPixmap(str(path))
        if not pix.isNull():self.avatar.setPixmap(pix.scaled(96,96,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))

    def invoke(self,fn):
        try:return fn()
        except Exception as exc:QMessageBox.warning(self,'暂未完成',str(exc))

    def begin(self):
        self.invoke(lambda:self.hub.focus.start(self.category.currentText(),self.label.text(),self.roles.currentData()));self.refresh(True)

    def toggle(self):
        self.invoke(self.hub.focus.pause if self.hub.focus.status()['state']=='running' else self.hub.focus.resume);self.refresh()

    def settle(self):
        result=self.invoke(self.hub.focus.finish)
        if result:
            text=(f"本次获得 {result['coins_earned']} 金币 · 余额 {result['balance']}\n今日累计 {int(result['today_seconds']//60)} 分钟 · 连续记录 {result['streak']} 天\n"
                  +('刷新单次专注纪录！\n' if result['personal_best'] else '')+'\n'.join(result['milestones'])+'\n\n'+result['feedback'])
            QMessageBox.information(self,'专注结算' if result['valid'] else '这一小段也值得尊重',text)
        self.refresh(True)

    def feedback(self,role,text):
        names=dict((r[0],r[1]) for r in list_roles(self.hub.root));item=QListWidgetItem(names.get(role,'伙伴')+'：'+text)
        self.feed.addItem(item)
        while self.feed.count()>4:self.feed.takeItem(0)
        self.feed.scrollToBottom()
        def expire():
            index=self.feed.row(item)
            if index>=0:self.feed.takeItem(index)
        QTimer.singleShot(12000,self,expire)

    def refresh(self,full=False):
        state=self.hub.focus.status();elapsed=int(state['elapsed'])
        self.clock.setText(f'{elapsed//60:02d}:{elapsed%60:02d}'+(' · 已暂停' if state['state']=='paused' else ''))
        self.progress.setValue(min(100,int(elapsed/(self.target.value()*60)*100)))
        active=state['state']!='idle'
        if active:
            # 持久化活动的实际值，不能显示默认选项
            self.category.blockSignals(True);self.category.setEditText(str(state['category']));self.category.blockSignals(False)
            self.label.setText(str(state['label']))
            self.roles.setCurrentIndex(max(0,self.roles.findData(state['role_id'])))
        self.start.setEnabled(not active);self.pause.setEnabled(active);self.finish.setEnabled(active)
        self.pause.setText('继续' if state['state']=='paused' else '暂停')
        for widget in (self.category,self.label,self.roles):widget.setEnabled(not active)
        if full:
            roles=list_roles(self.hub.root)
            if [self.roles.itemData(i) for i in range(self.roles.count())]!=[r[0] for r in roles]:
                chosen=self.roles.currentData();self.roles.blockSignals(True);self.roles.clear()
                for rid,name,*_ in roles:self.roles.addItem(name,rid)
                self.roles.setCurrentIndex(max(0,self.roles.findData(chosen)));self.roles.blockSignals(False);self.art()
            stats=self.hub.focus.stats();self.stats.setText(f"今天 {int(stats['today_seconds']//60)} 分钟 / {stats['today_count']} 次 · 近 7 天 {int(stats['week_seconds']//60)} 分钟 · 连续 {stats['streak']} 天 · {stats['balance']} 金币")
            self.records.clear()
            records=self.hub.focus.records()
            for r in records:self.records.addItem(f"{r['day']} · {r['category']} · {int(r['seconds']//60)} 分钟 · {r['label']}\n{_hm(r['started'])} – {_hm(r['finished'])}")
            if not records:self.records.addItem('还没有有效记录。')
