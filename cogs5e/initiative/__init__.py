from .combat import Combat
from .combatant import Combatant, MonsterCombatant, PlayerCombatant
from .effect import Effect
from .errors import *
from .group import CombatantGroup
from .types import CombatantType

pass  # don't move my imports, pycharm - the cog has to be imported last

from .cog import InitTracker  # noqa E402


def setup(bot):
    bot.add_cog(InitTracker(bot))
