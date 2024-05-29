import abc
import dataclasses
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, TYPE_CHECKING

import d20

if TYPE_CHECKING:
    from cogs5e.initiative import InitiativeEffect
    from .effects.roll import RollEffectMetaVar

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
    "CheckResult",
)


@dataclass(frozen=True)
class EffectResult(abc.ABC):
    """
    Base class for the result of an automation effect.
    """

    type: str = field(init=False)

    def get_children(self) -> Iterable["EffectResult"]:
        if hasattr(self, "children"):
            return self.children
        return []

    def get_damage(self) -> int:
        return sum(child.get_damage() for child in self.get_children())

    def __iter__(self):
        yield from self.get_children()

    def to_dict(self):
        """Default impl: the value for all attrs, recurse on lists and dataclasses"""
        out = {}
        for fld in dataclasses.fields(self):
            value = getattr(self, fld.name)
            if isinstance(value, list):
                value = [i.to_dict() for i in value]
            elif dataclasses.is_dataclass(value):
                value = value.to_dict()
            out[fld.name] = value
        return out


@dataclass(frozen=True)
class AutomationResult(EffectResult):
    """Class for the overall result of automation (technically not an effect, but eh)."""

    type = "root"
    children: List[EffectResult]
    is_spell: bool = False
    caster_needs_commit: bool = False


@dataclass(frozen=True)
class TargetIteration(EffectResult):
    type = "target_iteration"
    # all, each, int, self, parent, or children
    target_type: str
    # whether the target was a str or None
    is_simple: bool
    # if the target is a combatant, their combatant ID
    target_id: Optional[str]
    # where the target was in the targets arg (accounting for sorting), for all/each/int targeting only
    target_index: Optional[int]
    # if -rr is passed, the iteration number (1-indexed)
    target_iteration: int
    # the results of this iteration
    results: List[EffectResult]

    def get_children(self):
        yield from self.results


@dataclass(frozen=True)
class TargetResult(EffectResult):
    type = "target"
    results: List[TargetIteration]

    def get_children(self):
        yield from self.results


@dataclass(frozen=True)
class AttackResult(EffectResult):
    type = "attack"
    attack_bonus: int  # does not include -b bonuses
    ac: Optional[int]
    to_hit_roll: Optional[d20.RollResult]  # can be None iff automatic hit/miss - see did_hit
    adv: int
    did_hit: bool
    did_crit: bool
    children: List[EffectResult]

    def to_dict(self):
        return {
            "type": self.type,
            "attack_bonus": self.attack_bonus,
            "ac": self.ac,
            "to_hit_roll": self.to_hit_roll and roll_result_to_dict(self.to_hit_roll),
            "adv": self.adv,
            "did_hit": self.did_hit,
            "did_crit": self.did_crit,
            "children": [child.to_dict() for child in self.children],
        }


@dataclass(frozen=True)
class SaveResult(EffectResult):
    type = "save"
    dc: int
    ability: str  # element of utils.constants.SAVE_NAMES, e.g. strengthSave
    save_roll: Optional[d20.RollResult]  # None if target is simple or automatic fail/pass
    adv: int
    did_save: bool
    children: List[EffectResult]

    def to_dict(self):
        return {
            "type": self.type,
            "dc": self.dc,
            "ability": self.ability,
            "save_roll": self.save_roll and roll_result_to_dict(self.save_roll),
            "adv": self.adv,
            "did_save": self.did_save,
            "children": [child.to_dict() for child in self.children],
        }


@dataclass(frozen=True)
class DamageResult(EffectResult):
    type = "damage"
    damage: int
    damage_roll: d20.RollResult
    in_crit: bool

    def get_damage(self) -> int:
        return self.damage

    def to_dict(self):
        return {
            "type": self.type,
            "damage": self.damage,
            "damage_roll": roll_result_to_dict(self.damage_roll),
            "in_crit": self.in_crit,
        }


@dataclass(frozen=True)
class TempHPResult(EffectResult):
    type = "temphp"
    amount: int
    amount_roll: d20.RollResult

    def to_dict(self):
        return {"type": self.type, "amount": self.amount, "amount_roll": roll_result_to_dict(self.amount_roll)}


@dataclass(frozen=True)
class IEffectResult(EffectResult):
    type = "ieffect"
    effect: "InitiativeEffect"
    conc_conflict: List["InitiativeEffect"]

    def to_dict(self):
        return {
            "type": self.type,
            "effect": self.effect.to_dict(),
            "conc_conflict": [e.to_dict() for e in self.conc_conflict],
        }


@dataclass(frozen=True)
class RemoveIEffectResult(EffectResult):
    type = "remove_ieffect"
    removed_effect: "InitiativeEffect"
    removed_parent: Optional["InitiativeEffect"]

    def to_dict(self):
        return {
            "type": self.type,
            "removed_effect": self.removed_effect.to_dict(),
            "removed_parent": self.removed_parent and self.removed_parent.to_dict(),
        }


@dataclass(frozen=True)
class RollResult(EffectResult):
    type = "roll"
    result: int
    roll: d20.RollResult
    simplified_metavar: "RollEffectMetaVar"
    hidden: bool

    def to_dict(self):
        return {
            "type": self.type,
            "result": self.result,
            "roll": roll_result_to_dict(self.roll),
            "simplified_metavar": str(self.simplified_metavar),
            "hidden": self.hidden,
        }


@dataclass(frozen=True)
class TextResult(EffectResult):
    type = "text"
    text: str
    title: str = "Effect"


@dataclass(frozen=True)
class SetVariableResult(EffectResult):
    type = "variable"
    value: int
    did_error: bool


@dataclass(frozen=True)
class ConditionResult(EffectResult):
    type = "condition"
    did_true: bool
    did_false: bool
    did_error: bool
    children: List[EffectResult]


@dataclass(frozen=True)
class UseCounterResult(EffectResult):
    type = "counter"
    counter_name: Optional[str] = None  # None if the counter was not used successfully
    counter_remaining: int = 0
    used_amount: int = 0
    requested_amount: int = 0
    skipped: bool = False


@dataclass(frozen=True)
class CastSpellResult(EffectResult):
    type = "spell"
    success: bool
    spell_id: Optional[int] = None
    level_override: Optional[int] = None
    dc_override: Optional[int] = None
    attack_bonus_override: Optional[int] = None
    casting_mod_override: Optional[int] = None
    children: List[EffectResult] = field(default_factory=list)


@dataclass(frozen=True)
class CheckResult(EffectResult):
    type = "check"
    skill_key: str
    skill_name: str
    check_roll: Optional[d20.RollResult]  # None if target is simple or automatic fail/pass
    dc: Optional[int]
    contest_roll: Optional[d20.RollResult]
    contest_skill_key: Optional[str]
    contest_skill_name: Optional[str]
    contest_did_tie: bool
    did_succeed: Optional[bool]
    children: List[EffectResult]

    def to_dict(self):
        return {
            "type": self.type,
            "skill_key": self.skill_key,
            "skill_name": self.skill_name,
            "check_roll": self.check_roll and roll_result_to_dict(self.check_roll),
            "dc": self.dc,
            "contest_roll": self.contest_roll and roll_result_to_dict(self.contest_roll),
            "contest_skill_key": self.contest_skill_key,
            "contest_skill_name": self.contest_skill_name,
            "contest_did_tie": self.contest_did_tie,
            "did_succeed": self.did_succeed,
            "children": [c.to_dict() for c in self.children],
        }


# ==== helpers ====
def roll_result_to_dict(roll_result: d20.RollResult) -> dict:
    return {"total": roll_result.total, "result": roll_result.result}
