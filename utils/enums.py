import enum

# NOTE: if writing new enums for the automation engine, make sure to update automation-common too!


# action activation type
class ActivationType(enum.IntEnum):
    ACTION = 1
    NO_ACTION = 2
    BONUS_ACTION = 3
    REACTION = 4
    MINUTE = 6
    HOUR = 7
    SPECIAL = 8
    LEGENDARY = 9
    MYTHIC = 10
    LAIR = 11

    def __str__(self):
        match self.value:
            case 1:
                return "Action"
            case 3:
                return "Bonus Action"
            case 4:
                return "Reaction"
            case 2 | 6 | 7 | 8:
                return "Special"
            case 9:
                return "Legendary Action"
            case 10:
                return "Mythic Action"
            case 11:
                return "Lair Action"


class AdvantageType(enum.IntEnum):
    """
    Enum compatible with the 0/1/-1/2 method of representing adv with an int. This is preferred
    in all cases when writing new code.
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
