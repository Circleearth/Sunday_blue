"""Attach optional module pages to the existing chat window, preserving its API."""
from PySide6.QtWidgets import QPushButton,QButtonGroup
from .hub import ModuleHub
from ..module_views import create_pages


def install_workspace(window):
    hub=window.module_hub=ModuleHub(window.config,window.store,window)
    entries=[('chat','聊天',window.chat_page)]+create_pages(hub,window)
    for key,title,page in entries[1:]:window.page_stack.addWidget(page)
    buttons=QButtonGroup(window);buttons.setExclusive(True);window.module_navigation=buttons
    positions={key:index for index,(key,_,_) in enumerate(entries)}
    def select(key):
        if key in ('calendar','reminders','checkins'):
            window.page_stack.widget(positions['schedule']).select(key);key='schedule'
        current=window.page_stack.currentWidget();target=positions[key]
        if current is not window.page_stack.widget(target) and hasattr(current,'can_leave') and not current.can_leave(lambda:select(key)):
            old=buttons.button(window.page_stack.currentIndex())
            if old:old.setChecked(True)
            return
        window.page_stack.setCurrentIndex(target);window.config.value['main_page']=key
        if buttons.button(target):buttons.button(target).setChecked(True)
    for index,(key,title,page) in enumerate(entries):
        button=QPushButton(title);button.setCheckable(True);button.setObjectName('ghost');buttons.addButton(button,index)
        window.module_nav.addWidget(button);button.clicked.connect(lambda checked=False,k=key:select(k))
    hub.navigate.connect(lambda key:select(key) if key in positions or key in ('calendar','reminders','checkins') else None)
    from ..module_views.attention_controls import rest_guide
    hub.rest_requested.connect(lambda:rest_guide(window))
    default=window.config.value.get('main_page','focus')
    if default=='relations':
        default='chat'
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0,window.open_relations)
    if default in ('calendar','reminders','checkins'):
        window.page_stack.widget(positions['schedule']).select(default);default='schedule'
    if default not in positions:default='focus'
    select(default);buttons.button(positions[default]).setChecked(True)
    def changed(module):
        if module in ('private','social'):
            window.refresh_sessions()
            if window.sid:window.render(preserve=True)
    hub.changed.connect(changed)
    hub.failed.connect(window.show_notice)
    return hub
