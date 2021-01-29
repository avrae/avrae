"""
The bot-internal (not user-facing) errors related to aliasing. For user-facing errors, see api.errors.
"""
from cogs5e.models.errors import AvraeException

__all__ = (
    'EvaluationError', 'CollectionNotFound', 'CollectableNotFound', 'AliasNameConflict', 'CollectableRequiresLicenses'
)


class EvaluationError(AvraeException):
    """Raised when a cvar evaluation causes an error."""

    def __init__(self, original, expression=None):
        super().__init__(f"Error evaluating expression: {original}")
        self.original = original
        self.expression = expression


class CollectionNotFound(AvraeException):
    """Raised when a WorkshopCollection is not found."""

    def __init__(self, msg=None):
        super().__init__(msg or "The specified collection was not found.")


class CollectableNotFound(AvraeException):
    """Raised when a collectable (alias/snippet) is not found in a collection."""

    def __init__(self, msg=None):
        super().__init__(msg or "The specified object was not found.")


class AliasNameConflict(AvraeException):
    """Unable to run command because two aliases share the same name."""
    pass


class CollectableRequiresLicenses(AvraeException):
    """Unable to invoke collectable because one or more licenses are missing"""

    def __init__(self, entities, collectable, has_connected_ddb):
        super().__init__(f"insufficient license to view {', '.join(e.name for e in entities)}")
        self.entities = entities
        self.collectable = collectable
        self.has_connected_ddb = has_connected_ddb
