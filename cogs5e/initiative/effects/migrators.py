from typing import TYPE_CHECKING

from cogs5e.models.sheet.attack import Attack
from cogs5e.models.sheet.resistance import Resistance
from utils.enums import AdvantageType
from utils.functions import reconcile_adv
from .effect import InitEffectReference, InitiativeEffect
from .interaction import AttackInteraction
from .passive import InitPassiveEffect

if TYPE_CHECKING:
    from ..combat import Combat
    from ..combatant import Combatant


def jit_v1_to_v2(d: dict, combat: "Combat", combatant: "Combatant") -> InitiativeEffect:
    name = d["name"]

    # migrate effects to passive/interactions
    data = d["effect"]

    # bonus/value handling
    ac_value = None
    ac_bonus = None
    try:
        ac_data = data.get("ac", "")
        if ac_data.startswith(("+", "-")):
            ac_bonus = int(ac_data)
        elif ac_data:
            ac_value = int(ac_data)
    except (ValueError, TypeError):
        pass

    max_hp_value = None
    max_hp_bonus = None
    try:
        max_hp_data = data.get("maxhp", "")
        if max_hp_data.startswith(("+", "-")):
            max_hp_bonus = int(max_hp_data)
        elif max_hp_data:
            max_hp_value = int(max_hp_data)
    except (ValueError, TypeError):
        pass

    effects = InitPassiveEffect(
        attack_advantage=AdvantageType(reconcile_adv(adv=data.get("adv"), dis=data.get("dis"), ea=data.get("eadv"))),
        to_hit_bonus=data.get("b"),
        damage_bonus=data.get("d"),
        magical_damage=bool(data.get("magical")),
        silvered_damage=bool(data.get("silvered")),
        resistances=[Resistance.from_str(v) for v in data.get("resist", [])],
        immunities=[Resistance.from_str(v) for v in data.get("immune", [])],
        vulnerabilities=[Resistance.from_str(v) for v in data.get("vuln", [])],
        ignored_resistances=[Resistance.from_str(v) for v in data.get("neutral", [])],
        ac_value=ac_value,
        ac_bonus=ac_bonus,
        max_hp_value=max_hp_value,
        max_hp_bonus=max_hp_bonus,
        save_bonus=data.get("sb"),
        save_adv=set(data.get("sadv", [])),
        save_dis=set(data.get("sdis", [])),
        check_bonus=data.get("cb"),
    )
    attacks = []
    if data.get("attack"):
        attacks.append(AttackInteraction(attack=Attack.from_dict(data["attack"])))

    # migrate ticks to end round
    end_round = None
    end_on_turn_end = d["tonend"]
    if d["remaining"] > 0:
        end_round = combat.round_num + d["remaining"]
        # if we are going to tick this effect once this round, subtract 1 from the end round
        has_ticked_this_round = combat.index is not None and (
            combat.index > combatant.index if end_on_turn_end else combat.index >= combatant.index
        )
        if not has_ticked_this_round:
            end_round -= 1

    # parent/children
    children = [InitEffectReference.from_dict(r) for r in d["children"]]
    if parent_data := d["parent"]:
        parent = InitEffectReference.from_dict(parent_data)
    else:
        parent = None

    return InitiativeEffect(
        combat=combat,
        combatant=combatant,
        id=d["id"],
        name=name,
        effects=effects,
        attacks=attacks,
        duration=d["duration"],
        end_round=end_round,
        end_on_turn_end=end_on_turn_end,
        concentration=d["concentration"],
        children=children,
        parent=parent,
        desc=d["desc"],
    )
