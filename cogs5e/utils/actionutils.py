import itertools
from collections import namedtuple

import discord

from cogs5e.initiative import InitiativeEffect
from cogs5e.initiative.types import BaseCombatant
from cogs5e.models import embeds
from cogs5e.models.errors import InvalidArgument, InvalidSpellLevel, RequiresLicense
from gamedata import lookuputils
from utils import constants
from utils.functions import a_or_an, confirm, maybe_http_url, natural_join, search_and_select, smart_trim, verbose_stat


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
    if not args.last("h", type_=bool):
        name = caster.get_title_name()
    else:
        name = "An unknown creature"

    if not attack.proper:
        attack_name = a_or_an(attack.name)
    else:
        attack_name = attack.name

    verb = attack.verb or "attacks with"

    if args.last("title") is not None:
        embed.title = args.last("title").replace("[name]", name).replace("[aname]", attack_name).replace("[verb]", verb)
    else:
        embed.title = f"{name} {verb} {attack_name}!"

    # arg overrides (#1163)
    arg_defaults = {
        "criton": attack.criton,
        "phrase": attack.phrase,
        "thumb": attack.thumb,
        "c": attack.extra_crit_damage,
    }
    args.update_nx(arg_defaults)

    return await run_automation(ctx, embed, args, caster, attack.automation, targets, combat)


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

    if not args.last("h", type_=bool):
        name = caster.get_title_name()
    else:
        name = "An unknown creature"

    if args.last("title") is not None:
        embed.title = args.last("title").replace("[name]", name).replace("[aname]", action.name)
    else:
        embed.title = f"{name} uses {action.name}!"

    if action.automation is not None:
        return await run_automation(ctx, embed, args, caster, action.automation, targets, combat)

    # else, show action description and note that it can't be automated
    if action.snippet:
        embed.description = action.snippet
    else:
        embed.description = "Unknown action effect."
    embed.set_footer(text="No action automation found.")
    return None


async def cast_spell(spell, ctx, caster, targets, args, combat=None):
    """
    Casts this spell.

    :param spell: The spell to cast.
    :param ctx: The context of the casting.
    :param caster: The caster of this spell.
    :type caster: :class:`~cogs5e.models.sheet.statblock.StatBlock`
    :param targets: A list of targets
    :type targets: list of :class:`~cogs5e.models.sheet.statblock.StatBlock`
    :param args: Args
    :type args: :class:`~utils.argparser.ParsedArguments`
    :param combat: The combat the spell was cast in, if applicable.
    :rtype: CastResult
    """

    # generic args
    cast_level = args.last("l", spell.level, int)
    ignore = args.last("i", type_=bool)
    title = args.last("title")
    nopact = args.last("nopact", type_=bool)

    # meta checks
    if not spell.level <= cast_level <= 9:
        raise InvalidSpellLevel()

    # caster spell-specific overrides
    dc_override = None
    ab_override = None
    spell_override = None
    is_prepared = True
    spellbook_spell = caster.spellbook.get_spell(spell)
    if spellbook_spell is not None:
        dc_override = spellbook_spell.dc
        ab_override = spellbook_spell.sab
        spell_override = spellbook_spell.mod
        is_prepared = spellbook_spell.prepared

    if not ignore:
        # if I'm a warlock, and I didn't have any slots of this level anyway (#655)
        # automatically scale up to our pact slot level (or the next available level s.t. max > 0)
        if (
            cast_level > 0
            and cast_level == spell.level
            and not caster.spellbook.get_max_slots(cast_level)
            and not caster.spellbook.can_cast(spell, cast_level)
        ):
            if caster.spellbook.pact_slot_level is not None:
                cast_level = caster.spellbook.pact_slot_level
            else:
                cast_level = next(
                    (sl for sl in range(cast_level, 6) if caster.spellbook.get_max_slots(sl)), cast_level
                )  # only scale up to l5
            args["l"] = cast_level

        # can I cast this spell?
        if not caster.spellbook.can_cast(spell, cast_level):
            embed = embeds.EmbedWithAuthor(ctx)
            embed.title = "Cannot cast spell!"
            if not caster.spellbook.get_slots(cast_level):
                # out of spell slots
                err = (
                    f"You don't have enough level {cast_level} slots left! Use `-l <level>` to cast at a different "
                    f"level, `{ctx.prefix}g lr` to take a long rest, or `-i` to ignore spell slots!"
                )
            elif spell.name not in caster.spellbook:
                # don't know spell
                err = (
                    f"You don't know this spell! Use `{ctx.prefix}sb add {spell.name}` to add it to your "
                    f"spellbook, or pass `-i` to ignore restrictions."
                )
            else:
                # ?
                err = (
                    "Not enough spell slots remaining, or spell not in known spell list!\n"
                    f"Use `{ctx.prefix}game longrest` to restore all spell slots if this is a character, "
                    f"or pass `-i` to ignore restrictions."
                )
            embed.description = err
            if cast_level > 0:
                embed.add_field(name="Spell Slots", value=caster.spellbook.remaining_casts_of(spell, cast_level))
            return CastResult(embed=embed, success=False, automation_result=None)

        # #1000: is this spell prepared (soft check)?
        if not is_prepared:
            skip_prep_conf = await confirm(
                ctx,
                f"{spell.name} is not prepared. Do you want to cast it anyway? (Reply with yes/no)",
                delete_msgs=True,
            )
            if not skip_prep_conf:
                embed = embeds.EmbedWithAuthor(
                    ctx,
                    title=f"Cannot cast spell!",
                    description=f"{spell.name} is not prepared! Prepare it on your character sheet and use "
                    f"`{ctx.prefix}update` to mark it as prepared, or use `-i` to ignore restrictions.",
                )
                return CastResult(embed=embed, success=False, automation_result=None)

        # use resource
        caster.spellbook.cast(spell, cast_level, pact=not nopact)

    # base stat stuff
    mod_arg = args.last("mod", type_=int)
    with_arg = args.last("with")
    stat_override = ""
    if mod_arg is not None:
        mod = mod_arg
        prof_bonus = caster.stats.prof_bonus
        dc_override = 8 + mod + prof_bonus
        ab_override = mod + prof_bonus
        spell_override = mod
    elif with_arg is not None:
        if with_arg not in constants.STAT_ABBREVIATIONS:
            raise InvalidArgument(f"{with_arg} is not a valid stat to cast with.")
        mod = caster.stats.get_mod(with_arg)
        dc_override = 8 + mod + caster.stats.prof_bonus
        ab_override = mod + caster.stats.prof_bonus
        spell_override = mod
        stat_override = f" with {verbose_stat(with_arg)}"

    # begin setup
    embed = discord.Embed()
    if title:
        embed.title = (
            title.replace("[name]", caster.name)
            .replace("[aname]", spell.name)
            .replace("[sname]", spell.name)
            .replace("[verb]", "casts")
        )  # #1514, [aname] is action name now, #1587, add verb to action/cast
    else:
        embed.title = f"{caster.get_title_name()} casts {spell.name}{stat_override}!"
    if targets is None:
        targets = [None]

    # concentration
    noconc = args.last("noconc", type_=bool)
    conc_conflict = None
    conc_effect = None
    if all((spell.concentration, isinstance(caster, BaseCombatant), combat, not noconc)):
        duration = args.last("dur", spell.get_combat_duration(), int)
        conc_effect = InitiativeEffect.new(
            combat=combat, combatant=caster, name=spell.name, duration=duration, effect_args="", concentration=True
        )
        # noinspection PyUnresolvedReferences
        effect_result = caster.add_effect(conc_effect)
        conc_conflict = effect_result["conc_conflict"]

    # run
    automation_result = None
    if spell.automation and spell.automation.effects:
        embed.title = f"{caster.name} cast {spell.name}!"
        # todo update this to use modular AutomationContext
        # automation_result = await spell.automation.run(
        #     ctx,
        #     embed,
        #     caster,
        #     targets,
        #     args,
        #     combat,
        #     spell,
        #     conc_effect=conc_effect,
        #     ab_override=ab_override,
        #     dc_override=dc_override,
        #     spell_override=spell_override,
        #     title=title,
        # )
        automation_result = await run_automation(
            ctx, embed, args, caster, spell.automation, targets, combat, always_commit_caster=True
        )
    else:  # no automation, display spell description
        phrase = args.join("phrase", "\n")
        if phrase:
            embed.description = f"*{phrase}*"
        embed.add_field(name="Description", value=smart_trim(spell.description), inline=False)
        embed.set_footer(text="No spell automation found.")

    if cast_level != spell.level and spell.higherlevels:
        embed.add_field(name="At Higher Levels", value=smart_trim(spell.higherlevels), inline=False)

    if cast_level > 0 and not ignore:
        embed.add_field(name="Spell Slots", value=caster.spellbook.remaining_casts_of(spell, cast_level))

    if conc_conflict:
        conflicts = ", ".join(e.name for e in conc_conflict)
        embed.add_field(name="Concentration", value=f"Dropped {conflicts} due to concentration.")

    if "thumb" not in args and spell.image:
        embed.set_thumbnail(url=spell.image)
    lookuputils.handle_source_footer(embed, spell, add_source_str=False)

    return CastResult(embed=embed, success=True, automation_result=automation_result)


CastResult = namedtuple("CastResult", "embed success automation_result")


async def run_automation(ctx, embed, args, caster, automation, targets, combat, always_commit_caster=False):
    """
    Common automation runner

    :type ctx: discord.ext.commands.Context
    :type embed: discord.Embed
    :type args: utils.argparser.ParsedArguments
    :type caster: cogs5e.models.sheet.statblock.StatBlock
    :type automation: cogs5e.models.automation.Automation
    :type targets: list of str or list of cogs5e.models.sheet.statblock.StatBlock
    :type combat: None or cogs5e.models.initiative.Combat
    :rtype: cogs5e.models.automation.AutomationResult
    """
    result = await automation.run(ctx, embed, caster, targets, args, combat=combat, title=embed.title)
    if combat:
        await combat.final()
    # commit character only if we have not already committed it via combat final
    if always_commit_caster or (
        result.caster_needs_commit and hasattr(caster, "commit") and not (combat and caster in combat.get_combatants())
    ):
        await caster.commit(ctx)

    embeds.add_fields_from_args(embed, args.get("f"))
    if "thumb" in args:
        embed.set_thumbnail(url=maybe_http_url(args.last("thumb", "")))

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
        actions = filter(lambda action: action.automation is not None, actions)

    return await search_and_select(
        ctx, list_to_search=list(itertools.chain(attacks, actions)), query=name, key=lambda a: a.name, **kwargs
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
    verbose = "-v" in args
    display_attacks = "attack" in args
    display_actions = "action" in args
    display_bonus = "bonus" in args
    display_reactions = "reaction" in args
    display_other = "other" in args
    is_display_filtered = any((display_attacks, display_actions, display_bonus, display_reactions, display_other))
    filtered_action_type_strs = list(
        itertools.compress(
            ("attacks", "actions", "bonus actions", "reactions", "other actions"),
            (display_attacks, display_actions, display_bonus, display_reactions, display_other),
        )
    )

    # helpers
    non_automated_count = 0
    non_e10s_count = 0
    e10s_map = {}
    source_names = set()

    # action display
    if attacks and (display_attacks or not is_display_filtered):
        atk_str = attacks.build_str(caster)
        fields.append({"name": "Attacks", "value": atk_str})

    # since the sheet displays the description regardless of entitlements, we do here too
    async def add_action_field(title, action_source):
        nonlocal non_automated_count, non_e10s_count  # eh
        action_texts = []
        for action in sorted(action_source, key=lambda a: a.name):
            has_automation = action.gamedata is not None
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
        action_text = "\n".join(action_texts)
        fields.append({"name": title, "value": action_text})

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
            description = (
                f"{description}\nItalicized actions are for display only and cannot be run. "
                f"Connect your D&D Beyond account to unlock the full potential of these actions!"
            )
        else:
            source_names = natural_join([lookuputils.long_source_name(s) for s in source_names], "and")
            description = (
                f"{description}\nItalicized actions are for display only and cannot be run. Unlock "
                f"{source_names} on your D&D Beyond account to unlock the full potential of these actions!"
            )
    if description:
        ep.add_description(description.strip())

    # fields
    for field in fields:
        ep.add_field(**field)

    # footer
    if not verbose and actions:
        if non_automated_count:
            ep.set_footer(
                value=f"Use the -v argument to view each action's full description "
                f"and {non_automated_count} display-only actions."
            )
        else:
            ep.set_footer(value=f"Use the -v argument to view each action's full description.")
    elif verbose and (non_automated_count or non_e10s_count):
        ep.set_footer(value="Italicized actions are for display only and cannot be run.")

    await ep.send_to(destination)
