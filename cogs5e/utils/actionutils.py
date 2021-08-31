import itertools

import discord

from cogs5e.models import embeds
from cogs5e.models.errors import RequiresLicense
from gamedata import lookuputils
from utils.functions import a_or_an, maybe_http_url, natural_join, search_and_select


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
    await ctx.trigger_typing()

    # entitlements: ensure runner has access to grantor entity
    source_feature = action.gamedata.source_feature
    available_entity_e10s = await ctx.bot.ddb.get_accessible_entities(
        ctx, ctx.author.id, source_feature.entitlement_entity_type
    )
    if not lookuputils.can_access(source_feature, available_entity_e10s):
        raise RequiresLicense(source_feature, available_entity_e10s is not None)

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
async def send_action_list(ctx, caster, destination=None, attacks=None, actions=None, embed=None, args=None):
    """
    Sends the list of actions and attacks given to the given destination.

    :type ctx: discord.ext.commands.Context
    :type caster: cogs5e.models.sheet.statblock.StatBlock
    :type destination: discord.abc.Messageable
    :type attacks: cogs5e.models.sheet.attack.AttackList
    :type actions: cogs5e.models.sheet.action.Actions
    :type embed: discord.Embed
    :type args: Iterable[str]
    """
    if destination is None:
        destination = ctx
    if embed is None:
        embed = discord.Embed(color=caster.get_color(), title=f"{caster.get_title_name()}'s Actions")
    if args is None:
        args = ()

    await destination.trigger_typing()

    # long embed builder
    ep = embeds.EmbedPaginator(embed)
    fields = []

    # arg setup
    verbose = '-v' in args
    display_attacks = 'attack' in args
    display_actions = 'action' in args
    display_bonus = 'bonus' in args
    display_reactions = 'reaction' in args
    display_other = 'other' in args
    is_display_filtered = any((display_attacks, display_actions, display_bonus, display_reactions, display_other))
    filtered_action_type_strs = list(itertools.compress(
        ('attacks', 'actions', 'bonus actions', 'reactions', 'other actions'),
        (display_attacks, display_actions, display_bonus, display_reactions, display_other)
    ))

    # helpers
    non_automated_count = 0
    non_e10s_count = 0
    e10s_map = {}
    source_names = set()

    # action display
    if attacks and (display_attacks or not is_display_filtered):
        atk_str = attacks.build_str(caster)
        fields.append({'name': 'Attacks', 'value': atk_str})

    # since the sheet displays the description regardless of entitlements, we do here too
    async def add_action_field(title, action_source):
        nonlocal non_automated_count, non_e10s_count  # eh
        action_texts = []
        for action in sorted(action_source, key=lambda a: a.name):
            has_automation = action.uid is not None
            has_e10s = True
            # entitlement stuff
            if has_automation:
                source_feature = action.gamedata.source_feature
                if source_feature.entitlement_entity_type not in e10s_map:
                    e10s_map[source_feature.entitlement_entity_type] = await ctx.bot.ddb.get_accessible_entities(
                        ctx, ctx.author.id, source_feature.entitlement_entity_type
                    )
                source_feature_type_e10s = e10s_map[source_feature.entitlement_entity_type]
                has_e10s = lookuputils.can_access(source_feature, source_feature_type_e10s)
                if not has_e10s:
                    non_e10s_count += 1
                    source_names.add(source_feature.source)

            if verbose:
                name = f"**{action.name}**" if has_automation and has_e10s else f"***{action.name}***"
                action_texts.append(f"{name}: {action.build_str(caster=caster, snippet=True)}")
            elif has_automation:
                name = f"**{action.name}**" if has_e10s else f"***{action.name}***"
                action_texts.append(f"**{name}**: {action.build_str(caster=caster, snippet=False)}")

            # count these for extra display
            if not has_automation:
                non_automated_count += 1
        if not action_texts:
            return
        action_text = '\n'.join(action_texts)
        fields.append({'name': title, 'value': action_text})

    if actions is not None:
        if actions.full_actions and (display_actions or not is_display_filtered):
            await add_action_field("Actions", actions.full_actions)
        if actions.bonus_actions and (display_bonus or not is_display_filtered):
            await add_action_field("Bonus Actions", actions.bonus_actions)
        if actions.reactions and (display_reactions or not is_display_filtered):
            await add_action_field("Reactions", actions.reactions)
        if actions.other_actions and (display_other or not is_display_filtered):
            await add_action_field("Other", actions.other_actions)

    # build embed

    # description: filtering help
    description = ""
    if not fields:
        if is_display_filtered:
            description = f"{caster.get_title_name()} has no {natural_join(filtered_action_type_strs, 'or')}."
        else:
            description = f"{caster.get_title_name()} has no actions."
    elif is_display_filtered:
        description = f"Only displaying {natural_join(filtered_action_type_strs, 'and')}."

    # description: entitlements help
    if not verbose and actions and non_e10s_count:
        has_ddb_link = any(v is not None for v in e10s_map.values())
        if not has_ddb_link:
            description = (f"{description}\nItalicized actions are for display only and cannot be run. "
                           f"Connect your D&D Beyond account to unlock the full potential of these actions!")
        else:
            source_names = natural_join([lookuputils.long_source_name(s) for s in source_names], 'and')
            description = (f"{description}\nItalicized actions are for display only and cannot be run. Unlock "
                           f"{source_names} on your D&D Beyond account to unlock the full potential of these actions!")
    if description:
        ep.add_description(description.strip())

    # fields
    for field in fields:
        ep.add_field(**field)

    # footer
    if not verbose and actions:
        if non_automated_count:
            ep.set_footer(value=f"Use the -v argument to view each action's full description "
                                f"and {non_automated_count} display-only actions.")
        else:
            ep.set_footer(value=f"Use the -v argument to view each action's full description.")
    elif verbose and (non_automated_count or non_e10s_count):
        ep.set_footer(value="Italicized actions are for display only and cannot be run.")

    await ep.send_to(destination)
