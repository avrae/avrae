from cogs5e.models.errors import AvraeException
from cogs5e.models.errors import ExternalImportError


class ExplorationException(AvraeException):
    """A base exception for combat-related exceptions to stem from."""

    pass


class ExplorationNotFound(ExplorationException):
    """Raised when a channel has no active exploration."""

    def __init__(self):
        super().__init__("This channel has no active exploration.")


class RequiresContext(ExplorationException):
    """Raised when an exploration is committed without context."""

    def __init__(self, msg=None):
        super().__init__(msg or "Exploration not contextualized.")


class ChannelInUse(ExplorationException):
    """Raised when an exploration is started with an already active exploration."""

    def __init__(self):
        super().__init__("Channel already in use.")


class ExplorationChannelNotFound(ExplorationException):
    """Raised when an exploration's channel is not in the channel list."""

    def __init__(self):
        super().__init__("Exploration channel does not exist.")


class MissingValues(ExternalImportError):
    def __init__(self, cell, sheet):
        self.cell = cell
        self.sheet = sheet
        super().__init__(f"Missing encounter table value in cell {cell} on sheet '{sheet}'")


class NoEncounter(AvraeException):
    """Raised when a GM has no encounter table set up."""

    def __init__(self):
        super().__init__("You have no random encounter table set up.")
