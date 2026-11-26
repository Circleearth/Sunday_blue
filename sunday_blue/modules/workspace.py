"""Main navigation and route aliases for the desktop workspace."""
from datetime import datetime

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QButtonGroup, QPushButton

from .day_plan import active_plan
from .hub import ModuleHub
from ..module_views import create_pages


def install_workspace(window):
    hub = window.module_hub = ModuleHub(window.config, window.store, window)
    from ..image_layouts import set_office_mode
    set_office_mode(window.config.root, hub.db.get("office_mode", False))
    entries = [("chat", "聊天", window.chat_page)] + create_pages(hub, window)
    pages = {key: page for key, _, page in entries}
    for _, _, page in entries[1:]:
        window.page_stack.addWidget(page)

    buttons = window.module_navigation = QButtonGroup(window)
    buttons.setExclusive(True)
    nav = {}
    schedule_routes = {"calendar", "reminders", "checkins", "plan"}
    aliases = {"weekly": "growth", "exercise": "life"}
    aliases.update(dict.fromkeys(schedule_routes, "schedule"))
    # Put everyday actions first while retaining direct access to every workspace.
    order = ("moment", "focus", "work", "growth", "life", "schedule", "notes", "documents",
             "chat", "social", "rewards")

    def restore_selection():
        previous = buttons.button(window.page_stack.currentIndex())
        if previous:
            previous.setChecked(True)

    def select(route):
        if route == "study_help":
            pages["moment"].help_study()
            return True
        key = aliases.get(route, route)
        if key not in pages:
            restore_selection()
            return False
        target = pages[key]
        current = window.page_stack.currentWidget()
        if current is not target and hasattr(current, "can_leave"):
            if not current.can_leave(lambda: select(route)):
                restore_selection()
                return False
        window.page_stack.setCurrentWidget(target)
        window.config.value["main_page"] = key
        nav[key].setChecked(True)
        if route in schedule_routes:
            target.select(route)
            if route=="plan":
                slot,row,_,day=active_plan(hub.db,datetime.now())
                target.pages["plan"].reveal(slot,row,day)
        elif route == "weekly":
            target.tabs.setCurrentWidget(target.weekly)
            target.weekly.today()
            if not target.weekly.pid:
                target.weekly.transition()
            target.weekly.tabs.setCurrentIndex(1)
        elif route == "exercise":
            target.exercise_dialog()
        return True

    titles = {key: title for key, title, _ in entries}
    for key in dict.fromkeys((*order, *titles)):
        if key not in pages:
            continue
        item = QPushButton(titles[key])
        item.setObjectName("workspaceTab")
        item.setCheckable(True)
        buttons.addButton(item, window.page_stack.indexOf(pages[key]))
        window.module_nav.addWidget(item)
        item.clicked.connect(lambda checked=False, route=key: select(route))
        nav[key] = item
    window.module_nav.addStretch()
    hub.navigate.connect(select)

    if hasattr(window, "game_button"):
        from ..hamlet.page import open_village
        window.game_button.show()
        window.game_button.clicked.connect(lambda: open_village(hub, window))

    if hasattr(window, "plan_strip"):
        from ..module_views.moment import current_plan

        def show_plan():
            title = current_plan(hub.db, datetime.now())
            window.plan_strip.set_plan(title if title != "自由安排" else "")

        window.plan_strip.clicked.connect(lambda:select("plan"))
        hub.changed.connect(lambda name: show_plan() if name == "weekly_plan" else None)
        window.plan_timer = QTimer(window)
        window.plan_timer.timeout.connect(show_plan)
        window.plan_timer.start(30000)
        hub.closed.connect(window.plan_timer.stop)
        show_plan()

    from ..module_views.attention_controls import rest_guide
    hub.rest_requested.connect(lambda: rest_guide(window))
    default = window.config.value.get("main_page", "moment")
    if default == "relations":
        default = "chat"
        QTimer.singleShot(0, window.open_relations)
    select(default if default in pages or default in schedule_routes else "moment")

    def changed(module):
        if module in ("private", "social"):
            window.refresh_sessions()
            if window.sid:
                window.render(preserve=True)

    hub.changed.connect(changed)
    hub.failed.connect(getattr(window,"show_module_notice",window.show_notice))
    return hub
