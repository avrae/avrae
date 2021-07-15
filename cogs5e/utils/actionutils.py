import itertools

import discord

from cogs5e.models import embeds
from utils.functions import a_or_an, natural_join


async def run_attack(ctx, embed, args, caster, attack, targets, combat):
    """
    Runs an attack: adds title, handles -f and -thumb args, commits combat, runs automation, edits embed.

    :type ctx: discord.ext.commands.Context
    :type embed: discord.Embed
    :type args: utils.argparser.ParsedArguments
    :type caster: cogs5e.models.sheet.statblock.StatBlock
    :type attack: cogs5e.models.sheet.attack.Attack
    :type targets: list of str or list of cogs5e.models.sheet.statblock.StatBlock
    :type combat: None or cogs5e.models.initiative.Combat
    :rtype: cogs5e.models.automation.AutomationResult
    """
    if not args.last('h', type_=bool):
        name = caster.get_title_name()
    else:
        name = "An unknown creature"

    if not attack.proper:
        attack_name = a_or_an(attack.name)
    else:
        attack_name = attack.name

    verb = attack.verb or "attacks with"

    if args.last('title') is not None:
        embed.title = args.last('title') \
            .replace('[name]', name) \
            .replace('[aname]', attack_name)
    else:
        embed.title = f'{name} {verb} {attack_name}!'

    # arg overrides (#1163)
    arg_defaults = {
        'criton': attack.criton, 'phrase': attack.phrase, 'thumb': attack.thumb, 'c': attack.extra_crit_damage
    }
    args.update_nx(arg_defaults)

    return await _run_common(ctx, embed, args, caster, attack, targets, combat)


async def run_action(ctx, embed, args, caster, action, targets, combat):
    """
    Runs an action: adds title, handles -f and -thumb args, commits combat, runs automation, edits embed.

    :type ctx: discord.ext.commands.Context
    :type embed: discord.Embed
    :type args: utils.argparser.ParsedArguments
    :type caster: cogs5e.models.character.Character
    :type action: cogs5e.models.sheet.action.Action
    :type targets: list of str or list of cogs5e.models.sheet.statblock.StatBlock
    :type combat: None or cogs5e.models.initiative.Combat
    :rtype: cogs5e.models.automation.AutomationResult or None
    """
    if not args.last('h', type_=bool):
        name = caster.get_title_name()
    else:
        name = "An unknown creature"

    if args.last('title') is not None:
        embed.title = args.last('title') \
            .replace('[name]', name) \
            .replace('[aname]', action.name)
    else:
        embed.title = f'{name} uses {action.name}!'

    if action.automation is not None:
        return await _run_common(ctx, embed, args, caster, action, targets, combat)

    # else, show action description and note that it can't be automated
    if action.snippet:
        embed.description = action.snippet
    else:
        embed.description = "Unknown action effect."
    embed.set_footer(text="No action automation found.")
    return None


async def _run_common(ctx, embed, args, caster, action, targets, combat):
    """
    Common automation runner for attacks/actions

    :type ctx: discord.ext.commands.Context
    :type embed: discord.Embed
    :type args: utils.argparser.ParsedArguments
    :type caster: cogs5e.models.sheet.statblock.StatBlock
    :type action: cogs5e.models.sheet.attack.Attack or cogs5e.models.sheet.action.Action
    :type targets: list of str or list of cogs5e.models.sheet.statblock.StatBlock
    :type combat: None or cogs5e.models.initiative.Combat
    :rtype: cogs5e.models.automation.AutomationResult
    """
    result = await action.automation.run(ctx, embed, caster, targets, args, combat=combat, title=embed.title)
    if combat:
        await combat.final()
    # commit character only if we have not already committed it via combat final
    if result.caster_needs_commit and hasattr(caster, 'commit') and not (combat and caster in combat.get_combatants()):
        await caster.commit(ctx)

    embeds.add_fields_from_args(embed, args.get('f'))
    if 'thumb' in args:
        embed.set_thumbnail(url=args.last('thumb'))

    return result


# ==== action display ====
async def send_action_list(destination, caster, attacks=None, actions=None, embed=None, args=None):
    """
    Sends the list of actions and attacks given to the given destination.

    :type destination: discord.abc.Messageable
    :type caster: cogs5e.models.sheet.statblock.StatBlock
    :type attacks: cogs5e.models.sheet.attack.AttackList
    :type actions: cogs5e.models.sheet.action.Actions
    :type embed: discord.Embed
    :type args: Iterable[str]
    """
    if embed is None:
        embed = discord.Embed(color=caster.get_color(), title=f"{caster.get_title_name()}'s Actions")
    if args is None:
        args = ()

    # arg setup
    verbose = '-v' in args
    display_attacks = 'attacks' in args
    display_actions = 'actions' in args
    display_bonus = 'bonus' in args
    display_reactions = 'reactions' in args
    display_other = 'other' in args
    is_display_filtered = any((display_attacks, display_actions, display_bonus, display_reactions, display_other))
    filtered_action_type_strs = list(itertools.compress(
        ('attacks', 'actions', 'bonus actions', 'reactions', 'other actions'),
        (display_attacks, display_actions, display_bonus, display_reactions, display_other)
    ))

    # action display
    if attacks and (display_attacks or not is_display_filtered):
        atk_str = attacks.build_str(caster)
        embeds.add_fields_from_long_text(embed, field_name="Attacks", text=atk_str)

    # since the sheet displays the description regardless of entitlements, we do here too
    def add_action_field(title, action_source):
        action_texts = (f"**{action.name}**: {action.build_str(caster=caster, automation_only=not verbose)}"
                        for action in action_source)
        action_text = '\n'.join(action_texts)
        embeds.add_fields_from_long_text(embed, field_name=title, text=action_text)

    if actions is not None:
        if actions.full_actions and (display_actions or not is_display_filtered):
            add_action_field("Actions", actions.full_actions)
        if actions.bonus_actions and (display_bonus or not is_display_filtered):
            add_action_field("Bonus Actions", actions.bonus_actions)
        if actions.reactions and (display_reactions or not is_display_filtered):
            add_action_field("Reactions", actions.reactions)
        if actions.other_actions and (display_other or not is_display_filtered):
            add_action_field("Other", actions.other_actions)

    # misc helper displays
    if not embed.fields:
        if is_display_filtered:
            embed.description = f"{caster.get_title_name()} has no {natural_join(filtered_action_type_strs, 'or')}."
        else:
            embed.description = f"{caster.get_title_name()} has no actions."
    elif is_display_filtered:
        embed.description = f"Only displaying {natural_join(filtered_action_type_strs, 'and')}."

    if not verbose and actions:
        embed.set_footer(text="Use the -v argument to view each action's full description.")

    await destination.send(embed=embed)
