import enum


# action activation type
class ActivationType(enum.IntEnum):
    ACTION = 1
    NO_ACTION = 2
    BONUS_ACTION = 3
    REACTION = 4
    MINUTE = 6
    HOUR = 7
    SPECIAL = 8


class AdvantageType(enum.IntEnum):
    """
    Enum compatible with the 0/1/-1/2 method of representing adv with an int. This is preferred
    in all cases when writing new code.

    TODO: refactor old code to use this
    """

    NONE = 0
    ADV = 1
    DIS = -1
    ELVEN = 2


class CoinsAutoConvert(enum.IntEnum):
    ASK = 0
    ALWAYS = 1
    NEVER = 2


class CritDamageType(enum.IntEnum):
    NORMAL = 0
    MAX_ADD = 1
    DOUBLE_ALL = 2
    DOUBLE_DICE = 3
