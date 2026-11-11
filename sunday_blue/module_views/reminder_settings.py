"""Reminder channel preferences; network checks use the delivery service's worker."""
from PySide6.QtCore import Qt,Slot
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QLineEdit,
    QPushButton,QTabWidget,QWidget,QCheckBox,QSlider,QFileDialog)
from ..modules.focus_preferences import import_sound

def style_reminders(tabs,lists,theme):
    from ..design_system import tokens
    t=tokens(theme)
    tabs.setStyleSheet(f"QTabWidget::pane {{ border: none; }} QTabBar::tab {{ background: transparent; color: {t['text_subtle']}; padding: 10px 18px; border-bottom: 2px solid transparent; }} QTabBar::tab:selected {{ color: {t['text']}; border-bottom: 2px solid {t['accent']}; }}")
    for widget in lists:
        widget.setStyleSheet(f"QListWidget {{ border: none; background: transparent; color: {t['text']}; }} QListWidget::item {{ background: {t['surface_raised']}; border-radius: 8px; padding: 12px; margin: 3px 0; }} QListWidget::item:selected {{ background: {t['accent_soft']}; color: {t['text']}; }} QListWidget::item:hover {{ background: {t['surface']}; }}")

class ReminderSettings(QDialog):
    def __init__(self,hub,parent=None):
        super().__init__(parent);self.hub=hub;self.request=None
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose);self.setWindowTitle('提醒设置');self.resize(580,420)
        layout=QVBoxLayout(self);layout.setContentsMargins(24,24,24,24);layout.setSpacing(16)
        tabs=QTabWidget();layout.addWidget(tabs);style_reminders(tabs,[],hub.config.value.get('ui_theme','dark'))
        qq=QWidget();form=QFormLayout(qq);form.setSpacing(14);tabs.addTab(qq,'QQ 渠道')
        value=hub.db.get('shared_qq',{})
        if not value:
            for rv in (hub.config.value.get('roles') or {}).values():
                ps=(rv.get('plugin_settings') or {}).get('qq-reminders') or {}
                if ps.get('qq_openid'):
                    value={'profile':ps.get('dsh_profile','qqbot'),'openid':ps['qq_openid'],'proxy':ps.get('http_proxy','')};break
        self.profile=QLineEdit(value.get('profile','qqbot'));self.openid=QLineEdit(value.get('openid',''));self.proxy=QLineEdit(value.get('proxy',''))
        self.proxy.setPlaceholderText('留空使用系统网络')
        for label,w in [('机器人配置名',self.profile),('接收者 openid',self.openid),('网络代理',self.proxy)]:form.addRow(label,w)
        note=QLabel('复用已绑定机器人的凭据。检查和试发使用当前填写内容；保存后才用于定时提醒。');note.setWordWrap(True);note.setObjectName('muted');form.addRow(note)
        self.status=QLabel('尚未检查。打开设置不会自动联网。');self.status.setWordWrap(True);form.addRow(self.status)
        row=QHBoxLayout();self.check=QPushButton('检查连接');self.send=QPushButton('发送测试消息');self.save=QPushButton('保存 QQ 配置');self.save.setObjectName('primary')
        for b in (self.check,self.send,self.save):row.addWidget(b)
        form.addRow(row);self.check.clicked.connect(lambda:self.start(False));self.send.clicked.connect(lambda:self.start(True));self.save.clicked.connect(self.save_channel)
        hub.reminder_delivery.check_result.connect(self.checked)
        sound=QWidget();sf=QFormLayout(sound);sf.setSpacing(14);tabs.addTab(sound,'电脑提示音')
        self.sound_cfg=hub.db.get('reminder_sound',{'sound_enabled':True,'volume':65,'sounds':{'focus':''}})
        self.path=self.sound_cfg.get('sounds',{}).get('focus','');self.enabled=QCheckBox('启用电脑声音');self.enabled.setChecked(self.sound_cfg.get('sound_enabled',True));sf.addRow(self.enabled)
        self.volume=QSlider(Qt.Orientation.Horizontal);self.volume.setRange(0,100);self.volume.setValue(self.sound_cfg.get('volume',65));self.volume_label=QLabel(str(self.volume.value())+'%');self.volume.valueChanged.connect(lambda n:self.volume_label.setText(str(n)+'%'))
        volrow=QHBoxLayout();volrow.addWidget(self.volume);volrow.addWidget(self.volume_label);sf.addRow('音量',volrow)
        self.sound_label=QLabel();self.sound_label.setWordWrap(True);sf.addRow('提示音',self.sound_label);self.update_sound_label()
        buttons=QHBoxLayout()
        for title,fn in [('选择 MP3 / WAV',self.choose_sound),('恢复默认',self.reset_sound),('试听',self.preview),('停止',hub.reminder_alarm.stop)]:
            b=QPushButton(title);b.clicked.connect(fn);buttons.addWidget(b)
        sf.addRow(buttons);save_sound=QPushButton('保存声音设置');save_sound.clicked.connect(self.save_sound);sf.addRow(save_sound)
        self.sound_status=QLabel('声音仅用于已启用电脑渠道的提醒。');self.sound_status.setWordWrap(True);sf.addRow(self.sound_status)
        close=QPushButton('关闭');close.clicked.connect(self.close);layout.addWidget(close,alignment=Qt.AlignmentFlag.AlignRight)
    def draft(self):return {'profile':self.profile.text(),'openid':self.openid.text(),'proxy':self.proxy.text()}
    def save_channel(self):
        try:
            cfg=self.hub.reminder_delivery.validate(self.draft());self.hub.db.set('shared_qq',cfg)
            self.status.setText('QQ 配置已保存，后续定时提醒使用此配置。');self.hub.changed.emit('planner')
        except Exception as exc:self.status.setText(self.hub.reminder_delivery.error_text(exc))
    def start(self,send):
        try:self.request=self.hub.reminder_delivery.start_check(self.draft(),send)
        except Exception as exc:self.status.setText(self.hub.reminder_delivery.error_text(exc));return
        for w in (self.check,self.send,self.save,self.profile,self.openid,self.proxy):w.setEnabled(False)
        self.status.setText('正在后台试发，请勿重复提交；关闭窗口不会撤回发送。' if send else '正在后台验证凭据与连接，可继续使用主窗口。')
    @Slot(str,object)
    def checked(self,key,result):
        if key!=self.request:return
        self.request=None
        for w in (self.check,self.send,self.save,self.profile,self.openid,self.proxy):w.setEnabled(True)
        self.status.setText(result['message'])
    def update_sound_label(self):
        from pathlib import Path
        self.sound_label.setText(Path(self.path).name if self.path else '系统默认音效')
    def choose_sound(self):
        source,_=QFileDialog.getOpenFileName(self,'选择提醒声音','','音频 (*.mp3 *.wav)')
        if source:
            try:self.path=import_sound(self.hub.root,source);self.update_sound_label()
            except Exception as exc:self.sound_status.setText(str(exc))
    def reset_sound(self):self.path='';self.update_sound_label()
    def sound_value(self):return {'sound_enabled':self.enabled.isChecked(),'volume':self.volume.value(),'sounds':{'focus':self.path}}
    def preview(self):self.hub.reminder_alarm.play('focus',self.hub.focus.options()|self.sound_value())
    def save_sound(self):self.hub.db.set('reminder_sound',self.sound_value());self.sound_status.setText('提示音设置已保存。')
    def closeEvent(self,event):self.hub.reminder_alarm.stop();super().closeEvent(event)
