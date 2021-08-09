import itertools

import discord

from cogs5e.models import embeds
from utils.functions import a_or_an, natural_join, maybe_http_url, search_and_select


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
            .replace('[aname]', attack_name) \
            .replace('[verb]', verb)
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
        embed.set_thumbnail(url=maybe_http_url(args.last('thumb', '')))

    return result


async def select_action(ctx, name, attacks, actions=None, allow_no_automation=False, **kwargs):
    """
    Prompts the user to select an action from the caster's valid list of runnable actions, or returns a single
    unambiguous action.

    :type ctx: discord.ext.commands.Context
    :type name: str
    :type attacks: cogs5e.models.sheet.attack.AttackList
    :type actions: cogs5e.models.sheet.action.Actions
    :param bool allow_no_automation:
        When selecting from a player's action list, whether to allow returning an action that has no action gamedata.
    :rtype: cogs5e.models.sheet.attack.Attack or cogs5e.models.sheet.action.Action
    """
    if actions is None:
        actions = []
    elif not allow_no_automation:
        actions = filter(lambda action: action.uid is not None, actions)

    return await search_and_select(
        ctx,
        list_to_search=list(itertools.chain(attacks, actions)),
        query=name,
        key=lambda a: a.name,
        **kwargs
    )


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
    non_automated_count = 0

    # action display
    if attacks and (display_attacks or not is_display_filtered):
        atk_str = attacks.build_str(caster)
        embeds.add_fields_from_long_text(embed, field_name="Attacks", text=atk_str)

    # since the sheet displays the description regardless of entitlements, we do here too
    def add_action_field(title, action_source):
        nonlocal non_automated_count  # eh
        action_texts = []
        for action in sorted(action_source, key=lambda a: a.name):
            if verbose:
                name = f"**{action.name}**" if action.uid is not None else f"***{action.name}***"
                action_texts.append(f"{name}: {action.build_str(caster=caster, automation_only=False)}")
            elif action.uid is not None:
                action_texts.append(f"**{action.name}**: {action.build_str(caster=caster, automation_only=True)}")
            # count these for extra display
            if action.uid is None:
                non_automated_count += 1
        if not action_texts:
            return
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
        if non_automated_count:
            embed.set_footer(text=f"Use the -v argument to view each action's full description "
                                  f"and {non_automated_count} display-only actions.")
        else:
            embed.set_footer(text="Use the -v argument to view each action's full description.")
    elif verbose and non_automated_count:
        embed.set_footer(text="Italicized actions are for display only and cannot be run.")

    await destination.send(embed=embed)
