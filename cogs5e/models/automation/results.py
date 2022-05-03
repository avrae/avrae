import abc
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, TYPE_CHECKING, Tuple, Union

import d20

if TYPE_CHECKING:
    from cogs5e.models.sheet.statblock import StatBlock
    from cogs5e.initiative import InitiativeEffect
    from gamedata import Spell

__all__ = (
    "EffectResult",
    "AutomationResult",
    "TargetResult",
    "AttackResult",
    "SaveResult",
    "DamageResult",
    "TempHPResult",
    "IEffectResult",
    "RemoveIEffectResult",
    "RollResult",
    "TextResult",
    "SetVariableResult",
    "ConditionResult",
    "UseCounterResult",
    "CastSpellResult",
)


class EffectResult(abc.ABC):
    """
    Base class for the result of an automation effect.
    """

    def get_children(self) -> Iterable["EffectResult"]:
        if hasattr(self, "children"):
            return self.children
        return []

    def get_damage(self) -> int:
        return sum(child.get_damage() for child in self.get_children())

    def __iter__(self):
        yield from self.get_children()


@dataclass(frozen=True)
class AutomationResult(EffectResult):
    """Class for the overall result of automation (technically not an effect, but eh)."""

    children: List[EffectResult]
    is_spell: bool = False
    caster_needs_commit: bool = False


@dataclass(frozen=True)
class TargetResult(EffectResult):
    """
    A zippable pair representing each iteration on a target and the results of that iteration.

    The same target may appear multiple times consecutively, which represents the multiple iterations of -rr.
    """

    targets: Tuple[Union[None, str, "StatBlock"]] = ()
    results: Tuple[List[EffectResult], ...] = ()

    def get_children(self):
        for inst in self.results:
            yield from inst


@dataclass(frozen=True)
class AttackResult(EffectResult):
    attack_bonus: int  # does not include -b bonuses
    ac: Optional[int]
    to_hit_roll: Optional[d20.RollResult]  # can be None iff automatic hit/miss - see did_hit
    adv: int
    did_hit: bool
    did_crit: bool
    children: List[EffectResult]


@dataclass(frozen=True)
class SaveResult(EffectResult):
    dc: int
    ability: str
    save_roll: Optional[d20.RollResult]  # None if target is simple or automatic fail/pass
    adv: int
    did_save: bool
    children: List[EffectResult]


@dataclass(frozen=True)
class DamageResult(EffectResult):
    damage: int
    damage_roll: d20.RollResult
    in_crit: bool

    def get_damage(self) -> int:
        return self.damage


@dataclass(frozen=True)
class TempHPResult(EffectResult):
    amount: int
    amount_roll: d20.RollResult


@dataclass(frozen=True)
class IEffectResult(EffectResult):
    effect: "InitiativeEffect"
    conc_conflict: List["InitiativeEffect"]


@dataclass(frozen=True)
class RemoveIEffectResult(EffectResult):
    removed_effect: "InitiativeEffect"
    removed_parent: Optional["InitiativeEffect"]


@dataclass(frozen=True)
class RollResult(EffectResult):
    result: int
    roll: d20.RollResult
    simplified_expr: d20.Expression
    hidden: bool


@dataclass(frozen=True)
class TextResult(EffectResult):
    text: str


@dataclass(frozen=True)
class SetVariableResult(EffectResult):
    value: int
    did_error: bool


@dataclass(frozen=True)
class ConditionResult(EffectResult):
    did_true: bool
    did_false: bool
    did_error: bool
    children: List[EffectResult]


@dataclass(frozen=True)
class UseCounterResult(EffectResult):
    counter_name: Optional[str] = None  # None if the counter was not used successfully
    counter_remaining: int = 0
    used_amount: int = 0
    requested_amount: int = 0
    skipped: bool = False


@dataclass(frozen=True)
class CastSpellResult(EffectResult):
    success: bool
    spell: Optional["Spell"] = None
    children: List[EffectResult] = field(default_factory=list)
