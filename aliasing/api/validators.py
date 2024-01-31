"""
Useful validators for methods with complex types (like SimpleCombatant.add_effect()).
"""

from typing import List, Optional, Set

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
    dc_bonus: Optional[int]

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

    def dict(self, *args, **kwargs):
        kwargs.setdefault("by_alias", True)
        return super().dict(*args, **kwargs)


class ButtonInteraction(BaseModel):
    automation: automation_common.validation.ValidatedAutomation
    label: constr(max_length=80, min_length=1, strip_whitespace=True)
    verb: Optional[str255]
    style: Optional[conint(ge=1, le=4)]
    override_default_dc: Optional[int]
    override_default_attack_bonus: Optional[int]
    override_default_casting_mod: Optional[int]


# ==== helpers ====
def unsafeify(safe_thing, interpreter):
    """
    This recursively transforms Draconic safe-types into normal types.
    Note that this makes a copy of any compound type.

    It is possible to make this handle self-references by making the compound type branch cases save a ref to an empty
    container before recursing and adding to it, but this actually breaks pydantic if you feed it a self-referencing
    model, e.g.

    .. code-block:: python

        class Foo(pydantic.BaseModel):
            a: typing.List["Foo"]
        Foo.update_forward_refs()
        a = []
        a.append({'a': a})
        Foo.parse_obj({'a': a})  # RecursionError!

    Therefore, it is intentional that this function raises a ValueError on self-referencing compound types.
    """
    memo_table = {}
    seen = set()

    # noinspection PyProtectedMember
    def unsafety_dance(thing):
        """
        you can dance if you want to
        you can leave your types behind
        """
        # prevent infinite recursion, also make multiple refs to the same thing more efficient
        addr = id(thing)
        if addr in memo_table:
            return memo_table[addr]
        elif addr in seen:
            raise ValueError("Cannot use a self-referencing value here!")

        if isinstance(thing, interpreter._list):
            seen.add(addr)
            result = [unsafety_dance(x) for x in thing]
        elif isinstance(thing, interpreter._set):
            seen.add(addr)
            result = set(unsafety_dance(x) for x in thing)
        elif isinstance(thing, interpreter._dict):
            seen.add(addr)
            result = {unsafety_dance(k): unsafety_dance(v) for k, v in thing.items()}
        elif isinstance(thing, interpreter._str):
            result = str(thing)
        else:
            result = thing

        memo_table[addr] = result
        return result

    return unsafety_dance(safe_thing)
