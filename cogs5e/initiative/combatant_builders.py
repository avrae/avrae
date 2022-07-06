from d20 import roll
from d20 import roll
from disnake.ext import commands
from cogs5e.models.sheet.base import BaseStats, Levels, Saves, Skills
from cogs5e.models.sheet.resistance import Resistances
from utils.constants import STAT_ABBR_MAP
from utils.argparser import ParsedArguments
from cogs5e.models.errors import InvalidArgument
from cogs5e.initiative.effects.passive import resolve_check_advs, resolve_save_advs
from .utils import create_combatant_id
from . import (
    Combatant,
    utils,
)


async def add_builder(ctx, combat, name, modifier: int, args: ParsedArguments):
    private = False
    place = None
    controller = ctx.author.id
    hp = None
    ac = None
    resists = {}
    adv = args.adv()

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
        args.last("strength", type_=int, default=10),
        args.last("dexterity", type_=int, default=10),
        args.last("constitution", type_=int, default=10),
        args.last("intelligence", type_=int, default=10),
        args.last("wisdom", type_=int, default=10),
        args.last("charisma", type_=int, default=10),
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
    
    skills.initiative.value = modifier
    if adv:
        skills.initiative.adv = adv

    if args.get("p"):
        try:
            place_arg = args.last("p")
            if place_arg is True:
                place = modifier
            else:
                place = int(place_arg)
        except (ValueError, TypeError):
            place = modifier

    if place is None:
        init_roll = roll(skills.initiative.d20())
        init = init_roll.total
    else:
        init_roll = int(place)
        init = int(place)

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
            raise InvalidArgument("You must pass in a positive, nonzero HP with the -hp tag.")

    thp = args.last("thp", type_=int)

    creature_type = args.last("type", type_=str, default=None)

    me = Combatant(
        ctx=ctx,
        combat=combat,
        id=id,
        name=name,
        controller_id = controller,
        private = private,
        init=init,
        notes = note,
        # statblock info
        stats=stats,
        levels=levels,
        skills=skills,
        saves=saves,
        resistances = Resistances.from_dict(resists),
        ac=ac,
        max_hp = hp,
        temp_hp = thp,
        creature_type=creature_type,
    )

    return me, init_roll
