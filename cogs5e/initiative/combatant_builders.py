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


# ==== helpers ====
def resolve_n_arg(n: str) -> tuple[int, str | None]:
    """
    Given a string, parse it as an integer or roll it as dice and return a tuple representing
    (final_int, roll_result?).

    The final result is clamped s.t. 1 <= final_int <= 25.

    As the name suggests, this is used for the `-n` arg in !init add and !init madd.
    """
    msg = None
    try:
        n_result = int(n)
    except TypeError:
        # it was None
        return 1, None
    except ValueError:
        # it was a string, but not an int
        roll_result = roll(n)
        n_result = roll_result.total
        msg = f"Rolling random number of combatants: {roll_result}"

    return min(25, max(1, n_result)), msg


class NameBuilder:
    """
    Class to generate combatant names following a given pattern for a given combat.
    This is stateful because the name number is independent from the n-th combatant added (e.g. the 3rd kobold
    may be KO3, or KO5, or KO173), and searching for the smallest number each time is O(n). Thus adding *n* combatants
    would be O(n^2).
    This solution is O(n) amortized to add *n* combatants.
    """

    def __init__(self, pattern: str, combat, *, always_number_first_name=True):
        self.pattern = pattern
        self.combat = combat
        self.always_number_first_name = always_number_first_name
        self.name_num = 1

    def next(self) -> str:
        """
        Returns the next valid name to add, or raises an InvalidArgument if it can't find a valid name.

        If *always_number_first_name* is True or the pattern contains *#*, the first name will be numbered, otherwise
        a number will be added to the end of the name pattern only for the 2nd+ name.
        """
        if self.name_num == 1 and "#" not in self.pattern and not self.always_number_first_name:
            if self.combat.get_combatant(self.pattern, strict=True):
                raise InvalidArgument("A combatant with that name already exists.")
        elif "#" not in self.pattern:
            self.pattern = self.pattern + "#"

        name = self.pattern.replace("#", str(self.name_num))
        while self.combat.get_combatant(name, strict=True) and self.name_num < 100:
            self.name_num += 1
            name = self.pattern.replace("#", str(self.name_num))

        if self.combat.get_combatant(name, strict=True):
            raise InvalidArgument(f"Could not find a valid name for combatant with pattern {self.pattern!r}!")

        self.name_num += 1
        return name


# ==== builders ====
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
