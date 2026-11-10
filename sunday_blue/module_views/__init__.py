"""Small independent pages; no business rules or direct database writes here."""
def create_pages(hub,parent=None):
    from .focus import FocusPage
    from .social import SocialPage
    from .rewards import RewardsPage
    from .relations import RelationsPage
    from .planner import RemindersPage,CalendarPage,CheckinsPage
    return [('focus','专注',FocusPage(hub,parent)),('social','会议',SocialPage(hub,parent)),
            ('rewards','商店',RewardsPage(hub,parent)),('relations','关系',RelationsPage(hub,parent)),('reminders','提醒',RemindersPage(hub,parent)),('calendar','日历',CalendarPage(hub,parent)),('checkins','打卡',CheckinsPage(hub,parent))]
