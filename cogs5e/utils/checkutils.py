from collections import namedtuple

from d20 import roll

import cogs5e.models.initiative as init
from cogs5e.models import embeds
from cogs5e.models.errors import InvalidArgument
from cogs5e.models.sheet.base import Skill
from utils.constants import SKILL_MAP, STAT_ABBREVIATIONS
from utils.functions import a_or_an, camel_to_title, verbose_stat


def update_csetting_args(char, args, skill=None):
    """
    Updates a ParsedArguments with arguments representing a character's csettings.

    :type char: cogs5e.models.character.Character
    :type args: utils.argparser.ParsedArguments
    :type skill: cogs5e.models.sheet.base.Skill or None
    :return:
    """
    # reliable talent (#654)
    rt = bool(char.get_setting('talent', 0) and (skill and skill.prof >= 1))
    args['mc'] = args.get('mc') or 10 * rt

    # halfling luck
    args['ro'] = char.get_setting('reroll')


def run_check(skill_key, caster, args, embed):
    """
    Runs a caster's skill check, building on an existing embed and handling most arguments.

    :type skill_key: str
    :type caster: cogs5e.models.sheet.statblock.StatBlock
    :type args: utils.argparser.ParsedArguments
    :type embed: discord.Embed
    :return: The total of each check.
    :rtype: CheckResult
    """
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

    # ieffect -cb
    if isinstance(caster, init.Combatant):
        args['b'] = args.get('b') + caster.active_effects('cb')

    result = _run_common(skill, args, embed, mod_override=mod)
    return CheckResult(rolls=result.rolls, skill=skill, skill_name=skill_name, skill_roll_result=result)


def run_save(save_key, caster, args, embed):
    """
    Runs a caster's saving throw, building on an existing embed and handling most arguments.

    Also handles save bonuses from ieffects if caster is a combatant.

    :type save_key: str
    :type caster: cogs5e.models.sheet.statblock.StatBlock
    :type args: utils.argparser.ParsedArguments
    :type embed: discord.Embed
    :return: The total of each save.
    :rtype: SaveResult
    """
    if save_key.startswith('death'):
        save = Skill(0)
        stat_name = stat = 'Death'
        save_name = 'Death Save'
    else:
        try:
            save = caster.saves.get(save_key)
            stat = save_key[:3]
            stat_name = verbose_stat(stat).title()
            save_name = f"{stat_name} Save"
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

    # ieffect handling
    if isinstance(caster, init.Combatant):
        # -sb
        args['b'] = args.get('b') + caster.active_effects('sb')
        # -sadv/sdis
        sadv_effects = caster.active_effects('sadv')
        sdis_effects = caster.active_effects('sdis')
        if 'all' in sadv_effects or stat in sadv_effects:
            args['adv'] = True  # Because adv() only checks last() just forcibly add them
        if 'all' in sdis_effects or stat in sdis_effects:
            args['dis'] = True

    result = _run_common(save, args, embed, rr_format="Save {}")
    return SaveResult(rolls=result.rolls, skill=save, skill_name=stat_name, skill_roll_result=result)


def _run_common(skill, args, embed, mod_override=None, rr_format="Check {}"):
    """
    Runs a roll for a given Skill.

    :rtype: SkillRollResult
    """
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
    results = []

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
        result = roll(roll_str)
        if dc and result.total >= dc:
            num_successes += 1

        results.append(result)

        # output
        if iterations > 1:
            embed.add_field(name=rr_format.format(str(i + 1)), value=result.result)
        else:
            desc_out.append(result.result)

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
    if 'thumb' in args:
        embed.set_thumbnail(url=args.last('thumb'))

    return SkillRollResult(rolls=results, iterations=iterations, dc=dc, successes=num_successes)


SkillRollResult = namedtuple('SkillRollResult', 'rolls iterations dc successes')
CheckResult = namedtuple('CheckResult', 'rolls skill skill_name skill_roll_result')
SaveResult = namedtuple('SaveResult', 'rolls skill skill_name skill_roll_result')
