
class AvraeException(Exception):
    """A base exception class."""
    def __init__(self, msg):
        super().__init__(msg)

class NoCharacter(AvraeException):
    """Raised when a user has no active character."""
    def __init__(self):
        super().__init__("You have no character active.")

class InvalidArgument(AvraeException):
    """Raised when an argument is invalid."""
    pass

class EvaluationError(AvraeException):
    """Raised when a cvar evaluation causes an error."""
    def __init__(self, original):
        super().__init__(f"Error evaluating expression: {original}")
        self.original = original

class OutdatedSheet(AvraeException):
    """Raised when a feature is used that requires an updated sheet."""
    def __init__(self, msg=None):
        super().__init__(msg or "This command requires an updated character sheet. Try running `!update`.")

class ConsumableException(AvraeException):
    """A base exception for consumable exceptions to stem from."""
    pass

class ConsumableNotFound(ConsumableException):
    """Raised when a consumable is not found."""
    def __init__(self):
        super().__init__("The requested counter does not exist.")

class CounterOutOfBounds(ConsumableException):
    """Raised when a counter is set to a value out of bounds."""
    def __init__(self):
        super().__init__("The new value is out of bounds.")

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
    def __init__(self):
        super().__init__("There are no choices to select from.")

class SelectionCancelled(SelectionException):
    """Raised when get_selection() is cancelled or times out."""
    def __init__(self):
        super().__init__("Selection timed out or was cancelled.")