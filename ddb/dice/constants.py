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

    @classmethod
    def from_d20_adv(cls, advtype):
        import d20
        if advtype == d20.AdvType.ADV:
            return cls.ADVANTAGE
        elif advtype == d20.AdvType.DIS:
            return cls.DISADVANTAGE
        return cls.NONE


class DiceOperation(enum.Enum):
    SUM = 0
    MIN = 1
    MAX = 2
