from __future__ import annotations
import json
import math
import time
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, Signal, QSize
from PySide6.QtGui import QIcon, QPixmap, QColor, QPainter, QPen, QLinearGradient, QFont, QTextOption
from PySide6.QtWidgets import (QApplication, QWidget, QFrame, QLabel, QPushButton, QHBoxLayout,
    QVBoxLayout, QListWidget, QListWidgetItem, QScrollArea, QPlainTextEdit, QTextBrowser,
    QProgressBar, QDialog, QMessageBox, QInputDialog, QFileDialog, QSizeGrip, QSizePolicy, QMenu, QToolButton, QStackedWidget)
from .storage import Store, plain
from .roles import list_roles, require_role
from .agent import Agent, is_compact_command
from .legacy_greetings import LegacyGreetings as Greetings
from .settings import Settings
from .theme import style_for
from .chat_presentation import segments, delay, options, chat_font, tool_failure
from .tray import Tray

# Re-export names for existing imports/tests; implementation lives in ui_components.
from .ui_components import text_label, button, TitleBar, Composer, Portrait, Bubble

class MainWindow(QWidget):
    """Main window: sidebar sessions, chat view, character panel, role rail.

    Functional areas (search by these names):
    - session switching: switch_role / refresh_sessions / select_history / new_session / fork / rename / export
    - chat display (incremental): clear_chat / render / _add_message_widgets / add_bubble / more_history
    - scroll & follow: scroll_bottom / _update_follow_button / _follow_clicked / _on_bar_moved / _place_follow_button
    - worker coordination: send / retry / start_worker / on_text / on_changed / advance_segments / on_status /
      on_error / on_finished / on_approval / stop
    - status & context: update_state / update_context
    - display prefs: settings / toggle_theme / _apply_theme
    """
    def __init__(self,config):
        super().__init__()
        self.config=config; self.store=Store(config.data)
        self.store.recover_interrupted_tools()
        self.greetings=Greetings(config.data)
        self.role=list_roles(config.root)[0][0]; self.sid=None
        self.current_by_role={}
        for rid,sid in config.value.get('active_sessions',{}).items():
            saved=self.store.session(sid)
            if saved and saved['role']==rid:self.current_by_role[rid]=sid
        self.workers={}; self.statuses={}; self.drafts={}; self.errors={}
        from .role_lifecycle import RoleLifecycle
        self.role_service=RoleLifecycle(config, self.store, self.role_busy)
        self.role_recovery_errors=self.role_service.resume_pending()
        self.pending=None; self.pending_text=''; self.history_limit=120
        self._shown=None; self._shown_until=0; self._reveal_shown={}; self._greeted_shown=set()
        self._more_button=None; self._welcome_shown=False; self._stretch_added=False
        self._force_rebuild=False; self._auto_follow=False
        self._rendering=False; self._last_max=0; self._welcome=None
        self._follow_show_timer=QTimer(self); self._follow_show_timer.setInterval(1000); self._follow_show_timer.setSingleShot(True)
        self._follow_show_timer.timeout.connect(self._show_follow_button)
        self.chat_bubbles=[]
        self._message_rows={}
        self.reveals={}
        self.reveal_timer=QTimer(self);self.reveal_timer.setInterval(80);self.reveal_timer.timeout.connect(self.advance_segments);self.reveal_timer.start()
        self.setWindowTitle('Sunday Blue')
        self.setWindowIcon(QIcon(str(config.root/'assets'/'app.ico')))
        self.setWindowFlags(Qt.WindowType.Window|Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(1440,900); self.setMinimumSize(1100,720)
        self.ui_theme=config.value.get('ui_theme','dark'); self._apply_theme()
        outer=QVBoxLayout(self); outer.setContentsMargins(0,0,0,0)
        shell=QWidget(); shell.setObjectName('shell'); outer.addWidget(shell)
        main=QVBoxLayout(shell); main.setContentsMargins(1,1,1,1); main.setSpacing(0)
        top=TitleBar(); top.setObjectName('top'); top.setFixedHeight(56)
        bar=QHBoxLayout(top); bar.setContentsMargins(20,7,10,7)
        bar.addWidget(text_label('Sunday Blue','brand'))
        nav_scroll=QScrollArea();nav_scroll.setWidgetResizable(True);nav_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        nav_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        nav_content=QWidget();self.module_nav=QHBoxLayout(nav_content);self.module_nav.setContentsMargins(0,0,0,0)
        nav_scroll.setWidget(nav_content);bar.addWidget(nav_scroll,1)
        bar.addWidget(button('设置',self.settings,'ghost'))
        self.theme_button=button('☀  浅色' if self.ui_theme=='dark' else '☾  暗色',self.toggle_theme,'ghost'); bar.addWidget(self.theme_button)
        bar.addSpacing(10)
        for title,fn,obj in [('—',self.showMinimized,'ghost'),('□',self.maximize,'ghost'),('×',self.close,'close')]:
            b=button(title,fn,obj); b.setFixedSize(34,32); bar.addWidget(b)
        main.addWidget(top)
        self.page_stack=QStackedWidget();self.chat_page=QWidget();self.page_stack.addWidget(self.chat_page);main.addWidget(self.page_stack,1)
        body=QHBoxLayout(self.chat_page);body.setContentsMargins(0,0,0,0);body.setSpacing(0)
        self._sidebar(body); self._chat(body); self._character(body); self._rail(body)
        foot=QHBoxLayout(); foot.setContentsMargins(16,3,3,3)
        foot.addWidget(text_label('SUNDAY BLUE  /  0.1','eyebrow')); foot.addStretch()
        self.footer=text_label('本地会话 · 独立记忆 · 由你掌控','muted'); foot.addWidget(self.footer)
        grip=QSizeGrip(self); grip.setFixedSize(16,16); foot.addWidget(grip); main.addLayout(foot)
        last=config.value.get('last_role','rui')
        self.switch_role(last if last in {r[0] for r in list_roles(self.config.root)} else list_roles(self.config.root)[0][0])
        self.tray=Tray(self)
        if self.role_recovery_errors:
            self.show_notice('角色清理尚未完成，请打开角色管理查看：' + '；'.join(self.role_recovery_errors))

    def role_busy(self, role):
        from .memory_preferences import _jobs, _windows
        return (any(w.role == role for w in self.workers.values())
                or any(job.isRunning() for job in _jobs) or bool(_windows)
                or (hasattr(self,'module_hub') and role in self.module_hub.busy_roles()))

    def manage_roles(self):
        from .role_preferences import RoleManager
        dialog=RoleManager(self.role_service, self.role, self)
        dialog.changed.connect(self.refresh_roles)
        dialog.exec()

    def refresh_roles(self):
        active={r[0] for r in list_roles(self.config.root)}
        self.save_draft()
        self.current_by_role={r:s for r,s in self.current_by_role.items() if r in active}
        for mapping in (self.drafts, self.statuses, self.errors, self.reveals):
            for sid in list(mapping):
                session=self.store.session(sid)
                if not session or session['role'] not in active: mapping.pop(sid,None)
        if self.role not in active:
            self.role=list_roles(self.config.root)[0][0]; self.sid=None
        self._populate_roles()
        self._force_rebuild=True
        self.switch_role(self.role)
        if hasattr(self,'module_hub'):self.module_hub.changed.emit('roles')

    def maximize(self):
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def _apply_theme(self):
        self.setStyleSheet(style_for(self.ui_theme,self.config.value.get('ui_display',{})))
        if hasattr(self,'portrait'):
            self.portrait.theme=self.ui_theme;self.portrait.update()
        if hasattr(self, 'theme_button'):
            self.theme_button.setText('☀  浅色' if self.ui_theme == 'dark' else '☾  暗色')

    def toggle_theme(self):
        bar=self.chat_scroll.verticalScrollBar();position=bar.value();follow=self._auto_follow
        self._rendering=True
        self.ui_theme = 'light' if self.ui_theme == 'dark' else 'dark'
        self._apply_theme()
        self.refresh_art()
        for bubble in self.chat_bubbles:bubble.set_theme(self.ui_theme=='light')
        self.config.value['ui_theme'] = self.ui_theme
        self.config.save()
        self._rendering=False;self._auto_follow=follow
        QTimer.singleShot(0,lambda:bar.setValue(bar.maximum() if follow else min(position,bar.maximum())))

    def _sidebar(self,body):
        frame=QFrame(); frame.setObjectName('sidebar'); frame.setFixedWidth(232)
        layout=QVBoxLayout(frame); layout.setContentsMargins(16,22,14,16); layout.setSpacing(12)
        layout.addWidget(text_label('当前角色','section'))
        self.side_name=text_label('Rui','title'); layout.addWidget(self.side_name)
        layout.addWidget(button('＋  开始新对话',self.new_session,'primary'))
        layout.addSpacing(10); layout.addWidget(text_label('会话记录','section'))
        self.sessions_list=QListWidget(); self.sessions_list.currentItemChanged.connect(self.select_history)
        self.sessions_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.sessions_list.customContextMenuRequested.connect(self._sidebar_context_menu)
        layout.addWidget(self.sessions_list,1)
        row=QHBoxLayout()
        row.addWidget(button('重命名',self.rename_session,'ghost')); row.addWidget(button('导出',self.export_session,'ghost'))
        row.addWidget(button('已归档',self.archived_dialog,'ghost')); layout.addLayout(row)
        layout.addWidget(text_label('每一次对话，都有迹可循。','muted'))
        body.addWidget(frame)

    def _chat(self,body):
        panel=QWidget(); layout=QVBoxLayout(panel); layout.setContentsMargins(24,20,24,14); layout.setSpacing(12)
        row=QHBoxLayout(); names=QVBoxLayout()
        self.chat_title=text_label('Rui','title'); names.addWidget(self.chat_title)
        self.chat_status=text_label('就绪','muted'); names.addWidget(self.chat_status); row.addLayout(names); row.addStretch()
        self.session_menu=QMenu(self)
        self._menu_target=self.sid
        self.fork_action=self.session_menu.addAction('创建分支'); self.fork_action.triggered.connect(self._menu_fork)
        self.session_menu.addSeparator()
        self.archive_action=self.session_menu.addAction('归档会话'); self.archive_action.triggered.connect(self._menu_archive)
        self.delete_action=self.session_menu.addAction('删除会话'); self.delete_action.triggered.connect(self._menu_delete)
        self.session_button=button('⋮',lambda:None,'ghost'); self.session_button.setFixedSize(34,32)
        self.session_button.clicked.connect(lambda:self._show_session_menu())
        row.addWidget(self.session_button); layout.addLayout(row)
        self.chat_scroll=QScrollArea(); self.chat_scroll.setWidgetResizable(True)
        self.chat_content=QWidget(); self.chat_content.setObjectName('chatContent'); self.chat_content.setStyleSheet('QWidget#chatContent { background:transparent; }')
        self.chat_layout=QVBoxLayout(self.chat_content); self.chat_layout.setContentsMargins(0,10,5,10); self.chat_layout.setSpacing(14)
        self.chat_scroll.setWidget(self.chat_content); layout.addWidget(self.chat_scroll,1)
        self.chat_scroll.verticalScrollBar().valueChanged.connect(self._on_bar_moved)
        self.chat_scroll.verticalScrollBar().rangeChanged.connect(self._on_range_changed)
        # Floating "back to latest" hint: a child of the scroll area (never of the panel
        # layout), so showing/hiding it cannot reflow the chat column and cause a flash.
        self.follow_button=button('⌄  查看最新消息',self._follow_clicked,'ghost'); self.follow_button.setFixedHeight(32)
        self.follow_button.setParent(self.chat_scroll); self.follow_button.hide()
        self.notice=text_label('','muted'); self.notice.setWordWrap(True); self.notice.hide(); layout.addWidget(self.notice)
        composer=QFrame(); composer.setObjectName('composer'); c=QVBoxLayout(composer); c.setContentsMargins(12,9,12,9)
        self.input=Composer(); self.input.setObjectName('input'); self.input.setPlaceholderText('')
        self.input.setFixedHeight(80); self.input.send.connect(self.send); c.addWidget(self.input)
        actions=QHBoxLayout(); actions.addWidget(text_label('Enter 发送  ·  Shift + Enter 换行','muted')); actions.addStretch()
        self.retry_button=button('重试',self.retry,'ghost'); actions.addWidget(self.retry_button)
        self.stop_button=button('停止并撤回',self.stop,'ghost'); actions.addWidget(self.stop_button)
        self.send_button=button('发送  ↗',self.send,'primary'); actions.addWidget(self.send_button); c.addLayout(actions); layout.addWidget(composer)
        body.addWidget(panel,1)

    def _character(self,body):
        panel=QWidget(); panel.setFixedWidth(276);self.character_panel=panel
        layout=QVBoxLayout(panel); layout.setContentsMargins(0,20,16,16); layout.setSpacing(10)
        row=QHBoxLayout(); row.addWidget(text_label('角色档案','section')); row.addStretch(); row.addWidget(button('刷新素材',self.refresh_art,'ghost')); layout.addLayout(row)
        self.portrait=Portrait(self.config.root);self.portrait.theme=self.ui_theme;layout.addWidget(self.portrait,1)
        self.role_description=text_label('','muted'); self.role_description.setWordWrap(True); layout.addWidget(self.role_description)
        layout.addSpacing(5)
        self.context_label=text_label('上下文 · 等待第一条消息','muted'); self.context_label.setWordWrap(True); layout.addWidget(self.context_label)
        self.context_progress=QProgressBar(); self.context_progress.setRange(0,100); self.context_progress.setTextVisible(False); self.context_progress.setFixedHeight(4); layout.addWidget(self.context_progress)
        layout.addWidget(button('编辑已确认记忆',self.memory_dialog,'ghost'))
        layout.addWidget(button('协作记录',self.event_dialog,'ghost'))
        layout.addWidget(button('记忆大脑 / Ollama',self.brain_dialog,'ghost'))
        self.permission_label=text_label('','muted'); self.permission_label.setWordWrap(True); layout.addWidget(self.permission_label)
        body.addWidget(panel)

    def _rail(self,body):
        rail=QFrame(); rail.setObjectName('rail'); rail.setFixedWidth(96)
        layout=QVBoxLayout(rail); layout.setContentsMargins(8,18,8,10); layout.setSpacing(10)
        layout.addWidget(text_label('角色','section'),0,Qt.AlignmentFlag.AlignHCenter)
        scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner=QWidget(); inner.setObjectName('roleContent'); inner.setStyleSheet('QWidget#roleContent { background:transparent; }'); items=QVBoxLayout(inner); items.setContentsMargins(0,0,0,0); items.setSpacing(10)
        self.role_items=items
        self._populate_roles()
        scroll.setWidget(inner); layout.addWidget(scroll); body.addWidget(rail)
        layout.addWidget(button('管理',self.manage_roles,'ghost'))

    def _populate_roles(self):
        items=self.role_items
        while items.count():
            item=items.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self.role_buttons={}
        for rid,name,desc,color in list_roles(self.config.root):
            b=QToolButton(); b.setObjectName('role'); b.setCheckable(True);b.setText(name)
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon);b.setIconSize(QSize(44,44))
            b.setToolTip(name+' · '+desc); b.clicked.connect(lambda checked=False,r=rid:self.switch_role(r))
            b.setStyleSheet(f'QToolButton {{border-top:2px solid {color};}}')
            self.role_buttons[rid]=b; items.addWidget(b);b.setFixedSize(76,88)
        items.addStretch()
        self.refresh_art()

    def refresh_art(self):
        for rid,b in getattr(self,'role_buttons',{}).items():
            pix=QPixmap(str(self.config.root/'assets'/'roles'/rid/'avatar.png'))
            b.setIcon(QIcon(pix.scaled(44,44,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)))
        if hasattr(self,'portrait'): self.portrait.set_role(self.role)

    def save_draft(self):
        if self.sid: self.drafts[self.sid]=self.input.toPlainText()

    def switch_role(self,role):
        require_role(self.config.root, role)
        self.save_draft(); self.role=role
        saved_sid=self.current_by_role.get(role)
        saved=self.store.session(saved_sid) if saved_sid else None
        saved_ok=saved is not None and not saved['archived']
        rows=self.store.sessions(role)
        self.sid=saved_sid if saved_ok else (rows[0]['id'] if rows else self.store.create(role))
        if not saved_ok:self.current_by_role.pop(role,None)
        self.current_by_role[role]=self.sid
        self.history_limit=120
        self.refresh_sessions(); self.render()
        name=next(r for r in list_roles(self.config.root) if r[0]==role)
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
        self._menu_target=self.sid; self._menu_fork()

    def _show_session_menu(self):
        # Header "⋯": branch the active session, disabled while a worker is running.
        if self.sid is None: return
        self._prepare_session_menu(self.sid)
        self.session_menu.exec(self.session_button.mapToGlobal(self.session_button.rect().bottomLeft()))

    def _sidebar_context_menu(self, pos):
        # Right-click on a session row: branch/archive/delete that specific session.
        item=self.sessions_list.itemAt(pos)
        if not item:return
        sid=item.data(Qt.ItemDataRole.UserRole)
        self._prepare_session_menu(sid)
        self.session_menu.exec(self.sessions_list.mapToGlobal(pos))

    def _prepare_session_menu(self,sid):
        if sid is None:
            self._menu_target=None
            self.fork_action.setEnabled(False); self.archive_action.setEnabled(False); self.delete_action.setEnabled(False)
            return
        session=self.store.session(sid)
        busy=sid in self.workers
        self._menu_target=sid
        self.fork_action.setEnabled(not busy)
        self.archive_action.setEnabled(bool(session) and not busy and not session['archived'])
        self.delete_action.setEnabled(bool(session) and not busy)

    def _menu_fork(self):
        sid=self._menu_target
        if sid is None or sid in self.workers:
            self.show_notice('请等待该会话当前回复完成或停止后再创建分支。'); return
        self.save_draft()
        self.sid=self.store.fork(sid); self.current_by_role[self.role]=self.sid
        self.input.clear(); self.refresh_sessions(); self.render(); self.update_state()
        self.show_notice('已创建独立分支；原对话保留，角色持久记忆共享。')

    def _menu_archive(self):
        sid=self._menu_target
        if sid is None: return
        if sid in self.workers:
            self.show_notice('请等待该会话当前回复完成或停止后再归档。'); return
        s=self.store.session(sid); title=s['title']
        if QMessageBox.question(self,'归档会话','确认归档「%s」？\n归档后会话将不在左侧列表显示，但可打开"已归档"随时还原。'%title)!=QMessageBox.StandardButton.Yes:
            return
        self._leave_session_if_needed(sid,create_when_empty=False)
        self.store.archive(sid)
        self._refresh_after_session_removed()
        self.show_notice('已归档「%s」。点左侧"已归档"可还原。'%title)

    def _menu_delete(self):
        sid=self._menu_target
        if sid is None: return
        if sid in self.workers:
            self.show_notice('请等待该会话当前回复完成或停止后再删除。'); return
        s=self.store.session(sid); title=s['title']
        message=('确认删除「%s」？\n删除会同时清除这条对话的所有消息，以及它进入过记忆队列的相关记录；'\
                 '无法恢复。已提炼到记忆大脑的角色记忆和已确认记忆均保留；这不是遗忘操作。'%title)
        if QMessageBox.question(self,'删除会话',message)!=QMessageBox.StandardButton.Yes:
            return
        if self.role_busy(self.store.session(sid)['role']):
            self.show_notice('请先结束该角色的任务并关闭记忆图谱，再删除会话。')
            return
        try:
            self.store.delete(sid)
        except Exception as exc:
            self.show_notice('删除未完成，记录保留，可重试：' + str(exc))
            return
        self._leave_session_if_needed(sid,create_when_empty=True)
        self._refresh_after_session_removed()
        self.show_notice('已删除「%s」。'%title)

    def _leave_session_if_needed(self,sid,create_when_empty):
        # Archive/delete happen AFTER this, so sid is still in the store: exclude it.
        self.drafts.pop(sid,None)
        self.errors.pop(sid,None)
        if self.sid!=sid:return
        remaining=[s['id'] for s in self.store.sessions(self.role) if s['id']!=sid]
        if remaining:
            self.sid=remaining[0]; self.current_by_role[self.role]=self.sid
            self.input.setPlainText(self.drafts.get(self.sid,''))
        elif create_when_empty:
            # delete left zero sessions: a fresh one is the only way to keep chatting
            self.sid=self.store.create(self.role); self.current_by_role[self.role]=self.sid
            self.input.clear()
        else:
            # archive left zero visible sessions: stay in an empty welcome state, no new row
            self.sid=None; self.current_by_role.pop(self.role,None)
            self.input.clear()

    def _refresh_after_session_removed(self):
        self.refresh_sessions(); self.render(); self.update_state()

    def archived_dialog(self):
        rows=[s for s in self.store.sessions(self.role,include_archived=True) if s['archived']]
        dlg=QDialog(self); dlg.setWindowTitle('已归档会话 · '+next(r[1] for r in list_roles(self.config.root) if r[0]==self.role)); dlg.resize(460,360)
        layout=QVBoxLayout(dlg)
        layout.addWidget(text_label('还原后会回到左侧"会话记录"列表。','muted'))
        list_widget=QListWidget()
        for s in rows:
            item=QListWidgetItem(s['title']); item.setData(Qt.ItemDataRole.UserRole,s['id']); list_widget.addItem(item)
        if not rows:list_widget.addItem('暂无已归档会话')
        layout.addWidget(list_widget,1)
        buttons=QHBoxLayout()
        def _restore():
            item=list_widget.currentItem()
            if not item or item.text()=='暂无已归档会话':return
            sid=item.data(Qt.ItemDataRole.UserRole)
            if sid in self.workers:self.show_notice('请等待该会话当前回复完成或停止后再还原。');return
            self.store.archive(sid,False)
            dlg.accept()
            self._refresh_after_session_removed()
            self.show_notice('已还原「%s」。'%self.store.session(sid)['title'])
        restore=button('还原选中',_restore,'primary'); buttons.addStretch(); buttons.addWidget(restore)
        buttons.addWidget(button('关闭',dlg.accept,'ghost'))
        layout.addLayout(buttons)
        dlg.exec()

    def rename_session(self):
        if self.sid is None: self.show_notice('请先选择或新建一个会话。'); return
        title,ok=QInputDialog.getText(self,'会话名称','名称：',text=self.store.session(self.sid)['title'])
        if ok and title.strip(): self.store.update(self.sid,title=title.strip()[:100]); self.refresh_sessions()

    def export_session(self):
        if self.sid is None: self.show_notice('请先选择或新建一个会话。'); return
        path,_=QFileDialog.getSaveFileName(self,'导出对话',str(self.config.root/'conversation.md'),'Markdown (*.md)')
        if not path:return
        data=['# '+self.store.session(self.sid)['title']]
        for m in self.store.messages(self.sid):
            data.append('\n## '+m['role']+' · '+m['created']+'\n\n'+(plain(m['content']) or json.dumps(m['content'],ensure_ascii=False,indent=2)))
        try: Path(path).write_text('\n'.join(data),encoding='utf-8'); self.show_notice('对话已导出。')
        except OSError as exc: QMessageBox.warning(self,'导出失败',str(exc))

    def clear_chat(self):
        self.pending=None; self.pending_text=''; self.chat_bubbles.clear()
        self._message_rows={}
        while self.chat_layout.count():
            item=self.chat_layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()

    def _is_at_bottom(self,tolerance=20):
        bar=self.chat_scroll.verticalScrollBar()
        return bar.value()>=max(0,bar.maximum()-tolerance)

    def _retire_pending(self):
        # Remove an unfinished live row; completed text is adopted in _add_message_widgets.
        old=self.pending
        self.pending=None
        self.pending_text=''
        if old:
            row=old.parentWidget()
            self.chat_layout.removeWidget(row);row.hide();row.deleteLater()
            if old in self.chat_bubbles:self.chat_bubbles.remove(old)

    def render(self, preserve=False):
        # Two paths:
        #  - rebuild: a different session is shown, the first render, or display prefs
        #    changed (settings) so every bubble must be recreated.
        #  - append: same session, new content landed (streaming tick, tool receipt,
        #    segment reveal, a new assistant/user message). New bubbles are inserted
        #    right before the bottom spacer; nothing already on screen is deleted or
        #    re-laid-out, so the view is left exactly where it is (WeChat-style:
        #    reading history is never disturbed; only programmatic actions at the
        #    bottom keep the view pinned to the latest message).
        force=self._force_rebuild
        rebuilding=self._shown is None or self._shown!=self.sid or force
        follow=None
        was_at_bottom=self._auto_follow
        self._rendering=True
        if rebuilding:
            self._force_rebuild=False
            if force or (preserve and self._shown==self.sid):
                # same-session forced rebuild (settings) or switch_role: keep position
                follow=None if was_at_bottom else self.chat_scroll.verticalScrollBar().value()
                self._auto_follow=was_at_bottom
            else:
                # switching/selecting/sending into a session: start at the bottom
                follow=None
                self._auto_follow=True
            self.clear_chat()
            self._shown=self.sid; self._shown_until=0; self._reveal_shown={}; self._greeted_shown=set()
            self._more_button=None; self._welcome_shown=False; self._stretch_added=False
            self._welcome=None
        if self.notice.isVisible():self.notice.hide()
        messages=self.store.messages(self.sid) if self.sid else []
        if messages and self._welcome is not None:
            self.chat_layout.removeWidget(self._welcome);self._welcome.hide();self._welcome.deleteLater()
            self._welcome=None;self._welcome_shown=False
        if not messages and not self._welcome_shown:
            welcome=QFrame(); col=QVBoxLayout(welcome); col.setContentsMargins(24,70,24,35); col.setSpacing(20)
            name=next(r[1] for r in list_roles(self.config.root) if r[0]==self.role)
            col.addWidget(text_label('A LITTLE SPACE, JUST FOR YOU','eyebrow'))
            col.addWidget(text_label(f'与 {name} 开始一段对话。','title'))
            intro=text_label('日常、计划，或一个还没整理好的想法。\n从这里开始，记忆会慢慢延续。','muted'); intro.setWordWrap(True); col.addWidget(intro)
            if not self.config.value['api']['model']:
                col.addWidget(button('设置你的 API 连接  →',self.settings,'primary'))
            self.chat_layout.addWidget(welcome); self._welcome_shown=True;self._welcome=welcome
        if len(messages)>self.history_limit and self._more_button is None:
            self._more_button=button('',self.more_history,'ghost'); self._more_button.setMaximumWidth(430)
            self.chat_layout.insertWidget(0,self._more_button)
        if self._more_button is not None:
            self._more_button.setVisible(len(messages)>self.history_limit)
            self._more_button.setText(f'加载更早的消息（还有 {len(messages)-self.history_limit} 条）')
        greetings=self.greetings.for_session(self.sid)
        added=False
        for m in messages[-self.history_limit:]:
            if m['id']<=self._shown_until:
                reveal=self.reveals.get((self.sid,m['id']))
                if reveal and reveal['count']>self._reveal_shown.get((self.sid,m['id']),0):
                    self._add_message_widgets(m,failures=False);added=True
                if m['id'] in greetings and m['id'] not in self._greeted_shown:
                    self.add_bubble(greetings[m['id']],local=True); self._greeted_shown.add(m['id'])
                continue
            self._add_message_widgets(m)
            self._shown_until=m['id']; added=True
            if m['id'] in greetings and m['id'] not in self._greeted_shown:
                self.add_bubble(greetings[m['id']],local=True); self._greeted_shown.add(m['id'])
        if not self._stretch_added:self.chat_layout.addStretch(1); self._stretch_added=True
        worker=self.workers.get(self.sid)
        if worker and getattr(worker,'live_text',''):
            self.on_text(self.sid,'',restore=worker.live_text)
        self._rendering=False
        if rebuilding:
            expected=self.sid
            def _restore_rebuild(expected=expected,follow=follow):
                if self.sid!=expected:return
                bar=self.chat_scroll.verticalScrollBar()
                if follow is None:
                    if self._auto_follow:self.scroll_bottom()
                else:bar.setValue(min(follow,bar.maximum()))
                self._update_follow_button()
            QTimer.singleShot(30,lambda:_restore_rebuild())
        elif not was_at_bottom:
            # Reading history: do NOT pull the view down; the hint button offers it.
            self._auto_follow=False
            self._update_follow_button()
        else:
            # At the bottom before this render: keep pinned to the latest message.
            self._auto_follow=True
            if added:
                expected=self.sid
                def _follow(expected=expected):
                    if self.sid==expected and self._auto_follow:
                        self.scroll_bottom(); self._update_follow_button()
                # 30ms: wait for Qt's deferred layout so maximum() already includes
                # the rows just appended (same reason Codex's rebuild restore uses 30ms).
                QTimer.singleShot(30,lambda:_follow())
        self.update_context()

    def _update_follow_button(self):
        # WeChat-style: the hint only appears if the user stays away from the bottom for
        # a full second (timer); any moment back at the bottom cancels it and hides it.
        if not hasattr(self,'follow_button'):return
        if self._is_at_bottom():
            self._follow_show_timer.stop()
            if self.follow_button.isVisible():self.follow_button.hide()
        elif not self._follow_show_timer.isActive():
            self._follow_show_timer.start()

    def _show_follow_button(self):
        if self._is_at_bottom() or self.follow_button.isVisible():return
        # Delay both place and show by one event-loop cycle: on first startup the
        # chat scroll area may not yet have its final width, so a same-frame move()
        # lands too far left (the reported "first time only" mispositioning).
        def _show():
            if self._is_at_bottom():return
            self._place_follow_button()
            self.follow_button.show()
        QTimer.singleShot(0,_show)

    def _place_follow_button(self):
        width=self.follow_button.sizeHint().width()
        height=self.follow_button.sizeHint().height()
        self.follow_button.move(max(0,(self.chat_scroll.viewport().width()-width)//2),
            max(6,self.chat_scroll.height()-height-8))

    def _on_bar_moved(self,value=None):
        bar=self.chat_scroll.verticalScrollBar()
        if not self._rendering and bar.maximum()==self._last_max:
            self._auto_follow=self._is_at_bottom()
        self._update_follow_button()

    def _on_range_changed(self,minimum,maximum):
        self._last_max=maximum
        if self._auto_follow:
            sid=self.sid
            QTimer.singleShot(0,lambda:self.scroll_bottom() if self.sid==sid and self._auto_follow else None)
        self._update_follow_button()

    def _follow_clicked(self):
        self._follow_show_timer.stop()
        self.follow_button.hide()
        self._auto_follow=True
        self.scroll_bottom()

    def _add_message_widgets(self,m,failures=True):
        text=plain(m['content']).strip()
        if text:
            parts=[text] if m['role']=='user' else segments(text,self.config.value.get('chat_display',{}))
            reveal=self.reveals.get((self.sid,m['id']))
            if reveal:
                shown=self._reveal_shown.get((self.sid,m['id']),0)
                parts=parts[:reveal['count']]
                if reveal['count']>shown:
                    for part in parts[shown:]:self.add_bubble(part,m['role']=='user',message=m['id'])
                    self._reveal_shown[(self.sid,m['id'])]=reveal['count']
            else:
                if m['role']=='assistant' and self.pending is not None and len(parts)==1:
                    self._message_rows.setdefault(m['id'],[]).append(self.pending.parentWidget())
                    self.pending.set_text(parts[0]);self.pending=None;self.pending_text=''
                else:
                    for part in parts:self.add_bubble(part,m['role']=='user',message=m['id'])
        if failures and isinstance(m['content'],list):
            for block in m['content']:
                failure=tool_failure(block)
                if failure:self.add_bubble(failure,message=m['id'])

    def more_history(self):
        bar=self.chat_scroll.verticalScrollBar();old_max=bar.maximum();old_value=bar.value();sid=self.sid
        self.history_limit+=120;self._force_rebuild=True;self.render(preserve=True)
        QTimer.singleShot(40,lambda:bar.setValue(old_value+bar.maximum()-old_max) if self.sid==sid else None)

    def _chat_width(self):
        return max(100,self.chat_scroll.viewport().width()-10)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'chat_scroll'):QTimer.singleShot(0,self.resize_bubbles)
        if hasattr(self,'follow_button'):QTimer.singleShot(0,lambda:self._place_follow_button() if self.follow_button.isVisible() else None)

    def resize_bubbles(self):
        for bubble in self.chat_bubbles:bubble.set_available_width(self._chat_width())

    def add_bubble(self,text,user=False,local=False,message=None):
        if not text.strip():return None
        row=QWidget(); line=QHBoxLayout(row); line.setContentsMargins(0,0,0,0)
        row.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Maximum)
        col=QVBoxLayout(); col.setSpacing(5)
        col.setAlignment(Qt.AlignmentFlag.AlignTop)
        name='你' if user else next(r[1] for r in list_roles(self.config.root) if r[0]==self.role)
        if local:name+=' · 时段寒暄'
        caption=text_label(name,'muted'); caption.setFixedHeight(20); caption.setAlignment(Qt.AlignmentFlag.AlignRight if user else Qt.AlignmentFlag.AlignLeft); col.addWidget(caption)
        bubble=Bubble(text,user,light=self.ui_theme=='light',width=self._chat_width(),font=chat_font(self.config.root,self.config.value.get('chat_display',{}),self.role))
        col.addWidget(bubble,0,Qt.AlignmentFlag.AlignRight if user else Qt.AlignmentFlag.AlignLeft)
        self.chat_bubbles.append(bubble)
        if user:line.addStretch(1)
        line.addLayout(col)
        if not user:line.addStretch(1)
        previous=self._message_rows.get(message,[])
        index=self.chat_layout.indexOf(previous[-1])+1 if previous else (max(0,self.chat_layout.count()-1) if self.chat_layout.count() and self.chat_layout.itemAt(self.chat_layout.count()-1).spacerItem() else self.chat_layout.count())
        self.chat_layout.insertWidget(index,row)
        if message is not None:self._message_rows.setdefault(message,[]).append(row)
        row.show()
        line.activate()
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
        from .models import resolve_api
        if not resolve_api(self.config.value,self.role)['model']:
            self.settings(); return
        if self.sid is None:
            # Empty welcome state (e.g. right after archiving the only session): open a fresh one.
            self.sid=self.store.create(self.role); self.current_by_role[self.role]=self.sid
        mid=self.store.add(self.sid,'user',text)
        if self.store.session(self.sid)['title']=='新对话':self.store.update(self.sid,title=text.replace('\n',' ')[:26])
        self.input.clear(); self.drafts[self.sid]=''; self.render(); self.start_worker()

    def retry(self):
        if self.sid in self.workers:return
        if self.sid is None:self.show_notice('没有等待回复的消息。');return
        msgs=self.store.messages(self.sid,context=True)
        if not msgs or msgs[-1]['role']!='user':self.show_notice('没有等待回复的消息。');return
        self.start_worker()

    def start_worker(self):
        # Normal chat turns. Typing "/compact" in the composer is intercepted inside the agent.
        sid=self.sid
        self.errors.pop(sid,None)
        worker=Agent(self.config.root,self.config.snapshot(),self.store,sid)
        worker.live_text=''; worker.start_after=max((m['id'] for m in self.store.messages(sid)),default=0); self.workers[sid]=worker
        worker.withdraw_id=next((m['id'] for m in reversed(self.store.messages(sid)) if m['role']=='user' and isinstance(m['content'],str)),None)
        worker.withdraw_requested=False
        worker.text.connect(self.on_text); worker.status.connect(self.on_status); worker.changed.connect(self.on_changed)
        worker.failed.connect(self.on_error); worker.approval.connect(self.on_approval)
        worker.finished.connect(lambda s=sid,w=worker:self.on_finished(s,w))
        self.notice.hide(); self.statuses[sid]='准备请求…'; worker.start(); self.update_state(); self.refresh_sessions()

    def on_text(self,sid,text,restore=None):
        worker=self.workers.get(sid)
        if worker and getattr(worker,'withdraw_requested',False):return
        if worker and restore is None:worker.live_text+=text
        if sid!=self.sid:return
        current=restore if restore is not None else (worker.live_text if worker else self.pending_text+text)
        self.pending_text=current
        c=options(self.config.value.get('chat_display',{}))
        if not current.strip() or (c['segmented'] and len(current.strip())<c['threshold']):return
        if self.pending is None:self.pending=self.add_bubble(current)
        else:self.pending.set_text(current)
        if self._auto_follow:QTimer.singleShot(0,lambda:self.scroll_bottom() if self.sid==sid and self._auto_follow else None)

    def on_changed(self,sid):
        worker=self.workers.get(sid)
        if worker and getattr(worker,'withdraw_requested',False):return
        if worker:
            worker.live_text=''
            c=self.config.value.get('chat_display',{})
            for m in self.store.messages(sid):
                key=(sid,m['id'])
                if m['id']<=worker.start_after or m['role']!='assistant' or key in self.reveals:continue
                parts=segments(plain(m['content']).strip(),c)
                if len(parts)>1:self.reveals[key]={'parts':parts,'count':1,'next':time.monotonic()+delay(parts[0],c),'config':dict(c)}
        if sid==self.sid:self.render(preserve=True)

    def advance_segments(self):
        changed=False
        for (sid,mid),state in self.reveals.items():
            if state['count']<len(state['parts']) and time.monotonic()>=state['next']:
                state['count']+=1
                state['next']=time.monotonic()+delay(state['parts'][state['count']-1],state['config'])
                changed=changed or sid==self.sid
        if changed:self.render(preserve=True)

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
        if sid==self.sid and self.pending is not None:self._retire_pending()
        if getattr(worker,'withdraw_requested',False) and worker.withdraw_id:
            text=self.store.withdraw_turn(sid,worker.withdraw_id)
            if worker.greeting:worker.greeting.discard(worker.role,sid,worker.withdraw_id)
            draft=self.input.toPlainText() if sid==self.sid else self.drafts.get(sid,'')
            self.drafts[sid]=text+('\n'+draft if draft else '')
            self.reveals={k:v for k,v in self.reveals.items() if k[0]!=sid or k[1]<worker.withdraw_id}
            self.statuses[sid]='已停止并撤回 · 内容已放回输入框'
            if sid==self.sid:self.input.setPlainText(self.drafts[sid]);self._force_rebuild=True
        if sid==self.sid:
            self.render(preserve=True)
            if getattr(worker,'error_text',None):self.show_notice(worker.error_text)
        self.refresh_sessions(); self.update_state(); worker.deleteLater()

    def brain_dialog(self):
        from .memory_preferences import show_memory_panel
        show_memory_panel(self.config.root, self.role, self)

    def on_approval(self,sid,item):
        if item.event.is_set():return
        role=self.store.session(sid)['role']
        dlg=QDialog(self); dlg.setWindowTitle(f'{role} · {item.title}'); dlg.resize(850,620)
        layout=QVBoxLayout(dlg)
        heading=text_label(role.upper()+' / '+item.title,'title');layout.addWidget(heading)
        sub=QLabel(item.subject);sub.setWordWrap(True);sub.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse);layout.addWidget(sub)
        if isinstance(item.detail, dict) and item.detail.get('kind') == 'text_change':
            from .change_review import ChangeReview
            layout.addWidget(ChangeReview(item.detail['before'], item.detail['after']))
        else:
            view=QPlainTextEdit(str(item.detail));view.setReadOnly(True);layout.addWidget(view)
        row=QHBoxLayout();row.addStretch();row.addWidget(button('拒绝',dlg.reject));row.addWidget(button('确认执行',dlg.accept,'primary'));layout.addLayout(row)
        timer=QTimer(dlg);timer.setInterval(100)
        timer.timeout.connect(lambda:dlg.reject() if sid not in self.workers or self.workers[sid].cancel.is_set() else None);timer.start()
        item.accepted=dlg.exec()==QDialog.DialogCode.Accepted
        timer.stop()
        item.event.set()

    def stop(self):
        worker=self.workers.get(self.sid)
        if worker:
            worker.withdraw_requested=True
            worker.stop();self.statuses[self.sid]='正在停止并撤回…';self.show_notice('停止完成后本轮消息回到输入框；已执行的文件操作不会撤销。');self.update_state()

    def update_state(self):
        active=self.sid in self.workers
        self.send_button.setEnabled(not active);self.retry_button.setEnabled(not active);self.stop_button.setEnabled(active)
        self.chat_status.setText(self.statuses.get(self.sid,'就绪 · 对话保存在本地'))
        for rid,b in self.role_buttons.items():
            busy=any(w.role==rid for w in self.workers.values())
            b.setText(('● ' if busy else '')+next(r[1] for r in list_roles(self.config.root) if r[0]==rid))
        roots=self.config.value['roles'][self.role]['roots']
        trusted=sum(bool(r.get('trusted') and r.get('write')) for r in roots)
        self.permission_label.setText(f'文件权限  /  {len(roots)} 个目录 · {trusted} 个信任\n信任目录自动确认 · 修改/删除备份')
        self.update_context()

    def update_context(self):
        session=self.store.session(self.sid) if self.sid else None
        if not session:
            self.context_label.setText('上下文 · 等待第一条消息'); self.context_progress.setValue(0)
            return
        usage=json.loads(session['usage'])
        if usage and ('input_tokens' in usage or 'prompt_tokens' in usage):
            tokens=usage.get('input_tokens',usage.get('prompt_tokens',0))+usage.get('cache_read_input_tokens',0)+usage.get('cache_creation_input_tokens',0)+usage.get('output_tokens',usage.get('completion_tokens',0))
            prefix='上次 API 用量'
        else:
            data=json.dumps(self.store.messages(self.sid,context=True),ensure_ascii=False)+session['summary']
            tokens=math.ceil(len(data)/2);prefix='历史估算（不含系统提示）'
        from .models import resolve_api
        limit=resolve_api(self.config.value,self.role)['context_limit'];percent=min(100,round(tokens/limit*100))
        self.context_label.setText(f'{prefix}\n{tokens:,} / {limit:,} tokens · {percent}%')
        self.context_progress.setValue(percent)

    def memory_dialog(self):
        from .memory_editor import MemoryEditor
        MemoryEditor(self.config.root, self.role, self.store, self).exec()

    def event_dialog(self):
        from .event_preferences import EventDialog
        EventDialog(self.store,self.role,self).exec()

    def show_document(self,title,text):
        dlg=QDialog(self);dlg.setWindowTitle(title);dlg.resize(800,600);layout=QVBoxLayout(dlg)
        view=QPlainTextEdit(text);view.setReadOnly(True);layout.addWidget(view);layout.addWidget(button('关闭',dlg.accept));dlg.exec()

    def settings(self):
        dlg=Settings(self.config,self.role,self)
        if dlg.exec()==QDialog.DialogCode.Accepted:
            self._apply_theme();self.update_state();self._force_rebuild=True;self.render(preserve=True)
        if getattr(dlg, 'open_role_manager_requested', False) is True:
            self.manage_roles()

    def closeEvent(self,event):
        self.config.value['last_role']=self.role
        self.config.value['active_sessions']=self.current_by_role
        self.config.save()
        if hasattr(self,'tray') and self.tray.hide_on_close():event.ignore();return
        from .memory_preferences import _jobs
        if any(job.isRunning() for job in _jobs):
            QMessageBox.information(self,'记忆操作正在进行','请等待当前模型启停或记忆整理操作完成后退出。')
            event.ignore();return
        if self.workers:
            QMessageBox.information(self,'还有任务在运行','请停止或等待所有会话中的任务完成后再关闭。右侧 ● 表示有任务运行的角色。')
            event.ignore();return
        if hasattr(self,'module_hub') and self.module_hub.jobs:
            QMessageBox.information(self,'后台任务还在运行','请先停止或等待会议回复、同步任务完成再退出。');event.ignore();return
        self.config.value['last_role']=self.role
        self.config.value['active_sessions']=self.current_by_role
        self.config.save()
        if hasattr(self,'module_hub'):self.module_hub.close()
        event.accept()
