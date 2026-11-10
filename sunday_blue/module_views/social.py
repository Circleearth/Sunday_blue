from datetime import datetime
from html import escape
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QPushButton,QTextBrowser,
    QPlainTextEdit,QDialog,QFormLayout,QLineEdit,QListWidget,QListWidgetItem,QCheckBox,QSpinBox,QMessageBox)
from ..roles import list_roles


def _when(iso):
    try:return datetime.fromisoformat(iso).astimezone().strftime('%m-%d %H:%M')
    except Exception:return ''


class SocialPage(QWidget):
    def __init__(self,hub,parent=None):
        super().__init__(parent);self.hub=hub;self._rendered=None;self._stopped=set();self._drafts={};self._current_group=None
        layout=QVBoxLayout(self);layout.setContentsMargins(28,22,28,22)
        title=QLabel('一起把日子过明白。');title.setObjectName('title');layout.addWidget(title)
        row=QHBoxLayout();self.groups=QComboBox();self.groups.currentIndexChanged.connect(self._group_changed);row.addWidget(self.groups,1)
        for label,callback in [('创建会议',self.create),('主动交流设置',self.preferences),('请求记录',self.diagnostics)]:
            button=QPushButton(label);button.clicked.connect(callback);row.addWidget(button)
        layout.addLayout(row)
        self.memory=QCheckBox('角色参考各自最近私聊与长期记忆；私聊也衔接群聊经历');self.memory.toggled.connect(self.memory_changed);layout.addWidget(self.memory)
        self.messages=QTextBrowser();self.messages.setOpenExternalLinks(False);layout.addWidget(self.messages,1)
        self.state=QLabel();self.state.setWordWrap(True);self.state.setObjectName('muted');layout.addWidget(self.state)
        self.input=QPlainTextEdit();self.input.setMaximumHeight(90);layout.addWidget(self.input)
        row=QHBoxLayout();self.send=QPushButton('发送到会议');self.send.setObjectName('primary');self.send.clicked.connect(self.post);row.addWidget(self.send)
        self.retry=QPushButton('继续回复');self.retry.clicked.connect(self.resume);row.addWidget(self.retry)
        self.summary=QPushButton('结束话题并总结');self.summary.clicked.connect(self.summarize);row.addWidget(self.summary)
        self.stop=QPushButton('停止回复');self.stop.clicked.connect(self.stop_clicked);row.addWidget(self.stop);layout.addLayout(row)
        hub.changed.connect(lambda *_:self.refresh());hub.failed.connect(self.error);self.refresh()
    def error(self,text):self.state.setText(text)
    def invoke(self,fn):
        try:fn();self.refresh();return True
        except Exception as exc:self.error(str(exc));return False
    def refresh(self,*args):
        selected=self.groups.currentData();groups=self.hub.social.groups()
        current=[self.groups.itemData(i) for i in range(self.groups.count())]
        if current!=[g['id'] for g in groups]:
            # 重建下拉前保存上一群草稿；期间屏蔽信号，改由下方显式恢复目标群草稿
            if self._current_group is not None:self._drafts[self._current_group]=self.input.toPlainText()
            self.groups.blockSignals(True);self.groups.clear()
            for g in groups:self.groups.addItem(g['title'],g['id'])
            index=max(0,self.groups.findData(selected));self.groups.setCurrentIndex(index)
            gid=self.groups.itemData(index)
            self.input.setPlainText(self._drafts.get(gid,'') if gid else '');self._current_group=gid
            self.groups.blockSignals(False)
        gid=self.groups.currentData();busy=gid in self.hub.busy_groups()
        if busy:self._stopped.discard(gid)
        self.send.setEnabled(bool(gid) and not busy);self.retry.setEnabled(bool(gid) and not busy);self.summary.setEnabled(bool(gid) and not busy);self.stop.setEnabled(busy)
        self.memory.setEnabled(bool(gid) and not busy)
        if not gid:self.messages.setPlainText('创建一个群，选择一起交流的角色。群聊不会让角色直接读取彼此的私人历史。');self.state.setText('');return
        group=self.hub.social.group(gid);self.memory.blockSignals(True);self.memory.setChecked(bool(group['private_context']));self.memory.blockSignals(False)
        names=dict((r[0],r[1]) for r in list_roles(self.hub.root))
        messages=self.hub.social.messages(gid);key=(gid,tuple(m['id'] for m in messages))
        if self._rendered!=key:
            bar=self.messages.verticalScrollBar();follow=bar.maximum()-bar.value()<24;position=bar.value()
            # 发送者名称取历史快照（m['name']），不受角色改名破坏；附带时间
            self.messages.setHtml('<br>'.join(
                f'<p><b>{escape(m["name"])}</b><span style="color:#888888"> {_when(m["created"])}</span><br>{escape(m["content"]).replace(chr(10),"<br>")}</p>'
                for m in messages))
            bar.setValue(bar.maximum() if follow or self._rendered is None or self._rendered[0]!=gid else min(position,bar.maximum()));self._rendered=key
        if busy:
            self.state.setText('角色正在倾听并判断是否接话；允许沉默，不强迫每个人发言。')
        elif gid in self._stopped:
            self.state.setText('已停止本次回复；可继续发消息，或点「继续回复」接上未说完的话题。')
        else:
            # 只按当前群成员过滤记忆支撑状态，不显示上一个群的状态
            status=self.hub.social.memory_status
            lines=[f'{names.get(rid,rid)}：{status[rid]}' for rid in group['members'] if rid in status]
            self.state.setText('记忆支撑：'+'；'.join(lines) if lines else '')
    def _group_changed(self,*_):
        # 切群前保存上一群草稿，恢复本群草稿；刷新按钮不触碰输入框
        if self._current_group is not None:self._drafts[self._current_group]=self.input.toPlainText()
        gid=self.groups.currentData()
        self.input.setPlainText(self._drafts.get(gid,''));self._current_group=gid
        self.refresh()
    def stop_clicked(self):
        gid=self.groups.currentData()
        if gid:self._stopped.add(gid)
        self.hub.cancel_group(gid)
    def memory_changed(self,enabled):
        gid=self.groups.currentData()
        if gid:self.invoke(lambda:self.hub.social.set_memory_support(gid,enabled))
    def create(self):
        dialog=QDialog(self);dialog.setWindowTitle('创建共同空间');layout=QVBoxLayout(dialog)
        title=QLineEdit('周日家庭会议');layout.addWidget(title);roles=QListWidget();layout.addWidget(roles)
        for rid,name,*_ in list_roles(self.hub.root):
            item=QListWidgetItem(name);item.setData(Qt.ItemDataRole.UserRole,rid);item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if rid in ('rui','kia','mia') else Qt.CheckState.Unchecked);roles.addItem(item)
        share=QCheckBox('允许专注完成记录进入这个群（不公开私人聊天记录）');layout.addWidget(share)
        memory=QCheckBox('各角色参考自己的私聊记忆，保持连续的共同生活');memory.setChecked(True);layout.addWidget(memory)
        save=QPushButton('创建群聊');save.clicked.connect(dialog.accept);layout.addWidget(save)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            members=[roles.item(i).data(Qt.ItemDataRole.UserRole) for i in range(roles.count()) if roles.item(i).checkState()==Qt.CheckState.Checked]
            def create():
                gid=self.hub.social.create_group(title.text(),members,share.isChecked(),memory.isChecked());self.refresh();self.groups.setCurrentIndex(self.groups.findData(gid))
            self.invoke(create)
    def post(self):
        text=self.input.toPlainText().strip()
        if text and self.invoke(lambda:self.hub.send_group(self.groups.currentData(),text)):
            self._stopped.discard(self.groups.currentData());self._drafts.pop(self.groups.currentData(),None);self.input.clear()
    def resume(self):
        self.invoke(lambda:self.hub.retry_group(self.groups.currentData()))
    def summarize(self):self.invoke(lambda:self.hub.summarize_group(self.groups.currentData()))
    def preferences(self):
        cfg=self.hub.social.get_settings();dialog=QDialog(self);dialog.setWindowTitle('主动交流与用量');form=QFormLayout(dialog);widgets={}
        for key,label in [('proactive_enabled','启用主动群聊'),('idle_enabled','允许每天一次轻松闲聊'),('followup_enabled','允许 Rui 在会后主动私聊')]:
            box=QCheckBox(label);box.setChecked(cfg[key]);form.addRow(box);widgets[key]=box
        groups=QComboBox();groups.addItem('请选择目标群',None)
        for g in self.hub.social.groups():groups.addItem(g['title'],g['id'])
        groups.setCurrentIndex(max(0,groups.findData(cfg['group_id'])));form.addRow('目标群',groups)
        for key,label,lo,hi in [('daily_calls','每天最多模型调用',1,100),('daily_tokens','每天估算 Token 预算',1000,200000),('cooldown_minutes','主动话题冷却（分钟）',5,1440),('max_turns','每话题最多发言角色',1,6),('quiet_start','静默开始时（0–23）',0,23),('quiet_end','静默结束时（相同则不设静默）',0,23)]:
            box=QSpinBox();box.setRange(lo,hi);box.setValue(cfg[key]);form.addRow(label,box);widgets[key]=box
        note=QLabel('只在软件运行时工作。专注期间不主动开启话题；手动群聊与主动交流共用预算。私聊支撑只取当前发言角色的近期记忆。');note.setWordWrap(True);form.addRow(note)
        save=QPushButton('保存');save.clicked.connect(dialog.accept);form.addRow(save)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            value=cfg|{k:(w.isChecked() if isinstance(w,QCheckBox) else w.value()) for k,w in widgets.items()}|{'group_id':groups.currentData()}
            self.invoke(lambda:self.hub.social.set_settings(value))
    def diagnostics(self):
        dialog=QDialog(self);dialog.setWindowTitle('最近请求 · 不包含正文或密钥');dialog.resize(750,420);layout=QVBoxLayout(dialog);view=QPlainTextEdit();view.setReadOnly(True);layout.addWidget(view)
        view.setPlainText('\n\n'.join(f"{r['created']} · {r['role']} · {r['model']} · {r['elapsed']} 秒\n{r['purpose']} · 推理参数 {r['reasoning']} · 用量 {r['usage']} · 错误 {r['error'] or '无'}" for r in self.hub.diagnostics()) or '暂无请求。')
        close=QPushButton('关闭');close.clicked.connect(dialog.accept);layout.addWidget(close);dialog.exec()
