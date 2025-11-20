from __future__ import annotations

from functools import cached_property
from typing import Any, Callable, List, Optional, TypeVar

import aliasing.api.statblock
import cogs5e.initiative.combatant as init
from cogs5e.initiative.group import CombatantGroup

from .utils import maybe_alias_statblock

__all__ = ("AutomationEffect", "AutomationCombatant", "AutomationGroup", "wrap_automation_entity")

_IntermediateT = TypeVar("_IntermediateT")
T = TypeVar("T")


class AutomationEffect:
    """Read-only wrapper around an initiative effect."""

    def __init__(self, effect: init.InitiativeEffect):
        self._effect = effect
        self.id = effect.id
        self.name = effect.name
        self.duration = effect.duration
        self.remaining = effect.remaining
        self.description = effect.desc
        self.concentration = effect.concentration
        self.ends_on_turn_end = effect.end_on_turn_end
        self.effect = effect.effects.to_dict()
        self.attacks = [attack.to_dict() for attack in effect.attacks]
        self.buttons = [button.to_dict() for button in effect.buttons]
        self.combatant_id = getattr(effect.combatant, "id", None)
        self.combatant_name = getattr(effect.combatant, "name", None)

    @cached_property
    def parent(self) -> Optional["AutomationEffect"]:
        parent = self._effect.get_parent_effect()
        return AutomationEffect(parent) if parent else None

    @cached_property
    def children(self) -> List["AutomationEffect"]:
        return [AutomationEffect(child) for child in self._effect.get_children_effects()]

    def __repr__(self):
        return f"<AutomationEffect name={self.name!r} remaining={self.remaining!r}>"


class AutomationCombatant(aliasing.api.statblock.AliasStatBlock):
    """
    Read-only automation-friendly wrapper around an initiative combatant.
    Exposes statblock data along with a handful of combat attributes.
    """

    def __init__(self, combatant: init.Combatant):
        super().__init__(combatant)
        self._combatant = combatant

    @property
    def id(self) -> str:
        return self._combatant.id

    @property
    def controller_id(self) -> int:
        return self._combatant.controller_id

    @property
    def init(self) -> int:
        return self._combatant.init

    @property
    def initiative_bonus(self) -> int:
        return int(self._combatant.init_skill)

    @property
    def note(self) -> Optional[str]:
        return self._combatant.notes

    @property
    def is_private(self) -> bool:
        return self._combatant.is_private

    @property
    def combatant_type(self):
        return self._combatant.type

    @property
    def group(self) -> Optional[str]:
        if hasattr(self._combatant, "group"):
            return self._combatant.group
        return None

    def hp_str(self, private: bool = False) -> str:
        return self._combatant.hp_str(private)

    @cached_property
    def effects(self) -> List[AutomationEffect]:
        return [AutomationEffect(effect) for effect in self._combatant.get_effects()]

    def get_effect_by_name(self, name: str, strict: Optional[bool] = None) -> Optional[AutomationEffect]:
        """
        Gets an effect on the combatant by its name.

        :param str name: The name of the effect to get.
        :param strict: Whether effect name must be a full case insensitive match.
            If this is ``None`` or ``False`` (default), attempts a strict match with fallback to partial match.
            If this is ``True``, it will only return a strict match.
        :return: The effect or None.
        :rtype: :class:`AutomationEffect` or None
        """
        name = str(name)
        effects = self._combatant.get_effects()

        # exact match first
        exact = next((e for e in effects if name.lower() == e.name.lower()), None)
        if exact:
            return AutomationEffect(exact)

        # partial match only if not strict
        if strict is not True:
            partial = next((e for e in effects if name.lower() in e.name.lower()), None)
            if partial:
                return AutomationEffect(partial)

        return None

    def is_concentrating(self) -> bool:
        return self._combatant.is_concentrating()


class AutomationGroup:
    """Read-only representation of an initiative group."""

    def __init__(self, group: CombatantGroup):
        self._group = group

    @property
    def id(self) -> str:
        return self._group.id

    @property
    def name(self) -> str:
        return self._group.name

    @property
    def init(self) -> int:
        return self._group.init

    @property
    def size(self) -> int:
        return len(self._group.get_combatants())

    @cached_property
    def combatants(self) -> List[AutomationCombatant]:
        return [AutomationCombatant(c) for c in self._group.get_combatants()]


def wrap_automation_entity(target):
    """
    Wraps a StatBlock/combatant/group into the automation-friendly variant.
    Returns AliasStatBlock for simple targets.
    """
    if isinstance(target, init.InitiativeEffect):
        return AutomationEffect(target)
    if isinstance(target, CombatantGroup):
        return AutomationGroup(target)
    if isinstance(target, init.Combatant):
        return AutomationCombatant(target)
    return maybe_alias_statblock(target)
