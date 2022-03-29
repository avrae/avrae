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


class CoinsAutoConvert(enum.IntEnum):
    ASK = 0
    ALWAYS = 1
    NEVER = -1
