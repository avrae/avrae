from typing import Any, TYPE_CHECKING

__all__ = ("_CombatT", "_CombatantT", "_IEffectT", "_StatBlockT", "_CharacterT")

# types are only defined when type checking to prevent circular imports
_CombatT = Any
_CombatantT = Any
_IEffectT = Any
_StatBlockT = Any
_CharacterT = Any
if TYPE_CHECKING:
    from ..combat import Combat
    from ..combatant import Combatant
    from .effect import InitiativeEffect
    from cogs5e.models.sheet.statblock import StatBlock
    from cogs5e.models.character import Character

    _CombatT = Combat
    _CombatantT = Combatant
    _IEffectT = InitiativeEffect
    _StatBlockT = StatBlock
    _CharacterT = Character
