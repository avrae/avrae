from aliasing.errors import EvaluationError
from cogs5e.models.errors import AvraeException

__all__ = (
    'AutomationException', 'StopExecution', 'TargetException', 'AutomationEvaluationException', 'NoSpellDC',
    'NoAttackBonus'
)


class AutomationException(AvraeException):
    pass


class StopExecution(AutomationException):
    """
    Some check failed that should cause automation to stop, whatever stage of execution it's at.
    This does not revert any side effects made before this point.
    """
    pass


class TargetException(AutomationException):
    pass


class AutomationEvaluationException(EvaluationError, AutomationException):
    """
    An error occurred while evaluating Draconic in automation.
    """

    def __init__(self, original, expression):
        super().__init__(original, expression)  # EvaluationError.__init__()


class NoSpellDC(AutomationException):
    def __init__(self, msg="No spell save DC found."):
        super().__init__(msg)


class NoAttackBonus(AutomationException):
    def __init__(self, msg="No attack bonus found."):
        super().__init__(msg)
