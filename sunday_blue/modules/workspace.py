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
        window.page_stack.setCurrentIndex(positions[key]);window.config.value['main_page']=key
    for index,(key,title,page) in enumerate(entries):
        button=QPushButton(title);button.setCheckable(True);button.setObjectName('ghost');buttons.addButton(button,index)
        window.module_nav.addWidget(button);button.clicked.connect(lambda checked=False,k=key:select(k))
    default=window.config.value.get('main_page','focus')
    if default not in positions:default='focus'
    select(default);buttons.button(positions[default]).setChecked(True)
    def changed(module):
        if module in ('private','social'):
            window.refresh_sessions()
            if window.sid:window.render(preserve=True)
    hub.changed.connect(changed)
    hub.failed.connect(window.show_notice)
    return hub
