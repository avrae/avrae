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
    def guess_from_d20(cls, result):
        """
        Guesses advantage/disadvantage based on a d20.RollResult.

        :type result: d20.RollResult
        """
        import d20
        left = d20.utils.leftmost(result.expr)
        # must be dice
        if not isinstance(left, d20.Dice):
            return cls.NONE
        # must be a d20
        if left.size != 20:
            return cls.NONE
        # must have exactly 1 keep op
        if not left.operations:
            return cls.NONE
        elif len(k_ops := [o for o in left.operations if o.op == 'k']) > 1:
            return cls.NONE
        k_op = k_ops[0]
        # with exactly one selector
        if len(k_op.sels) > 1:
            return cls.NONE
        sel = k_op.sels[0]

        # 2d20...kl1: dis
        if left.num == 2 and sel.cat == 'l' and sel.num == 1:
            return cls.DISADVANTAGE
        # 2d20...kh1 or 3d20...kh1: adv
        elif left.num in (2, 3) and sel.cat == 'h' and sel.num == 1:
            return cls.ADVANTAGE
        return cls.NONE


class DiceOperation(enum.Enum):
    SUM = 0
    MIN = 1
    MAX = 2
