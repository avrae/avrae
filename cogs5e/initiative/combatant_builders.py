from d20 import roll
from disnake.ext import commands
from cogs5e.models.sheet.base import BaseStats, Levels, Saves, Skill, Skills
from cogs5e.models.sheet.resistance import Resistances
from utils.constants import STAT_ABBR_MAP
from utils.argparser import argparse
from cogs5e.initiative.effects.passive import resolve_check_advs, resolve_save_advs
from .utils import create_combatant_id
from . import (
    Combatant,
    utils,
)

async def add_builder(ctx, combat, name, args):
    args = argparse(args)
    private = False
    place = None
    controller = ctx.author.id
    group = None
    hp = None
    ac = None
    resists = {}
    adv = args.adv(boolwise=True)

    if combat.get_combatant(name, True) is not None:
        await ctx.send("Combatant already exists.")
        return

    id = create_combatant_id()

    if args.last("controller"):
        controller_name = args.last("controller")
        member = await commands.MemberConverter().convert(ctx, controller_name)
        controller = member.id if member is not None and not member.bot else controller

    if args.last("h", type_=bool):
        private = True

    note = args.last("note")

    stats = BaseStats(
        args.last("pb", type_=int, default=0),
        args.last("str", type_=int, default=10),
        args.last("dex", type_=int, default=10),
        args.last("con", type_=int, default=10),
        args.last("int", type_=int, default=10),
        args.last("wis", type_=int, default=10),
        args.last("cha", type_=int, default=10),
    )

    cr = args.last("cr", type_=int, default=0)
    levels = Levels({"Monster": cr})

    exps = resolve_check_advs(args.get("exp"))
    profs = resolve_check_advs(args.get("prof"))-exps
    skills = Skills.default(stats)
    for skill in profs:
        skills[skill].prof = 1
        skills[skill].value += stats.prof_bonus    
    for skill in exps:
        skills[skill].prof = 2
        skills[skill].value += 2*stats.prof_bonus

    if args.get("p"):
        init = args.last("p",type_=int)
    else:
        init = roll(skills.initiative.d20()).total

    if args.adv:
        skills.initiative.adv = adv

    resolved_saves = resolve_save_advs(args.get("save"))
    saves = Saves.default(stats)
    for ability in resolved_saves:
        save_key = STAT_ABBR_MAP[ability].lower()+"Save"
        saves[save_key].prof = 1
        saves[save_key].value += stats.prof_bonus

    for k in ("resist", "immune", "vuln"):
        resists[k] = args.get(k)

    if args.last("ac"):
        ac = args.last("ac", type_=int)

    if args.last("hp"):
        hp = args.last("hp", type_=int)
        if hp < 1:
            return await ctx.send("You must pass in a positive, nonzero HP with the -hp tag.")

    thp = args.last("thp", type_=int)

    creature_type = args.last("type", type_=str, default=None)

    me = Combatant(
        ctx = ctx,
        combat = combat,
        id = id,
        name = name,
        controller_id = controller,
        private = private,
        init = init,
        notes = note,
        # statblock info
        stats = stats,
        levels = levels,
        skills = skills,
        saves = saves,
        resistances = Resistances.from_dict(resists),
        ac = ac,
        max_hp = hp,
        temp_hp = thp,
        creature_type = creature_type,
    )

    return me
