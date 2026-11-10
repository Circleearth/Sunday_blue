"""Small independent pages; no business rules or direct database writes here."""
def create_pages(hub,parent=None):
    from .focus import FocusPage
    from .social import SocialPage
    from .rewards import RewardsPage
    from .relations import RelationsPage
    return [('focus','专注',FocusPage(hub,parent)),('social','会议',SocialPage(hub,parent)),
            ('rewards','商店',RewardsPage(hub,parent)),('relations','关系',RelationsPage(hub,parent))]
