from __future__ import annotations
import copy
import json
from pathlib import Path
import re
import shutil
from PySide6.QtCore import Qt, QThread, Signal, QUrl, QSize
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QFormLayout, QLineEdit, QComboBox, QSpinBox, QCheckBox, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QFileDialog, QMessageBox, QPlainTextEdit, QInputDialog, QScrollArea,
    QStackedWidget, QFrame)
from .storage import protect, atomic_json
from .roles import list_roles
from .provider import Provider, endpoint
from .extensions import validate_servers
from .files import no_links, inside
from .chat_preferences import ChatPreferences
from .native_plugins import enabled
from .plugin_runtime import discover,parameters,load
from .plugin_preferences import PluginPreferences,PluginRowDelegate

def label(text):
    w = QLabel(text)
    w.setWordWrap(True)
    w.setObjectName('muted')
    return w

class ConnectionTest(QThread):
    result = Signal(str)
    def __init__(self, api):
        super().__init__()
        self.api = api
    def run(self):
        try:
            blocks, _, _ = Provider(self.api).complete('Reply briefly.', [{'role':'user','content':'Reply OK.'}], max_tokens=32)
            self.result.emit('连接成功 · 已收到模型响应（此测试产生少量 API 用量）。')
        except Exception as exc:
            self.result.emit(str(exc))

class Settings(QDialog):
    def __init__(self, config, role, parent=None):
        super().__init__(parent)
        self.config = config
        self.value = config.snapshot()
        self.current_role = role
        self.test_worker = None
        self.setWindowTitle('Sunday Blue · 设置')
        self.resize(980, 720);self.setMinimumSize(900,650)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20,18,20,16);layout.setSpacing(14)
        heading = QLabel('设置')
        heading.setObjectName('title')
        layout.addWidget(heading)
        content=QFrame();content.setObjectName('card');content_layout=QHBoxLayout(content);content_layout.setContentsMargins(0,0,0,0);content_layout.setSpacing(0)
        self.nav=QListWidget();self.nav.setObjectName('settingsNav');self.nav.setFixedWidth(176)
        self.tabs=QStackedWidget();content_layout.addWidget(self.nav);content_layout.addWidget(self.tabs,1);layout.addWidget(content,1)
        self.nav.currentRowChanged.connect(self.tabs.setCurrentIndex)
        self._api_page()
        self._permissions_page()
        self._plugins_page()
        self._mcp_page()
        self._skills_page()
        self._appearance_page()
        self._persona_page()
        self.nav.setCurrentRow(0)
        row = QHBoxLayout()
        row.addWidget(label('设置从下一次发送生效；运行中的任务使用启动时的配置。'))
        row.addStretch()
        cancel, save = QPushButton('取消'), QPushButton('保存设置')
        save.setObjectName('primary')
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self.save)
        row.addWidget(cancel); row.addWidget(save)
        layout.addLayout(row)

    def page(self, title):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(22, 20, 22, 18);layout.setSpacing(12)
        self.tabs.addWidget(page);self.nav.addItem(title)
        return layout

    def role_combo(self, selected=None):
        combo = QComboBox()
        for rid, name, desc, _ in list_roles(self.config.root):
            combo.addItem(f'{name} · {desc}', rid)
        combo.setCurrentIndex(next(i for i,r in enumerate(list_roles(self.config.root)) if r[0] == (selected or self.current_role)))
        return combo

    def _persona_page(self):
        layout = self.page('人格设定')
        manage = QPushButton('角色管理：创建、重命名、归档与删除')
        def open_manager():
            self.open_role_manager_requested = True
            self.reject()
        manage.clicked.connect(open_manager)
        layout.addWidget(manage)
        layout.addWidget(label('角色管理会关闭当前设置页；请先保存其他未提交的设置。也可从主界面角色栏直接打开。'))
        layout.addWidget(label('身份内核、性格反应、说话方式、角色关系。人格由你维护，工具技能交给插件。旧操作规程已归档，不进入对话。'))
        launch = QPushButton('打开人格编辑器')
        def open_editor():
            from .persona_preferences import PersonaDialog
            PersonaDialog(self.config.root, self.current_role, self).exec()
        launch.clicked.connect(open_editor)
        layout.addWidget(launch)
        layout.addWidget(label('编辑器中的“确认保存”立即写入并保留旧版；取消外层设置不会撤销已经确认的人格保存。'))
        layout.addStretch()

    def _api_page(self):
        layout = self.page('API 连接')
        layout.addWidget(label('直接连接你的 API 服务或中转站。可填写与 cc-switch 相同的地址、密钥和模型 ID；无需运行 Claude Desktop。'))
        form = QFormLayout()
        self.protocol = QComboBox()
        self.protocol.addItem('Anthropic Messages（Claude 接口）', 'anthropic')
        self.protocol.addItem('OpenAI 兼容 Chat Completions', 'openai')
        api = self.value['api']
        self.protocol.setCurrentIndex(0 if api['protocol']=='anthropic' else 1)
        self.url = QLineEdit(api['base_url'])
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText('已有加密密钥，留空保持' if api.get('key_encrypted') else '输入 API Key（本地代理可留空）')
        self.clear_key = QCheckBox('清除已保存的密钥')
        self.auth = QComboBox()
        self.auth.addItem('x-api-key（Anthropic 默认）','x-api-key')
        self.auth.addItem('Authorization: Bearer（中转站）','bearer')
        self.auth.setCurrentIndex(1 if api.get('auth')=='bearer' else 0)
        self.model = QLineEdit(api['model']); self.model.setPlaceholderText('填写服务商提供的准确模型 ID')
        self.tokens = QSpinBox(); self.tokens.setRange(256, 128000); self.tokens.setValue(api['max_tokens'])
        self.context = QSpinBox(); self.context.setRange(1024, 2000000); self.context.setSingleStep(1000); self.context.setValue(api['context_limit'])
        self.stream = QCheckBox('流式显示回复'); self.stream.setChecked(api.get('stream',True))
        self.thinking = QSpinBox(); self.thinking.setRange(0, 30000); self.thinking.setSingleStep(1024); self.thinking.setValue(int(api.get('thinking_budget',0) or 0))
        self.thinking.setSuffix(' tokens（0 = 关闭）')
        for title,w in [('接口协议',self.protocol),('请求地址',self.url),('API Key',self.key),('鉴权方式',self.auth),('模型 ID',self.model),('最大输出 token',self.tokens),('上下文容量（手动）',self.context),('扩展思考预算',self.thinking)]:
            form.addRow(title,w)
        form.addRow('',self.clear_key); form.addRow('',self.stream)
        layout.addLayout(form)
        self.test_status = label('扩展思考预算只对 Anthropic 协议模型生效；开启后思考块会随对话存档，并原样随后续请求回传。密钥使用 Windows DPAPI 加密保存；请求地址可填根地址、/v1 或完整端点。')
        self.test_button = QPushButton('测试连接 · 发送少量请求')
        self.test_button.clicked.connect(self.test)
        layout.addWidget(self.test_button); layout.addWidget(self.test_status); layout.addStretch()

    def api_value(self):
        api = dict(self.value['api'])
        api.update(protocol=self.protocol.currentData(), base_url=self.url.text().strip(), model=self.model.text().strip(),
                   auth=self.auth.currentData(), max_tokens=self.tokens.value(), context_limit=self.context.value(),
                   stream=self.stream.isChecked(), thinking_budget=self.thinking.value())
        endpoint(api['base_url'], api['protocol'])
        if self.clear_key.isChecked(): api['key_encrypted'] = ''
        if self.key.text().strip(): api['key_encrypted'] = protect(self.key.text().strip())
        return api

    def test(self):
        try:
            api = self.api_value()
            self.test_worker = ConnectionTest(api)
            self.test_button.setEnabled(False)
            self.test_status.setText('正在连接…')
            self.test_worker.result.connect(self.test_status.setText)
            self.test_worker.finished.connect(lambda: self.test_button.setEnabled(True))
            self.test_worker.start()
        except Exception as exc:
            QMessageBox.warning(self,'配置有误',str(exc))

    def _permissions_page(self):
        layout = self.page('角色权限')
        layout.addWidget(label('权限仅对所选角色生效。“信任”目录内的文件修改、创建、移动及删除自动确认，仍校验路径并备份修改/删除；普通可写目录逐次确认。'))
        self.permission_role = self.role_combo()
        self.permission_role.currentIndexChanged.connect(self.load_roots)
        layout.addWidget(self.permission_role)
        capabilities = QPushButton('配置此角色的能力、职责与按需加载')
        def configure_capabilities():
            from .capability_preferences import CapabilityDialog
            role = self.permission_role.currentData()
            dialog = CapabilityDialog(self.config.root, self.value, role, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.value['roles'][role] = dialog.value
        capabilities.clicked.connect(configure_capabilities)
        layout.addWidget(capabilities)
        models = QPushButton('配置此角色的独立模型与推理')
        def configure_model():
            from .model_preferences import RoleModelDialog
            role=self.permission_role.currentData()
            dialog=RoleModelDialog(self.config.root,self.value,role,self)
            if dialog.exec()==QDialog.DialogCode.Accepted:self.value['roles'][role]['model_profile']=dialog.profile
        models.clicked.connect(configure_model)
        layout.addWidget(models)
        self.roots = QListWidget()
        layout.addWidget(self.roots)
        row = QHBoxLayout()
        read, write, remove = QPushButton('＋ 只读目录'), QPushButton('＋ 可写目录'), QPushButton('移除所选')
        read.clicked.connect(lambda:self.add_root(False)); write.clicked.connect(lambda:self.add_root(True)); remove.clicked.connect(self.remove_root)
        for w in (read,write,remove): row.addWidget(w)
        layout.addLayout(row)
        trust=QPushButton('信任 / 取消信任所选工作区');trust.clicked.connect(self.toggle_trust);layout.addWidget(trust)
        layout.addWidget(label('内置工具支持文件/文件夹删除，删除前备份。信任不适用于持久记忆更新或 MCP。无终端或任意脚本工具；软件自身目录不可授权。'))
        self.load_roots()

    def load_roots(self):
        self.roots.clear()
        for root in self.value['roles'][self.permission_role.currentData()]['roots']:
            self.roots.addItem(('信任 · 自动确认  ' if root.get('trusted') and root.get('write') else '读写 · 需确认  ' if root.get('write') else '只读  ') + root['path'])

    def toggle_trust(self):
        index=self.roots.currentRow()
        if index<0:return
        root=self.value['roles'][self.permission_role.currentData()]['roots'][index]
        if not root.get('write'):
            QMessageBox.information(self,'只读目录','请先添加为可写目录，再设置信任。');return
        root['trusted']=not root.get('trusted',False);self.load_roots();self.roots.setCurrentRow(index)

    def add_root(self, write):
        path = QFileDialog.getExistingDirectory(self,'选择该角色可访问的目录')
        if not path: return
        try:
            p = Path(path).resolve()
            no_links(Path(path))
            if inside(p,self.config.root) or inside(self.config.root,p):
                raise ValueError('请选择软件目录以外的具体工作目录，不能授权软件自身或其上层目录。')
            if str(p).startswith('\\\\'):
                raise ValueError('暂不支持网络目录。')
            roots = self.value['roles'][self.permission_role.currentData()]['roots']
            roots[:] = [r for r in roots if Path(r['path'])!=p]
            roots.append({'path':str(p),'write':write})
            self.load_roots()
        except Exception as exc:
            QMessageBox.warning(self,'无法授权',str(exc))

    def remove_root(self):
        index = self.roots.currentRow()
        if index >= 0:
            del self.value['roles'][self.permission_role.currentData()]['roots'][index]
            self.load_roots()

    def _plugins_page(self):
        layout = self.page('插件')
        layout.addWidget(label('独立插件按所选角色启停；时间上下文与时段寒暄互不依赖。JSON 提示词插件仍可导入。'))
        self.features = {}
        for k,text in [('files','文件工作台 · 目录权限与差异审阅'),('memory','持久记忆 · 同角色跨会话共享'),('mcp','MCP 工具桥 · 启用下面 MCP 页的已配置服务')]:
            box = QCheckBox(text); box.setChecked(self.value['features'].get(k,False)); self.features[k]=box; layout.addWidget(box)
        self.plugin_role = self.role_combo()
        self.plugin_role.currentIndexChanged.connect(self.load_plugins)
        layout.addWidget(self.plugin_role)
        self.plugins = QListWidget(); self.plugins.itemChanged.connect(self.sync_plugins); layout.addWidget(self.plugins)
        self.plugins.setItemDelegate(PluginRowDelegate(self.plugins))
        self.plugins.setStyleSheet('QListWidget::item {padding:6px 4px; margin:2px 0;} QListWidget::indicator {width:0; height:0;}')
        add = QPushButton('导入提示词插件 .json'); add.clicked.connect(self.import_plugin); layout.addWidget(add)
        layout.addWidget(label('每行设置按钮打开该角色的插件参数。保存设置后，下一条消息生效。Python 插件拥有当前用户权限，仅安装信任的插件。'))
        self.load_plugins()

    def load_plugins(self):
        self.plugins.blockSignals(True); self.plugins.clear()
        selected = self.value['roles'][self.plugin_role.currentData()]['plugins']
        for pid,meta in discover(self.config.root).items():
            item=QListWidgetItem(meta['name']+' · '+meta['version'])
            item.setData(Qt.ItemDataRole.UserRole,('native',pid));item.setToolTip(meta['description'])
            item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if enabled(self.value,self.plugin_role.currentData(),pid) else Qt.CheckState.Unchecked)
            self.plugins.addItem(item)
            self.plugin_row(item,meta,lambda p=pid:self.configure_plugin(p))
        for p in sorted((self.config.root/'extensions'/'plugins').glob('*.json')):
            item = QListWidgetItem(p.stem)
            item.setData(Qt.ItemDataRole.UserRole,('prompt',p.stem))
            item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if p.stem in selected else Qt.CheckState.Unchecked)
            self.plugins.addItem(item)
            self.plugin_row(item,{'name':p.stem,'version':'提示词','description':'按角色启用与配置提示词'},lambda pid=p.stem:self.configure_prompt(pid))
        self.plugins.blockSignals(False)

    def plugin_row(self,item,meta,configure_callback):
        row=QWidget(self.plugins.viewport());line=QHBoxLayout(row);line.setContentsMargins(6,2,6,2)
        checkbox=QCheckBox(meta['name']+' · '+meta['version']);checkbox.setChecked(item.checkState()==Qt.CheckState.Checked)
        checkbox.setToolTip(meta['description']);checkbox.setEnabled(not meta.get('error'))
        checkbox.toggled.connect(lambda checked,i=item:i.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked))
        line.addWidget(checkbox,1)
        configure=QPushButton('设置');configure.setEnabled(not meta.get('error'));configure.clicked.connect(lambda:configure_callback());line.addWidget(configure)
        item.setText('');item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
        row.ensurePolished();item.setSizeHint(row.sizeHint()+QSize(0,16));self.plugins.setItemWidget(item,row)

    def configure_prompt(self,pid):
        try:
            role=self.value['roles'][self.plugin_role.currentData()]
            source=json.loads((self.config.root/'extensions/plugins'/(pid+'.json')).read_text(encoding='utf-8-sig'))
            meta={'name':pid,'schema':{'prompt':{'type':'text','description':'该角色使用的提示词','default':source.get('prompt','')}}}
            dialog=PluginPreferences(meta,role.get('plugin_settings',{}).get(pid,{'prompt':source.get('prompt','')}),self)
            if dialog.exec()==QDialog.DialogCode.Accepted:role.setdefault('plugin_settings',{})[pid]=dialog.values
        except (ValueError,OSError) as exc:QMessageBox.warning(self,'插件配置错误',str(exc))

    def configure_plugin(self,pid):
        role=self.plugin_role.currentData();meta=discover(self.config.root)[pid]
        # Optional per-plugin control panel embedded in the SAME settings dialog
        # (PLUGIN_SPEC section 3b). Only plugins that implement settings_extra
        # get one; it manages the plugin's own background components only.
        extra=None
        module=load(pid,self.config.root)
        if hasattr(module,'settings_extra'):
            extra=module.settings_extra(self.config.root)
        dialog=PluginPreferences(meta,parameters(self.value,role,pid,self.config.root),
                                 self,extra_widget=extra)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            self.value['roles'][role].setdefault('plugin_settings',{})[pid]=dialog.values

    def sync_plugins(self):
        role=self.value['roles'][self.plugin_role.currentData()]
        role['plugins']=[];role['native_plugins']={}
        for i in range(self.plugins.count()):
            item=self.plugins.item(i);kind,pid=item.data(Qt.ItemDataRole.UserRole)
            checked=item.checkState()==Qt.CheckState.Checked
            if kind=='native':role['native_plugins'][pid]=checked
            elif checked:role['plugins'].append(pid)

    def import_plugin(self):
        path,_ = QFileDialog.getOpenFileName(self,'导入插件',filter='JSON (*.json)')
        if not path: return
        try:
            p = Path(path)
            if p.stat().st_size > 65536: raise ValueError('插件文件最大 64 KiB。')
            obj = json.loads(p.read_text(encoding='utf-8-sig'))
            name = obj.get('id','')
            if not re.fullmatch(r'[A-Za-z0-9_-]+',name) or not isinstance(obj.get('prompt'),str): raise ValueError('需要 id（字母数字短横线）和 prompt 字符串。')
            dest = self.config.root/'extensions'/'plugins'/(name+'.json')
            if dest.exists() or dest.with_suffix('').exists(): raise ValueError('相同 ID 已存在，请先修改 ID。')
            atomic_json(dest,obj)
            self.load_plugins()
        except Exception as exc: QMessageBox.warning(self,'导入失败',str(exc))

    def _mcp_page(self):
        layout = self.page('MCP')
        layout.addWidget(label('本地 stdio MCP 配置（JSON 数组）。仅对 roles 中列出的角色启用。启动服务及每次工具调用均需确认。外部进程不受内置目录权限沙箱约束。'))
        self.mcp = QPlainTextEdit(json.dumps(self.value['mcp_servers'],ensure_ascii=False,indent=2))
        self.mcp.setPlaceholderText('[{"name":"my-server","command":"C:/path/node.exe","args":["C:/path/server.js"],"roles":["rui"],"enabled":true}]')
        layout.addWidget(self.mcp)
        layout.addWidget(label('字段：name、command、args、roles、enabled；可选 cwd、env。env 会以明文存储，请优先让服务自行读取系统凭据。本版支持 tools/list、tools/call；不支持远程 HTTP、OAuth、resources、prompts。'))
        example = QPushButton('插入禁用的配置示例')
        def insert():
            try:
                data = json.loads(self.mcp.toPlainText())
                data.append({'name':'example','command':'C:/path/to/node.exe','args':['C:/path/to/server.js'],'roles':['rui'],'enabled':False})
                self.mcp.setPlainText(json.dumps(data,ensure_ascii=False,indent=2))
            except Exception as exc: QMessageBox.warning(self,'JSON 格式错误',str(exc))
        example.clicked.connect(insert); layout.addWidget(example)

    def _skills_page(self):
        layout = self.page('Skills')
        layout.addWidget(label('导入包含 SKILL.md 的文件夹，副本保存在本软件 extensions/skills。勾选后，角色在下一次发送时加载指令。当前版本只加载 SKILL.md，不自动执行脚本或读取引用附件。'))
        self.skill_role = self.role_combo(); self.skill_role.currentIndexChanged.connect(self.load_skills); layout.addWidget(self.skill_role)
        self.skills = QListWidget(); self.skills.itemChanged.connect(self.sync_skills); layout.addWidget(self.skills)
        add = QPushButton('＋ 导入 Skill 文件夹'); add.clicked.connect(self.import_skill); layout.addWidget(add)
        self.load_skills()

    def load_skills(self):
        self.skills.blockSignals(True); self.skills.clear()
        enabled = self.value['roles'][self.skill_role.currentData()]['skills']
        for p in sorted((self.config.root/'extensions'/'skills').glob('*/SKILL.md')):
            item = QListWidgetItem(p.parent.name); item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if p.parent.name in enabled else Qt.CheckState.Unchecked); self.skills.addItem(item)
        self.skills.blockSignals(False)

    def sync_skills(self):
        self.value['roles'][self.skill_role.currentData()]['skills'] = [self.skills.item(i).text() for i in range(self.skills.count()) if self.skills.item(i).checkState()==Qt.CheckState.Checked]

    def import_skill(self):
        folder = QFileDialog.getExistingDirectory(self,'选择含 SKILL.md 的文件夹')
        if not folder: return
        try:
            p=Path(folder); no_links(p/'SKILL.md')
            if not (p/'SKILL.md').is_file(): raise ValueError('未找到 SKILL.md。')
            if not re.fullmatch(r'[A-Za-z0-9_-]+',p.name): raise ValueError('文件夹名请使用字母、数字、短横线或下划线。')
            if (p/'SKILL.md').stat().st_size>65536: raise ValueError('SKILL.md 最大 64 KiB。')
            dest=self.config.root/'extensions'/'skills'/p.name
            if dest.exists(): raise ValueError('同名 Skill 已存在，请改名后导入。')
            # Only the supported entry point is copied; no external runtime dependency.
            dest.mkdir(); shutil.copy2(p/'SKILL.md',dest/'SKILL.md')
            self.load_skills()
        except Exception as exc: QMessageBox.warning(self,'导入失败',str(exc))

    def _appearance_page(self):
        outer = self.page('外观 / 数据')
        scroll=QScrollArea();scroll.setWidgetResizable(True);outer.addWidget(scroll)
        content=QWidget();layout=QVBoxLayout(content);scroll.setWidget(content)
        self.chat_preferences=ChatPreferences(self.config.root,self.value.get('chat_display',{}),self.value.get('ui_display',{}),self.current_role)
        layout.addWidget(self.chat_preferences)
        self.close_to_tray=QCheckBox('关闭窗口后留在系统托盘，继续后台运行')
        self.close_to_tray.setChecked(self.value.get('close_to_tray',False));layout.addWidget(self.close_to_tray)
        layout.addWidget(label('无需打包；托盘可重新打开或退出。电脑休眠、注销或关机不会继续生成回复。'))
        layout.addWidget(label('头像与立绘是普通 PNG 文件，不需要重新编译软件。替换后点击主界面的“刷新素材”。'))
        layout.addWidget(QLabel('assets/roles/<角色 ID>/avatar.png\n推荐：512 × 512，正方形\n\nassets/roles/<角色 ID>/portrait.png\n推荐：1200 × 1800，透明背景，人物居中\n\n软件会等比例缩放；头像建议避免边缘重要内容。'))
        for title,relative in [('打开素材目录','assets/roles'),('打开数据目录','data'),('打开使用说明','README.md')]:
            button=QPushButton(title)
            button.clicked.connect(lambda checked=False,p=relative:QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.config.root/p)))); layout.addWidget(button)
        layout.addWidget(label('聊天数据库、角色记忆、备份、设置都在 data 内。备份时关闭软件并复制整个 Sunday_Blue 文件夹。API 密钥只能由原 Windows 账户解密。'))
        layout.addStretch()

    def save(self):
        try:
            self.value['chat_display']=self.chat_preferences.value()
            self.value['ui_display']=self.chat_preferences.ui_value()
            self.value['close_to_tray']=self.close_to_tray.isChecked()
            self.value['api']=self.api_value()
            self.value['mcp_servers']=validate_servers(json.loads(self.mcp.toPlainText()), self.config.root)
            self.value['features']={k:w.isChecked() for k,w in self.features.items()}
            self.config.save(self.value)
            self.accept()
        except Exception as exc: QMessageBox.warning(self,'无法保存',str(exc))

    def done(self, result):
        if self.test_worker and self.test_worker.isRunning():
            QMessageBox.information(self,'正在测试','请等待连接测试结束后关闭设置。')
            return
        super().done(result)
