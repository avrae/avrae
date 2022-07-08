import d20
from d20 import roll
from disnake.ext import commands

from cogs5e.initiative.effects.passive import resolve_check_advs, resolve_save_advs
from cogs5e.models.errors import InvalidArgument
from cogs5e.models.sheet.base import BaseStats, Levels, Saves, Skills
from cogs5e.models.sheet.resistance import Resistances
from utils.argparser import ParsedArguments
from utils.constants import SAVE_NAMES, STAT_ABBREVIATIONS
from .combatant import Combatant
from .utils import create_combatant_id


async def basic_combatant(
    ctx, combat, name: str, modifier: int, args: ParsedArguments
) -> tuple[Combatant, d20.RollResult | int]:
    """Creates a basic Combatant instance for the combat in the current context."""
    combatant_id = create_combatant_id()

    # controller
    controller = ctx.author.id
    if args.last("controller"):
        controller_name = args.last("controller")
        member = await commands.MemberConverter().convert(ctx, controller_name)
        controller = member.id if member is not None and not member.bot else controller

    # init meta-options
    private = False
    if args.last("h", type_=bool):
        private = True

    note = args.last("note")

    # ability scores
    stats = BaseStats(
        args.last("pb", type_=int, default=0),
        args.last("strength", type_=int, default=10),
        args.last("dexterity", type_=int, default=10),
        args.last("constitution", type_=int, default=10),
        args.last("intelligence", type_=int, default=10),
        args.last("wisdom", type_=int, default=10),
        args.last("charisma", type_=int, default=10),
    )

    # skills
    exps = resolve_check_advs(args.get("exp"))
    profs = resolve_check_advs(args.get("prof")) - exps
    skills = Skills.default(stats)
    for skill in profs:
        skills[skill].prof = 1
        skills[skill].value += stats.prof_bonus
    for skill in exps:
        skills[skill].prof = 2
        skills[skill].value += 2 * stats.prof_bonus

    # -p / modifier / init roll handling
    adv = args.adv(boolwise=True)
    skills.initiative.value = modifier
    if adv is not None:
        skills.initiative.adv = adv

    place = None
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
        init_roll = init = place

    # saves
    resolved_saves = resolve_save_advs(args.get("save"))
    saves = Saves.default(stats)
    for ability in resolved_saves:
        save_key = SAVE_NAMES[STAT_ABBREVIATIONS.index(ability)]
        saves[save_key].prof = 1
        saves[save_key].value += stats.prof_bonus

    # resistances
    resists = {}
    for k in ("resist", "immune", "vuln"):
        resists[k] = args.get(k)
    resistances = Resistances.from_dict(resists)

    # ac
    ac = args.last("ac", type_=int)

    # hp / thp
    hp = None
    if args.last("hp"):
        hp = args.last("hp", type_=int)
        if hp < 1:
            raise InvalidArgument("You must pass in a positive, nonzero HP with the -hp tag.")

    thp = args.last("thp", type_=int, default=0)

    # cr / monster information
    cr = args.last("cr", type_=float, default=0)
    levels = Levels({"Monster": cr})
    creature_type = args.last("type", type_=str, default=None)

    me = Combatant(
        ctx=ctx,
        combat=combat,
        id=combatant_id,
        name=name,
        controller_id=controller,
        private=private,
        init=init,
        notes=note,
        # statblock info
        stats=stats,
        levels=levels,
        skills=skills,
        saves=saves,
        resistances=resistances,
        ac=ac,
        max_hp=hp,
        temp_hp=thp,
        creature_type=creature_type,
    )

    return me, init_roll
