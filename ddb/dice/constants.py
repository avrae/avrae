import enum


class RollType(enum.Enum):
    ROLL = 'roll'
    TO_HIT = 'to hit'
    DAMAGE = 'damage'
    HEAL = 'heal'
    SPELL = 'spell'
    SAVE = 'save'
    CHECK = 'check'


class RollKind(enum.Enum):
    NONE = ''
    ADVANTAGE = 'advantage'
    DISADVANTAGE = 'disadvantage'
    CRITICAL_HIT = 'critical hit'


class DiceOperation(enum.Enum):
    SUM = 0
    MIN = 1
    MAX = 2
