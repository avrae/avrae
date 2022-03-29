from cogs5e.models.errors import AvraeException


class TutorialException(AvraeException):
    """Something happened in a tutorial"""

    pass


class PrerequisiteFailed(TutorialException):
    """We expected the tutorial to be in some state, but it isn't (e.g. player not in combat)"""

    def __init__(self, msg="Something isn't right: invalid tutorial state"):
        super().__init__(msg)
