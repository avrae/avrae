from cogs5e.models.errors import AvraeException

__all__ = ('GameLogException', 'NoCampaignLink', 'CampaignAlreadyLinked')


class GameLogException(AvraeException):
    pass


class NoCampaignLink(GameLogException):
    """This campaign link was not found."""

    def __init__(self, msg='No campaign link with that ID found.'):
        super().__init__(msg)


class CampaignAlreadyLinked(GameLogException):
    """Tried to link campaign but this campaign is already linked"""

    def __init__(self, msg='This campaign has already been linked to a different channel.'):
        super().__init__(msg)
