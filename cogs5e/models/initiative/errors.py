from cogs5e.models.errors import AvraeException

__all__ = (
    'CombatException', 'CombatNotFound', 'RequiresContext', 'ChannelInCombat', 'CombatChannelNotFound', 'NoCombatants'
)


class CombatException(AvraeException):
    """A base exception for combat-related exceptions to stem from."""
    pass


class CombatNotFound(CombatException):
    """Raised when a channel is not in combat."""

    def __init__(self):
        super().__init__("This channel is not in combat.")


class RequiresContext(CombatException):
    """Raised when a combat is committed without context."""

    def __init__(self, msg=None):
        super().__init__(msg or "Combat not contextualized.")


class ChannelInCombat(CombatException):
    """Raised when a combat is started with an already active combat."""

    def __init__(self):
        super().__init__("Channel already in combat.")


class CombatChannelNotFound(CombatException):
    """Raised when a combat's channel is not in the channel list."""

    def __init__(self):
        super().__init__("Combat channel does not exist.")


class NoCombatants(CombatException):
    """Raised when a combat tries to advance turn with no combatants."""

    def __init__(self):
        super().__init__("There are no combatants.")
