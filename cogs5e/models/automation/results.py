import abc
import typing
from dataclasses import dataclass

import d20

__all__ = (
    'EffectResult',
    'TargetResult', 'AttackResult', 'SaveResult', 'DamageResult', 'TempHPResult', 'IEffectResult', 'RollResult',
    'TextResult', 'SetVariableResult', 'ConditionResult'
)


class EffectResult(abc.ABC):
    """
    Base class for the result of an automation effect.
    """

    def get_children(self) -> typing.Iterable['EffectResult']:
        if hasattr(self, 'children'):
            return self.children
        return []

    def get_damage(self) -> int:
        return sum(child.get_damage() for child in self.get_children())


@dataclass(frozen=True)
class TargetResult(EffectResult):
    """
    A zippable pair representing each iteration on a target and the results of that iteration.

    The same target may appear multiple times consecutively, which represents the multiple iterations of -rr.
    """
    targets: typing.Tuple[typing.Union[None, str, 'cogs5e.models.sheet.statblock.StatBlock']] = ()
    results: typing.Tuple[typing.List[EffectResult], ...] = ()

    def get_children(self):
        for inst in self.results:
            yield from inst


@dataclass(frozen=True)
class AttackResult(EffectResult):
    attack_bonus: int  # does not include -b bonuses
    ac: typing.Optional[int]
    to_hit_roll: typing.Optional[d20.RollResult]  # can be None iff automatic hit/miss - see did_hit
    did_hit: bool
    did_crit: bool
    children: typing.List[EffectResult]


@dataclass(frozen=True)
class SaveResult(EffectResult):
    dc: int
    ability: str
    save_roll: typing.Optional[d20.RollResult]  # None if target is simple or automatic fail/pass
    did_save: bool
    children: typing.List[EffectResult]


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
    effect: 'cogs5e.models.initiative.Effect'
    conc_conflict: typing.List['cogs5e.models.initiative.Effect']


@dataclass(frozen=True)
class RollResult(EffectResult):
    result: int
    roll: d20.RollResult
    simplified: str


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
    children: typing.List[EffectResult]
