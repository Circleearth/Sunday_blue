"""Per-role model settings; unsupported reasoning is never silently advertised."""
import copy
from PySide6.QtCore import QThread,Signal
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QFormLayout,QHBoxLayout,QCheckBox,QLineEdit,
    QComboBox,QSpinBox,QLabel,QPushButton,QMessageBox)
from .storage import protect
from .models import resolve_api,RoleProvider
from .numeric_inputs import NumberSpin as QSpinBox, DecimalSpin as QDoubleSpinBox


class ModelTest(QThread):
    result=Signal(str)
    def __init__(self,root,role,config):
        super().__init__();self.root,self.role,self.config=root,role,config
    def run(self):
        try:
            provider=RoleProvider(self.root,self.role,self.config,purpose='connection_test')
            budget=int(provider.config.get('thinking_budget',0))
            provider.complete('Reply briefly.',[{'role':'user','content':'Reply OK.'}],max_tokens=budget+64 if budget else 64)
            self.result.emit('连接成功，服务已接受本次参数。实际推理效果仍由所选模型决定。')
        except Exception as exc:self.result.emit(str(exc))


class RoleModelDialog(QDialog):
    def __init__(self,root,config,role,parent=None):
        super().__init__(parent);self.root,self.config,self.role=root,copy.deepcopy(config),role;self.worker=None
        self.profile=copy.deepcopy(config['roles'][role].get('model_profile',{}));base=resolve_api(config,role)
        self.setWindowTitle('角色独立模型与推理');self.resize(700,620);layout=QVBoxLayout(self)
        self.enabled=QCheckBox('为这个角色使用独立模型 / 连接');self.enabled.setChecked(self.profile.get('enabled',False));layout.addWidget(self.enabled)
        form=QFormLayout()
        def section(text):
            head=QLabel(text);head.setObjectName('section');form.addRow(head)
        section('连接（留空项继承全局）')
        self.protocol=QComboBox();self.protocol.addItem('Anthropic Messages','anthropic');self.protocol.addItem('OpenAI 兼容','openai');self.protocol.setCurrentIndex(max(0,self.protocol.findData(base['protocol'])))
        self.url=QLineEdit(base['base_url']);self.model=QLineEdit(base['model']);self.light=QLineEdit(self.profile.get('light_model',''))
        self.key=QLineEdit();self.key.setEchoMode(QLineEdit.EchoMode.Password);self.key.setPlaceholderText('留空保持已有角色密钥；尚未设置则沿用全局密钥')
        self.auth=QComboBox();self.auth.addItems(['x-api-key','bearer']);self.auth.setCurrentText(base.get('auth','x-api-key'))
        self.maximum=QSpinBox();self.maximum.setRange(64,128000);self.maximum.setValue(base['max_tokens'])
        self.context=QSpinBox();self.context.setRange(1000,2000000);self.context.setValue(base['context_limit'])
        for label,widget in [('协议',self.protocol),('请求地址',self.url),('模型 ID',self.model),('API Key',self.key),('鉴权方式',self.auth),('最大输出',self.maximum),('上下文容量',self.context)]:form.addRow(label,widget)
        section('群聊与轻互动（可用更便宜的模型；留空则沿用上面的模型）')
        form.addRow('群聊 / 轻互动模型（可留空）',self.light)
        section('推理参数（只在实际测试确认服务商支持时启用，否则保持关闭）')
        self.mode=QComboBox()
        for label,key in [('不请求额外推理','off'),('服务商支持：Anthropic 思考预算','anthropic_budget'),('服务商支持：OpenAI reasoning_effort','openai_effort')]:self.mode.addItem(label,key)
        self.mode.setCurrentIndex(max(0,self.mode.findData(self.profile.get('reasoning','off'))))
        self.budget=QSpinBox();self.budget.setRange(1024,127000);self.budget.setValue(self.profile.get('thinking_budget',1024))
        self.effort=QComboBox();self.effort.addItems(['low','medium','high']);self.effort.setCurrentText(self.profile.get('reasoning_effort','medium'))
        for label,widget in [('推理参数支持声明',self.mode),('Anthropic 思考预算',self.budget),('OpenAI 推理强度',self.effort)]:form.addRow(label,widget)
        layout.addLayout(form)
        note=QLabel('不勾选独立模型时，本角色完全沿用全局连接、模型与密钥；勾选后按上方填写，留空项仍继承全局，各角色之间互不串值。\n'
                    '本页修改只在点「应用到设置草稿」后才写入设置草稿；取消或关闭不会改动任何正式配置。\n'
                    '「测试该角色连接」会真实发送一条简短请求并产生少量用量；软件不会按模型名称猜测推理能力，只在实际测试确认支持时启用相应参数。\n'
                    '群聊短互动与主动交流关闭额外推理；普通私聊和复盘使用此角色配置。');note.setWordWrap(True);layout.addWidget(note)
        self.result_label=QLabel();self.result_label.setWordWrap(True);layout.addWidget(self.result_label)
        row=QHBoxLayout();test=QPushButton('测试该角色连接（有少量用量）');test.clicked.connect(self.test);row.addWidget(test);row.addStretch()
        cancel=QPushButton('取消');cancel.clicked.connect(self.reject);row.addWidget(cancel);save=QPushButton('应用到设置草稿');save.clicked.connect(self.save);row.addWidget(save);layout.addLayout(row)
    def value(self):
        profile=self.profile|dict(enabled=self.enabled.isChecked(),protocol=self.protocol.currentData(),base_url=self.url.text().strip(),model=self.model.text().strip(),
            light_model=self.light.text().strip(),auth=self.auth.currentText(),max_tokens=self.maximum.value(),context_limit=self.context.value(),reasoning=self.mode.currentData(),
            thinking_budget=self.budget.value(),reasoning_effort=self.effort.currentText())
        if self.key.text():profile['key_encrypted']=protect(self.key.text())
        config=copy.deepcopy(self.config);config['roles'][self.role]['model_profile']=profile
        resolve_api(config,self.role)
        return profile,config
    def save(self):
        try:self.profile,_=self.value();self.accept()
        except Exception as exc:QMessageBox.warning(self,'配置需要调整',str(exc))
    def test(self):
        if self.worker and self.worker.isRunning():return
        try:
            _,config=self.value();self.worker=ModelTest(self.root,self.role,config);self.worker.result.connect(self.result_label.setText);self.worker.start();self.result_label.setText('正在测试…')
        except Exception as exc:self.result_label.setText(str(exc))
    def done(self,result):
        if self.worker and self.worker.isRunning():QMessageBox.information(self,'正在测试','请等待本次连接测试结束。');return
        super().done(result)
