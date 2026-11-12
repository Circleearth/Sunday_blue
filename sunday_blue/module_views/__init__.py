"""Small independent pages; no business rules or direct database writes here."""
def create_pages(hub,parent=None):
    from .life_work import WorkPage,LifePage
    from .markdown_reader import MarkdownPage
    from .focus import FocusPage
    from .social import SocialPage
    from .rewards import RewardsPage
    from .growth import GrowthPage,SchedulePage
    return [('focus','专注',FocusPage(hub,parent)),('work','工作',WorkPage(hub,parent)),('life','生活',LifePage(hub,parent)),('documents','资料',MarkdownPage(hub,parent)),('social','会议',SocialPage(hub,parent)),
            ('rewards','商店',RewardsPage(hub,parent)),('growth','成长',GrowthPage(hub,parent)),('schedule','日程',SchedulePage(hub,parent))]
