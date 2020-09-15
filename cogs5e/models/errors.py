class AvraeException(Exception):
    """A base exception class."""

    def __init__(self, msg):
        super().__init__(msg)


class NoCharacter(AvraeException):
    """Raised when a user has no active character."""

    def __init__(self):
        super().__init__("You have no character active.")


class NoActiveBrew(AvraeException):
    """Raised when a user has no active homebrew of a certain type."""

    def __init__(self):
        super().__init__("You have no homebrew of this type active.")


class ExternalImportError(AvraeException):
    """Raised when something fails to import."""

    def __init__(self, msg):
        super().__init__(msg)


class InvalidArgument(AvraeException):
    """Raised when an argument is invalid."""
    pass


class NotAllowed(AvraeException):
    """Raised when a user tries to do something they are not allowed to do by role or dependency."""
    pass


class OutdatedSheet(AvraeException):
    """Raised when a feature is used that requires an updated sheet."""

    def __init__(self, msg=None):
        super().__init__(msg or "This command requires an updated character sheet. Try running `!update`.")


class InvalidSaveType(AvraeException):
    def __init__(self):
        super().__init__("Invalid save type.")


class ConsumableException(AvraeException):
    """A base exception for consumable exceptions to stem from."""
    pass


class CounterOutOfBounds(ConsumableException):
    """Raised when a counter is set to a value out of bounds."""

    def __init__(self, msg=None):
        super().__init__(msg or "The new value is out of bounds.")


class NoReset(ConsumableException):
    """Raised when a consumable without a reset is reset."""

    def __init__(self):
        super().__init__("The counter does not have a reset value.")


class InvalidSpellLevel(ConsumableException):
    """Raised when a spell level is invalid."""

    def __init__(self):
        super().__init__("The spell level is invalid.")


class SelectionException(AvraeException):
    """A base exception for message awaiting exceptions to stem from."""
    pass


class NoSelectionElements(SelectionException):
    """Raised when get_selection() is called with no choices."""

    def __init__(self, msg=None):
        super().__init__(msg or "There are no choices to select from.")


class SelectionCancelled(SelectionException):
    """Raised when get_selection() is cancelled or times out."""

    def __init__(self):
        super().__init__("Selection timed out or was cancelled.")


class CombatException(AvraeException):
    """A base exception for combat-related exceptions to stem from."""
    pass


class CombatNotFound(CombatException):
    """Raised when a channel is not in combat."""

    def __init__(self):
        super().__init__("This channel is not in combat.")


class RequiresContext(CombatException):
    """Raised when a combat is committed without context."""

    def __init__(self):
        super().__init__("Combat not contextualized.")


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


class RequiresLicense(AvraeException):
    """This entity requires a license to view that you don't have."""

    def __init__(self, entity, has_connected_ddb):
        super().__init__(f"insufficient license to view {entity.name}")
        self.entity = entity
        self.has_connected_ddb = has_connected_ddb
