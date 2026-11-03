from __future__ import annotations
import json
import math
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, Signal, QSize
from PySide6.QtGui import QIcon, QPixmap, QColor, QPainter, QPen, QLinearGradient, QFont, QTextOption
from PySide6.QtWidgets import (QApplication, QWidget, QFrame, QLabel, QPushButton, QHBoxLayout,
    QVBoxLayout, QListWidget, QListWidgetItem, QScrollArea, QPlainTextEdit, QTextBrowser,
    QProgressBar, QDialog, QMessageBox, QInputDialog, QFileDialog, QSizeGrip, QSizePolicy, QMenu)
from .storage import ROLES, Store, plain
from .agent import Agent
from .settings import Settings
from .theme import style_for

# Re-export names for existing imports/tests; implementation lives in ui_components.
from .ui_components import text_label, button, TitleBar, Composer, Portrait, Bubble

class MainWindow(QWidget):
    def __init__(self,config):
        super().__init__()
        self.config=config; self.store=Store(config.data)
        self.store.recover_interrupted_tools()
        self.role='rui'; self.sid=None
        self.current_by_role={}
        for rid,sid in config.value.get('active_sessions',{}).items():
            saved=self.store.session(sid)
            if saved and saved['role']==rid:self.current_by_role[rid]=sid
        self.workers={}; self.statuses={}; self.drafts={}; self.errors={}
        self.pending=None; self.pending_text=''; self.history_limit=120
        self.chat_bubbles=[]
        self.setWindowTitle('Sunday Blue')
        self.setWindowIcon(QIcon(str(config.root/'assets'/'app.ico')))
        self.setWindowFlags(Qt.WindowType.Window|Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(1440,900); self.setMinimumSize(1100,720)
        self.ui_theme=config.value.get('ui_theme','dark'); self._apply_theme()
        outer=QVBoxLayout(self); outer.setContentsMargins(0,0,0,0)
        shell=QWidget(); shell.setObjectName('shell'); outer.addWidget(shell)
        main=QVBoxLayout(shell); main.setContentsMargins(1,1,1,1); main.setSpacing(0)
        top=TitleBar(); top.setObjectName('top'); top.setFixedHeight(65)
        bar=QHBoxLayout(top); bar.setContentsMargins(24,8,12,8)
        bar.addWidget(text_label('◇  SUNDAY BLUE','brand'))
        bar.addSpacing(18); bar.addWidget(text_label('YOUR PERSONAL SPACE','eyebrow')); bar.addStretch()
        bar.addWidget(button('⚙  设置',self.settings,'ghost'))
        self.theme_button=button('☀  浅色' if self.ui_theme=='dark' else '☾  暗色',self.toggle_theme,'ghost'); bar.addWidget(self.theme_button)
        bar.addSpacing(10)
        for title,fn,obj in [('—',self.showMinimized,'ghost'),('□',self.maximize,'ghost'),('×',self.close,'close')]:
            b=button(title,fn,obj); b.setFixedSize(34,32); bar.addWidget(b)
        main.addWidget(top)
        body=QHBoxLayout(); body.setSpacing(0); main.addLayout(body,1)
        self._sidebar(body); self._chat(body); self._character(body); self._rail(body)
        foot=QHBoxLayout(); foot.setContentsMargins(16,3,3,3)
        foot.addWidget(text_label('SUNDAY BLUE  /  0.1','eyebrow')); foot.addStretch()
        self.footer=text_label('本地会话 · 独立记忆 · 由你掌控','muted'); foot.addWidget(self.footer)
        grip=QSizeGrip(self); grip.setFixedSize(16,16); foot.addWidget(grip); main.addLayout(foot)
        last=config.value.get('last_role','rui')
        self.switch_role(last if last in {r[0] for r in ROLES} else 'rui')

    def maximize(self):
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def _apply_theme(self):
        self.setStyleSheet(style_for(self.ui_theme))
        if hasattr(self, 'theme_button'):
            self.theme_button.setText('☀  浅色' if self.ui_theme == 'dark' else '☾  暗色')

    def toggle_theme(self):
        self.ui_theme = 'light' if self.ui_theme == 'dark' else 'dark'
        self._apply_theme()
        self.refresh_art()
        self.render()
        self.config.value['ui_theme'] = self.ui_theme
        self.config.save()

    def _sidebar(self,body):
        frame=QFrame(); frame.setObjectName('sidebar'); frame.setFixedWidth(224)
        layout=QVBoxLayout(frame); layout.setContentsMargins(18,25,16,16); layout.setSpacing(15)
        layout.addWidget(text_label('WORKSPACE','section'))
        self.side_name=text_label('Rui','title'); layout.addWidget(self.side_name)
        layout.addWidget(button('＋  开始新对话',self.new_session,'primary'))
        layout.addSpacing(12); layout.addWidget(text_label('会话记录 / CONVERSATIONS','eyebrow'))
        self.sessions_list=QListWidget(); self.sessions_list.currentItemChanged.connect(self.select_history)
        self.sessions_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.sessions_list.customContextMenuRequested.connect(self._sidebar_context_menu)
        layout.addWidget(self.sessions_list,1)
        row=QHBoxLayout()
        row.addWidget(button('重命名',self.rename_session,'ghost')); row.addWidget(button('导出',self.export_session,'ghost')); layout.addLayout(row)
        layout.addWidget(text_label('每一次对话，都有迹可循。','muted'))
        body.addWidget(frame)

    def _chat(self,body):
        panel=QWidget(); layout=QVBoxLayout(panel); layout.setContentsMargins(24,22,24,14); layout.setSpacing(15)
        row=QHBoxLayout(); names=QVBoxLayout()
        self.chat_title=text_label('Rui','title'); names.addWidget(self.chat_title)
        self.chat_status=text_label('就绪','muted'); names.addWidget(self.chat_status); row.addLayout(names); row.addStretch()
        self.session_menu=QMenu(self)
        self._menu_fork_target=self.sid
        self.fork_action=self.session_menu.addAction('创建分支'); self.fork_action.triggered.connect(self._menu_fork)
        self.session_button=button('⋮',lambda:None,'ghost'); self.session_button.setFixedSize(34,32)
        self.session_button.clicked.connect(lambda:self._show_session_menu())
        row.addWidget(self.session_button); layout.addLayout(row)
        self.chat_scroll=QScrollArea(); self.chat_scroll.setWidgetResizable(True)
        self.chat_content=QWidget(); self.chat_content.setObjectName('chatContent'); self.chat_content.setStyleSheet('QWidget#chatContent { background:transparent; }')
        self.chat_layout=QVBoxLayout(self.chat_content); self.chat_layout.setContentsMargins(0,12,5,12); self.chat_layout.setSpacing(18)
        self.chat_scroll.setWidget(self.chat_content); layout.addWidget(self.chat_scroll,1)
        self.notice=text_label('','muted'); self.notice.setWordWrap(True); self.notice.hide(); layout.addWidget(self.notice)
        composer=QFrame(); composer.setObjectName('composer'); c=QVBoxLayout(composer); c.setContentsMargins(14,10,14,10)
        self.input=Composer(); self.input.setObjectName('input'); self.input.setPlaceholderText('今天想聊些什么？也可以交给我一项任务。输入 /compact 可压缩当前上下文。')
        self.input.setFixedHeight(80); self.input.send.connect(self.send); c.addWidget(self.input)
        actions=QHBoxLayout(); actions.addWidget(text_label('Enter 发送  ·  Shift + Enter 换行','muted')); actions.addStretch()
        self.retry_button=button('重试',self.retry,'ghost'); actions.addWidget(self.retry_button)
        self.stop_button=button('停止',self.stop,'ghost'); actions.addWidget(self.stop_button)
        self.send_button=button('发送  ↗',self.send,'primary'); actions.addWidget(self.send_button); c.addLayout(actions); layout.addWidget(composer)
        body.addWidget(panel,1)

    def _character(self,body):
        panel=QWidget(); panel.setFixedWidth(292)
        layout=QVBoxLayout(panel); layout.setContentsMargins(0,24,18,16); layout.setSpacing(12)
        row=QHBoxLayout(); row.addWidget(text_label('角色档案','section')); row.addStretch(); row.addWidget(button('刷新素材',self.refresh_art,'ghost')); layout.addLayout(row)
        self.portrait=Portrait(self.config.root); layout.addWidget(self.portrait,1)
        self.role_description=text_label('','muted'); self.role_description.setWordWrap(True); layout.addWidget(self.role_description)
        layout.addSpacing(5)
        self.context_label=text_label('上下文 · 等待第一条消息','muted'); self.context_label.setWordWrap(True); layout.addWidget(self.context_label)
        self.context_progress=QProgressBar(); self.context_progress.setRange(0,100); self.context_progress.setTextVisible(False); self.context_progress.setFixedHeight(4); layout.addWidget(self.context_progress)
        layout.addWidget(button('查看持久记忆',self.memory_dialog,'ghost'))
        self.permission_label=text_label('','muted'); self.permission_label.setWordWrap(True); layout.addWidget(self.permission_label)
        body.addWidget(panel)

    def _rail(self,body):
        rail=QFrame(); rail.setObjectName('rail'); rail.setFixedWidth(108)
        layout=QVBoxLayout(rail); layout.setContentsMargins(10,22,10,12); layout.setSpacing(12)
        layout.addWidget(text_label('CHARACTERS','eyebrow'),0,Qt.AlignmentFlag.AlignHCenter)
        scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner=QWidget(); inner.setObjectName('roleContent'); inner.setStyleSheet('QWidget#roleContent { background:transparent; }'); items=QVBoxLayout(inner); items.setContentsMargins(0,0,0,0); items.setSpacing(10)
        self.role_buttons={}
        for rid,name,desc,color in ROLES:
            b=QPushButton(); b.setObjectName('role'); b.setCheckable(True); b.setFixedSize(79,92)
            b.setToolTip(name+' · '+desc); b.clicked.connect(lambda checked=False,r=rid:self.switch_role(r))
            col=QVBoxLayout(b); col.setContentsMargins(6,6,6,6); col.setSpacing(4)
            avatar=QLabel(); avatar.setFixedSize(52,52); avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
            avatar.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            avatar.setStyleSheet(f'background:#22344c; border:1px solid {color}; border-radius:8px;')
            col.addWidget(avatar,0,Qt.AlignmentFlag.AlignHCenter)
            label=text_label(name); label.setAlignment(Qt.AlignmentFlag.AlignCenter); label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents); col.addWidget(label)
            b.avatar=avatar; b.name_label=label
            self.role_buttons[rid]=b; items.addWidget(b)
        items.addStretch(); scroll.setWidget(inner); layout.addWidget(scroll); body.addWidget(rail)
        self.refresh_art()

    def refresh_art(self):
        for rid,b in getattr(self,'role_buttons',{}).items():
            pix=QPixmap(str(self.config.root/'assets'/'roles'/rid/'avatar.png'))
            b.avatar.setPixmap(pix.scaled(48,48,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
        if hasattr(self,'portrait'): self.portrait.set_role(self.role)

    def save_draft(self):
        if self.sid: self.drafts[self.sid]=self.input.toPlainText()

    def switch_role(self,role):
        self.save_draft(); self.role=role
        rows=self.store.sessions(role)
        self.sid=self.current_by_role.get(role) or (rows[0]['id'] if rows else self.store.create(role))
        self.current_by_role[role]=self.sid
        self.history_limit=120
        self.refresh_sessions(); self.render()
        name=next(r for r in ROLES if r[0]==role)
        self.side_name.setText(name[1]); self.chat_title.setText(name[1]); self.role_description.setText(name[2]+'\n人格持续保留 · 同角色共享记忆')
        self.portrait.set_role(role)
        for rid,b in self.role_buttons.items(): b.setChecked(rid==role)
        self.input.setPlainText(self.drafts.get(self.sid,''))
        self.input.setFocus(); self.update_state()
        if self.sid in self.errors:self.show_notice(self.errors[self.sid])

    def refresh_sessions(self):
        self.sessions_list.blockSignals(True); self.sessions_list.clear()
        for s in self.store.sessions(self.role):
            item=QListWidgetItem(('● ' if s['id'] in self.workers else '')+s['title'])
            item.setData(Qt.ItemDataRole.UserRole,s['id']); item.setToolTip(s['created']+'\n'+s['id']); self.sessions_list.addItem(item)
            if s['id']==self.sid: self.sessions_list.setCurrentItem(item)
        self.sessions_list.blockSignals(False)

    def select_history(self,item,previous=None):
        if not item:return
        self.save_draft(); self.sid=item.data(Qt.ItemDataRole.UserRole); self.current_by_role[self.role]=self.sid; self.history_limit=120
        self.input.setPlainText(self.drafts.get(self.sid,'')); self.render(); self.update_state()
        if self.sid in self.errors:self.show_notice(self.errors[self.sid])

    def new_session(self):
        self.save_draft(); self.sid=self.store.create(self.role); self.current_by_role[self.role]=self.sid
        self.input.clear(); self.refresh_sessions(); self.render(); self.update_state()

    def fork_session(self):
        # Public entry (header button / tests): branch the currently active session.
        self._menu_fork_target=self.sid; self._menu_fork()

    def _show_session_menu(self):
        # Header "⋯": branch the active session, disabled while a worker is running.
        self._menu_fork_target=self.sid
        self.fork_action.setEnabled(self.sid not in self.workers)
        self.session_menu.exec(self.session_button.mapToGlobal(self.session_button.rect().bottomLeft()))

    def _sidebar_context_menu(self, pos):
        # Right-click on a session row: branch that specific session.
        items=self.sessions_list.itemsAt(pos)
        if not items:return
        sid=items[0].data(Qt.ItemDataRole.UserRole)
        self._menu_fork_target=sid
        self.fork_action.setEnabled(sid not in self.workers)
        self.session_menu.exec(self.sessions_list.mapToGlobal(pos))

    def _menu_fork(self):
        sid=self._menu_fork_target
        if sid in self.workers:
            self.show_notice('请等待该会话当前回复完成或停止后再创建分支。'); return
        self.save_draft()
        self.sid=self.store.fork(sid); self.current_by_role[self.role]=self.sid
        self.input.clear(); self.refresh_sessions(); self.render(); self.update_state()
        self.show_notice('已创建独立分支；原对话保留，角色持久记忆共享。')

    def rename_session(self):
        title,ok=QInputDialog.getText(self,'会话名称','名称：',text=self.store.session(self.sid)['title'])
        if ok and title.strip(): self.store.update(self.sid,title=title.strip()[:100]); self.refresh_sessions()

    def export_session(self):
        path,_=QFileDialog.getSaveFileName(self,'导出对话',str(self.config.root/'conversation.md'),'Markdown (*.md)')
        if not path:return
        data=['# '+self.store.session(self.sid)['title']]
        for m in self.store.messages(self.sid):
            data.append('\n## '+m['role']+' · '+m['created']+'\n\n'+(plain(m['content']) or json.dumps(m['content'],ensure_ascii=False,indent=2)))
        try: Path(path).write_text('\n'.join(data),encoding='utf-8'); self.show_notice('对话已导出。')
        except OSError as exc: QMessageBox.warning(self,'导出失败',str(exc))

    def clear_chat(self):
        self.pending=None; self.pending_text=''; self.chat_bubbles.clear()
        while self.chat_layout.count():
            item=self.chat_layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()

    def render(self):
        self.clear_chat(); self.notice.hide()
        messages=self.store.messages(self.sid)
        if not messages:
            welcome=QFrame(); col=QVBoxLayout(welcome); col.setContentsMargins(24,70,24,35); col.setSpacing(20)
            name=next(r[1] for r in ROLES if r[0]==self.role)
            col.addWidget(text_label('A LITTLE SPACE, JUST FOR YOU','eyebrow'))
            col.addWidget(text_label(f'与 {name} 开始一段对话。','title'))
            intro=text_label('日常、计划，或一个还没整理好的想法。\n从这里开始，记忆会慢慢延续。','muted'); intro.setWordWrap(True); col.addWidget(intro)
            if not self.config.value['api']['model']:
                col.addWidget(button('设置你的 API 连接  →',self.settings,'primary'))
            self.chat_layout.addWidget(welcome)
        if len(messages)>self.history_limit:
            self.chat_layout.addWidget(button(f'加载更早的消息（还有 {len(messages)-self.history_limit} 条）',self.more_history,'ghost'))
        for m in messages[-self.history_limit:]:
            text=plain(m['content'])
            if text:self.add_bubble(text,m['role']=='user')
            if isinstance(m['content'],list):
                for block in m['content']:
                    if block['type']=='tool_use':
                        self.add_tool('↳ '+block['name'],json.dumps(block['input'],ensure_ascii=False,indent=2))
                    elif block['type']=='tool_result':
                        self.add_tool('✓ 工具回执' if not block.get('is_error') else '! 工具错误',block['content'])
        self.chat_layout.addStretch(1)
        worker=self.workers.get(self.sid)
        if worker and getattr(worker,'live_text',''):
            self.on_text(self.sid,'',restore=worker.live_text)
        QTimer.singleShot(30,self.scroll_bottom)
        self.update_context()

    def more_history(self):
        self.history_limit+=120; self.render()

    def _chat_width(self):
        # Usable chat column: full dialog minus the fixed side panels.
        return max(320, self.width() - 224 - 292 - 108)

    def add_bubble(self,text,user=False):
        row=QWidget(); line=QHBoxLayout(row); line.setContentsMargins(0,0,0,0)
        row.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Maximum)
        col=QVBoxLayout(); col.setSpacing(5)
        col.setAlignment(Qt.AlignmentFlag.AlignTop)
        name='你' if user else next(r[1] for r in ROLES if r[0]==self.role)
        caption=text_label(name,'muted'); caption.setFixedHeight(20); caption.setAlignment(Qt.AlignmentFlag.AlignRight if user else Qt.AlignmentFlag.AlignLeft); col.addWidget(caption)
        bubble=Bubble(text,user,light=self.ui_theme=='light',width=self._chat_width())
        col.addWidget(bubble,0,Qt.AlignmentFlag.AlignRight if user else Qt.AlignmentFlag.AlignLeft)
        self.chat_bubbles.append(bubble)
        if user:line.addStretch(1)
        line.addLayout(col,7)
        if not user:line.addStretch(1)
        self.chat_layout.insertWidget(max(0,self.chat_layout.count()-1) if self.chat_layout.count() and self.chat_layout.itemAt(self.chat_layout.count()-1).spacerItem() else self.chat_layout.count(),row)
        return bubble

    def add_tool(self,title,detail):
        b=button(title+'  ·  查看',lambda:self.show_document(title,detail),'ghost')
        b.setMaximumWidth(330); self.chat_layout.addWidget(b,0,Qt.AlignmentFlag.AlignLeft)

    def scroll_bottom(self):
        bar=self.chat_scroll.verticalScrollBar(); bar.setValue(bar.maximum())

    def show_notice(self,text):
        self.notice.setText(text); self.notice.show()

    def send(self):
        if self.sid in self.workers:return
        text=self.input.toPlainText().strip()
        if not text:return
        if not self.config.value['api']['model']:
            self.settings(); return
        self.store.add(self.sid,'user',text)
        if self.store.session(self.sid)['title']=='新对话':self.store.update(self.sid,title=text.replace('\n',' ')[:26])
        self.input.clear(); self.drafts[self.sid]=''; self.render(); self.start_worker()

    def retry(self):
        if self.sid in self.workers:return
        msgs=self.store.messages(self.sid,context=True)
        if not msgs or msgs[-1]['role']!='user':self.show_notice('没有等待回复的消息。');return
        self.start_worker()

    def start_worker(self):
        # Normal chat turns. Typing "/compact" in the composer is intercepted inside the agent.
        sid=self.sid
        self.errors.pop(sid,None)
        worker=Agent(self.config.root,self.config.snapshot(),self.store,sid)
        worker.live_text=''; self.workers[sid]=worker
        worker.text.connect(self.on_text); worker.status.connect(self.on_status); worker.changed.connect(self.on_changed)
        worker.failed.connect(self.on_error); worker.approval.connect(self.on_approval)
        worker.finished.connect(lambda s=sid,w=worker:self.on_finished(s,w))
        self.notice.hide(); self.statuses[sid]='准备请求…'; worker.start(); self.update_state(); self.refresh_sessions()

    def on_text(self,sid,text,restore=None):
        worker=self.workers.get(sid)
        if worker and restore is None:worker.live_text+=text
        if sid!=self.sid:return
        if self.pending is None:self.pending=self.add_bubble('…')
        self.pending_text=restore if restore is not None else self.pending_text+text
        self.pending.set_text(self.pending_text)
        self.scroll_bottom()

    def on_changed(self,sid):
        worker=self.workers.get(sid)
        if worker:worker.live_text=''
        if sid==self.sid:self.render()

    def on_status(self,sid,text):
        self.statuses[sid]=text
        if sid==self.sid:self.chat_status.setText(text)

    def on_error(self,sid,error):
        self.statuses[sid]='请求失败'
        self.errors[sid]=error
        # Error is visible even when another role is selected.
        self.store.audit(self.store.session(sid)['role'],sid,'request_failed',error)
        if sid==self.sid:self.show_notice(error)
        else:self.footer.setText('某个会话请求失败 · 切回对应角色查看')
        worker=self.workers.get(sid)
        if worker:worker.error_text=error

    def on_finished(self,sid,worker):
        self.workers.pop(sid,None)
        if sid==self.sid:
            self.render()
            if getattr(worker,'error_text',None):self.show_notice(worker.error_text)
        self.refresh_sessions(); self.update_state(); worker.deleteLater()

    def on_approval(self,sid,item):
        if item.event.is_set():return
        role=self.store.session(sid)['role']
        dlg=QDialog(self); dlg.setWindowTitle(f'{role} · {item.title}'); dlg.resize(850,620)
        layout=QVBoxLayout(dlg)
        heading=text_label(role.upper()+' / '+item.title,'title');layout.addWidget(heading)
        sub=QLabel(item.subject);sub.setWordWrap(True);sub.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse);layout.addWidget(sub)
        view=QPlainTextEdit(item.detail);view.setReadOnly(True);view.setStyleSheet('font-family:Consolas; font-size:12px;');layout.addWidget(view)
        row=QHBoxLayout();row.addStretch();row.addWidget(button('拒绝',dlg.reject));row.addWidget(button('确认执行',dlg.accept,'primary'));layout.addLayout(row)
        item.accepted=dlg.exec()==QDialog.DialogCode.Accepted
        item.event.set()

    def stop(self):
        worker=self.workers.get(self.sid)
        if worker:
            worker.stop();self.statuses[self.sid]='正在停止…';self.show_notice('已请求停止；等待当前网络读取结束（最长约 60 秒）。已执行的操作不会撤销。');self.update_state()

    def update_state(self):
        active=self.sid in self.workers
        self.send_button.setEnabled(not active);self.retry_button.setEnabled(not active);self.stop_button.setEnabled(active)
        self.chat_status.setText(self.statuses.get(self.sid,'就绪 · 对话保存在本地'))
        for rid,b in self.role_buttons.items():
            busy=any(w.role==rid for w in self.workers.values())
            b.name_label.setText(('● ' if busy else '')+next(r[1] for r in ROLES if r[0]==rid))
        roots=self.config.value['roles'][self.role]['roots']
        self.permission_label.setText(f'文件权限  /  {len(roots)} 个目录\n写入需审阅 · 自动保留备份')
        self.update_context()

    def update_context(self):
        session=self.store.session(self.sid)
        usage=json.loads(session['usage'])
        if usage and ('input_tokens' in usage or 'prompt_tokens' in usage):
            tokens=usage.get('input_tokens',usage.get('prompt_tokens',0))+usage.get('cache_read_input_tokens',0)+usage.get('cache_creation_input_tokens',0)+usage.get('output_tokens',usage.get('completion_tokens',0))
            prefix='上次 API 用量'
        else:
            data=json.dumps(self.store.messages(self.sid,context=True),ensure_ascii=False)+session['summary']
            tokens=math.ceil(len(data)/2);prefix='历史估算（不含系统提示）'
        limit=self.config.value['api']['context_limit'];percent=min(100,round(tokens/limit*100))
        self.context_label.setText(f'{prefix}\n{tokens:,} / {limit:,} tokens · {percent}%')
        self.context_progress.setValue(percent)

    def memory_dialog(self):
        p=self.config.data/'memory'/self.role/'long_term.md'
        self.show_document('角色持久记忆 · '+self.role,p.read_text(encoding='utf-8')+'\n\n存储位置：'+str(p))

    def show_document(self,title,text):
        dlg=QDialog(self);dlg.setWindowTitle(title);dlg.resize(800,600);layout=QVBoxLayout(dlg)
        view=QPlainTextEdit(text);view.setReadOnly(True);layout.addWidget(view);layout.addWidget(button('关闭',dlg.accept));dlg.exec()

    def settings(self):
        dlg=Settings(self.config,self.role,self)
        if dlg.exec()==QDialog.DialogCode.Accepted:self.update_state();self.render()

    def closeEvent(self,event):
        if self.workers:
            QMessageBox.information(self,'还有任务在运行','请停止或等待所有会话中的任务完成后再关闭。右侧 ● 表示有任务运行的角色。')
            event.ignore();return
        self.config.value['last_role']=self.role
        self.config.value['active_sessions']=self.current_by_role
        self.config.save()
        event.accept()
