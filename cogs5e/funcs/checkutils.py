from cogs5e.funcs.dice import roll
from cogs5e.models import embeds
from cogs5e.models.errors import InvalidArgument
from utils.constants import SKILL_MAP, STAT_ABBREVIATIONS
from utils.functions import a_or_an, camel_to_title, verbose_stat


def run_check(skill_key, caster, args, embed):
    skill = caster.skills[skill_key]
    skill_name = camel_to_title(skill_key)
    mod = skill.value

    # str/dex/con/int/wis/cha
    if any(args.last(s, type_=bool) for s in STAT_ABBREVIATIONS):
        base = next(s for s in STAT_ABBREVIATIONS if args.last(s, type_=bool))
        mod = mod - caster.stats.get_mod(SKILL_MAP[skill_key]) + caster.stats.get_mod(base)
        skill_name = f"{verbose_stat(base)} ({skill_name})"

    # -title
    if args.last('title'):
        embed.title = args.last('title', '') \
            .replace('[name]', caster.get_title_name()) \
            .replace('[cname]', skill_name)
    elif args.last('h'):
        embed.title = f"An unknown creature makes {a_or_an(skill_name)} check!"
    else:
        embed.title = f'{caster.get_title_name()} makes {a_or_an(skill_name)} check!'

    _run_common(skill, args, embed, mod_override=mod)


def run_save(save_key, caster, args, embed):
    try:
        save = caster.saves.get(save_key)
        save_name = f"{verbose_stat(save_key[:3]).title()} Save"
    except ValueError:
        raise InvalidArgument('That\'s not a valid save.')

    # -title
    if args.last('title'):
        embed.title = args.last('title', '') \
            .replace('[name]', caster.get_title_name()) \
            .replace('[sname]', save_name)
    elif args.last('h'):
        embed.title = f"An unknown creature makes {a_or_an(save_name)}!"
    else:
        embed.title = f'{caster.get_title_name()} makes {a_or_an(save_name)}!'

    _run_common(save, args, embed, rr_format="Save {}")


def _run_common(skill, args, embed, mod_override=None, rr_format="Check {}"):
    # ephemeral support: adv, b
    # phrase
    phrase = args.join('phrase', '\n')
    # num rolls
    iterations = min(args.last('rr', 1, int), 25)
    # dc
    dc = args.last('dc', type_=int)
    # ro
    ro = args.last('ro', type_=int)
    # mc
    mc = args.last('mc', type_=int)

    desc_out = []
    num_successes = 0

    # add DC text
    if dc:
        desc_out.append(f"**DC {dc}**")

    for i in range(iterations):
        # advantage
        adv = args.adv(boolwise=True, ephem=True)
        # roll bonus
        b = args.join('b', '+', ephem=True)

        # set up dice
        roll_str = skill.d20(base_adv=adv, reroll=ro, min_val=mc, mod_override=mod_override)
        if b is not None:
            roll_str = f"{roll_str}+{b}"

        # roll
        result = roll(roll_str, inline=True)
        if dc and result.total >= dc:
            num_successes += 1

        # output
        if iterations > 1:
            embed.add_field(name=rr_format.format(str(i + 1)), value=result.skeleton)
        else:
            desc_out.append(result.skeleton)

    # phrase
    if phrase:
        desc_out.append(f"*{phrase}*")

    # DC footer
    if iterations > 1 and dc:
        embed.set_footer(text=f"{num_successes} Successes | {iterations - num_successes} Failures")
    elif dc:
        embed.set_footer(text="Success!" if num_successes else "Failure!")

    # build embed
    embed.description = '\n'.join(desc_out)
    embeds.add_fields_from_args(embed, args.get('f'))
