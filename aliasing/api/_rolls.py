"""Shared save and check rolls for scripting statblocks."""

from d20 import ast, parse, roll

from cogs5e.models.errors import InvalidSaveType
from utils.argparser import argparse
from utils.constants import SKILL_MAP
from utils.dice import get_roll_comment


def _roll_with_args(dice, args, *, is_check=False):
    # Import here to avoid the cycle through combat and automation.
    from aliasing.api.functions import SimpleRollResult

    bonuses = args.get("b", ephem=True)
    if is_check and args.last("guidance", type_=bool):
        bonuses.append("1d4 [guidance]")
    if bonuses:
        comments = []
        for bonus in bonuses:
            if not bonus:
                continue
            bonus_dice, comment = get_roll_comment(bonus)
            dice = f"{dice}+({bonus_dice})"
            if comment:
                comments.append(comment)
        dice_ast = parse(dice)
        dice = ast.Expression(dice_ast.roll, comment=" ".join(comments) or None)
    return SimpleRollResult(roll(dice))


def roll_save(statblock, ability, adv=None, include_ieffects=False, args=None, *, combatant=None, character=None):
    from cogs5e.models.automation.utils import parse_save_bonuses

    try:
        save = statblock.saves.get(str(ability))
    except ValueError:
        raise InvalidSaveType

    args = argparse(str(args) if args is not None else "")
    save_bonuses = []
    if combatant is not None:
        save_bonuses = combatant.active_effects(mapper=lambda effect: effect.effects.save_bonus, default=[])
    sb = parse_save_bonuses(ability, save_bonuses)

    final_adv = adv if adv is not None else args.adv(boolwise=True, ephem=True)
    if include_ieffects and combatant is not None:
        stat = str(ability)[:3].lower()
        sadv_effects = combatant.active_effects(
            mapper=lambda effect: effect.effects.save_adv,
            reducer=lambda saves: set().union(*saves),
            default=set(),
        )
        sdis_effects = combatant.active_effects(
            mapper=lambda effect: effect.effects.save_dis,
            reducer=lambda saves: set().union(*saves),
            default=set(),
        )
        if final_adv is None and "adv" not in args and "dis" not in args:
            if stat in sadv_effects:
                final_adv = True
            elif stat in sdis_effects:
                final_adv = False

    reroll = character.options.reroll if character is not None else None
    reroll = args.last("ro", reroll, int)
    min_val = args.last("mc", type_=int)
    saveroll = save.d20(base_adv=final_adv, reroll=reroll, min_val=min_val)
    if sb:
        saveroll = f'{saveroll}+{"+".join(sb)}'
    return _roll_with_args(saveroll, args)


def roll_check(statblock, skill_name, adv=None, include_ieffects=False, args=None, *, combatant=None, character=None):
    try:
        skill, skill_key = statblock.skills.get(str(skill_name), return_name=True)
    except ValueError:
        raise ValueError(f"Invalid skill: {skill_name}")

    args = argparse(str(args) if args is not None else "")
    final_adv = adv if adv is not None else args.adv(boolwise=True, ephem=True)
    combat_bonuses = []
    if include_ieffects and combatant is not None:
        base_ability_key = SKILL_MAP[skill_key]
        combat_bonuses = combatant.active_effects(mapper=lambda effect: effect.effects.check_bonus, default=[])
        cadv_effects = combatant.active_effects(
            mapper=lambda effect: effect.effects.check_adv,
            reducer=lambda checks: set().union(*checks),
            default=set(),
        )
        cdis_effects = combatant.active_effects(
            mapper=lambda effect: effect.effects.check_dis,
            reducer=lambda checks: set().union(*checks),
            default=set(),
        )
        if final_adv is None and "adv" not in args and "dis" not in args:
            if skill_key in cadv_effects or base_ability_key in cadv_effects:
                final_adv = True
            elif skill_key in cdis_effects or base_ability_key in cdis_effects:
                final_adv = False

    reroll = None
    min_val = None
    if character is not None:
        reroll = character.options.reroll
        if character.options.talent and skill.prof >= 1:
            min_val = 10

    reroll = args.last("ro", reroll, int)
    min_val = args.last("mc", min_val, int)
    roll_str = skill.d20(base_adv=final_adv, reroll=reroll, min_val=min_val)
    if combat_bonuses:
        roll_str = f"{roll_str}+{'+'.join(combat_bonuses)}"
    return _roll_with_args(roll_str, args, is_check=True)
