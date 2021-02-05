import enum
import uuid


def create_combatant_id():
    """Creates a unique string ID for each combatant. Might be changed to ObjectId later."""
    return str(uuid.uuid4())


def create_effect_id():
    """Creates a unique string ID for each effect. Might be changed to ObjectId later."""
    return str(uuid.uuid4())


class CombatantType(enum.Enum):
    GENERIC = 'common'
    PLAYER = 'player'
    MONSTER = 'monster'
    GROUP = 'group'
