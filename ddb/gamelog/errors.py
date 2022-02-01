from cogs5e.models.errors import AvraeException

__all__ = ('GameLogException',
           'CampaignLinkException', 'LinkNotAllowed', 'NoCampaignLink', 'CampaignAlreadyLinked', 'IgnoreEvent')


class GameLogException(AvraeException):
    """Base class for all game log exceptions."""
    pass


# ==== campaign linking ====
class CampaignLinkException(GameLogException):
    """Base class for all exceptions related to campaign linking."""
    pass


class LinkNotAllowed(CampaignLinkException):
    """You cannot link this campaign because you are not in it or something"""

    def __init__(self, msg='You are not allowed to link this campaign.'):
        super().__init__(msg)


class NoCampaignLink(CampaignLinkException):
    """This campaign link was not found."""

    def __init__(self, msg='No campaign link with that ID found.'):
        super().__init__(msg)


class CampaignAlreadyLinked(CampaignLinkException):
    """Tried to link campaign but this campaign is already linked"""

    def __init__(self, msg='This campaign has already been linked to a different channel.'):
        super().__init__(msg)


# ==== event handling ====
class IgnoreEvent(GameLogException):
    """We should just stop processing this event. Do not display any error."""
    pass
