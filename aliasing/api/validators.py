"""
Useful validators for methods with complex types (like SimpleCombatant.add_effect()).
"""
from typing import List, Optional, Sequence, Set

import automation_common
from pydantic import BaseModel, conint, constr, validator

import cogs5e.initiative as init
from cogs5e.models.errors import InvalidArgument
from utils import enums

str255 = constr(max_length=255)


# noinspection PyMethodParameters
class PassiveEffects(BaseModel):
    attack_advantage: Optional[enums.AdvantageType]
    to_hit_bonus: Optional[str255]
    damage_bonus: Optional[str255]
    magical_damage: Optional[bool]
    silvered_damage: Optional[bool]
    resistances: Optional[List[str255]]
    immunities: Optional[List[str255]]
    vulnerabilities: Optional[List[str255]]
    ignored_resistances: Optional[List[str255]]
    ac_value: Optional[int]
    ac_bonus: Optional[int]
    max_hp_value: Optional[int]
    max_hp_bonus: Optional[int]
    save_bonus: Optional[str255]
    save_adv: Optional[Set[str]]
    save_dis: Optional[Set[str]]
    check_bonus: Optional[str255]
    check_adv: Optional[Set[str]]
    check_dis: Optional[Set[str]]

    @validator("save_adv", "save_dis")
    def check_valid_save_keys(cls, value):
        try:
            return init.effects.passive.resolve_save_advs(value)
        except InvalidArgument as e:
            raise ValueError(str(e)) from e

    @validator("check_adv", "check_dis")
    def check_valid_check_keys(cls, value):
        try:
            return init.effects.passive.resolve_check_advs(value)
        except InvalidArgument as e:
            raise ValueError(str(e)) from e


class AttackInteraction(BaseModel):
    attack: automation_common.validation.models.AttackModel
    override_default_dc: Optional[int]
    override_default_attack_bonus: Optional[int]
    override_default_casting_mod: Optional[int]


class AttackInteractionList(BaseModel):
    __root__: Sequence[AttackInteraction]


class ButtonInteraction(BaseModel):
    automation: automation_common.validation.ValidatedAutomation
    label: constr(max_length=80, min_length=1, strip_whitespace=True)
    verb: Optional[str255]
    style: Optional[conint(ge=1, le=4)]
    override_default_dc: Optional[int]
    override_default_attack_bonus: Optional[int]
    override_default_casting_mod: Optional[int]


class ButtonInteractionList(BaseModel):
    __root__: Sequence[ButtonInteraction]
