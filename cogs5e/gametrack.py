"""
Created on Jul 28, 2017

Most of this module was coded 5 miles in the air. (Aug 8, 2017)

@author: andrew
"""

import collections
import logging
import re

import d20
from disnake.ext import commands

from aliasing import helpers
from cogs5e.models import embeds
from cogs5e.models.character import Character, CustomCounter
from cogs5e.models.embeds import EmbedWithCharacter
from cogs5e.models.errors import ConsumableException, InvalidArgument, NoSelectionElements
from cogs5e.utils import actionutils, checkutils, gameutils, targetutils
from cogs5e.utils.gameutils import resolve_strict_coins
from cogs5e.utils.help_constants import *
from gamedata.lookuputils import get_spell_choices, select_spell_full
from utils.constants import COUNTER_BUBBLES
from utils.argparser import argparse
from utils.functions import confirm, maybe_mod, search, search_and_select, try_delete

log = logging.getLogger(__name__)


class GameTrack(commands.Cog):
    """Commands to help track game resources."""

    def __init__(self, bot):
        self.bot = bot

    # ===== bot commands =====
    @commands.group(name="game", aliases=["g"])
    async def game(self, ctx):
        """Commands to help track character information in a game. Use `!help game` to view subcommands."""
        if ctx.invoked_subcommand is None:
            await ctx.send(f"Incorrect usage. Use {ctx.prefix}help game for help.")
        await try_delete(ctx.message)

    @game.command(name="status", aliases=["summary"])
    async def game_status(self, ctx):
        """Prints the status of the current active character."""
        character: Character = await ctx.get_character()
        embed = EmbedWithCharacter(character)
        embed.add_field(name="Hit Points", value=character.hp_str())
        embed.add_field(name="Spell Slots", value=character.spellbook.slots_str())
        if character.death_saves.successes != 0 or character.death_saves.fails != 0:
            embed.add_field(name="Death Saves", value=str(character.death_saves))
        for counter in character.consumables:
            embed.add_field(name=counter.name, value=counter.full_str())
        await ctx.send(embed=embed)

    @game.command(name="spellbook", aliases=["sb"], hidden=True)
    async def game_spellbook(self, ctx):
        """**DEPRECATED** - use `!spellbook` instead."""
        await self.spellbook(ctx)

    @game.command(name="spellslot", aliases=["ss"])
    async def game_spellslot(self, ctx, level: int = None, value: str = None, *args):
        """
        Views or sets your remaining spell slots.
        __Valid Arguments__
        nopact - Modifies normal spell slots first instead of a Pact Magic slots, if applicable.
        """
        if level is not None:
            try:
                assert 0 < level < 10
            except AssertionError:
                return await ctx.send("Invalid spell level.")
        character: Character = await ctx.get_character()
        embed = EmbedWithCharacter(character)

        if level is None and value is None:  # show remaining
            embed.description = f"__**Remaining Spell Slots**__\n{character.spellbook.slots_str()}"
        elif value is None:
            embed.description = f"__**Remaining Level {level} Spell Slots**__\n{character.spellbook.slots_str(level)}"
        else:
            old_slots = character.spellbook.get_slots(level)
            value = maybe_mod(value, old_slots)
            character.spellbook.set_slots(level, value, pact="nopact" not in args)
            await character.commit(ctx)
            embed.description = (
                f"__**Remaining Level {level} Spell Slots**__\n"
                f"{character.spellbook.slots_str(level)} ({(value - old_slots):+})"
            )

        bubble = COUNTER_BUBBLES["bubble"]
        pact = COUNTER_BUBBLES["square"]

        # footer - pact vs non pact
        if character.spellbook.max_pact_slots is not None:
            embed.set_footer(
                text=f"{bubble.filled} = Available / {bubble.empty} = Used\n{pact.filled} / {pact.empty} = Pact Slot"
            )
        else:
            embed.set_footer(text=f"{bubble.filled} = Available / {bubble.empty} = Used")

        await ctx.send(embed=embed)

    async def _rest(self, ctx, rest_type, *args):
        """
        Runs a rest.

        :param ctx: The Context.
        :param character: The Character.
        :param rest_type: "long", "short", "all"
        :param args: a list of args.
        """
        character: Character = await ctx.get_character()
        old_hp = character.hp
        old_slots = {lvl: character.spellbook.get_slots(lvl) for lvl in range(1, 10)}

        embed = EmbedWithCharacter(character, name=False)
        if rest_type == "long":
            reset_counters = character.long_rest()
            embed.title = f"{character.name} took a Long Rest!"
        elif rest_type == "short":
            reset_counters = character.short_rest()
            embed.title = f"{character.name} took a Short Rest!"
        elif rest_type == "all":
            reset_counters = character.reset_all_consumables()
            embed.title = f"{character.name} reset all counters!"
        else:
            raise ValueError(f"Invalid rest type: {rest_type}")

        if "-h" in args:
            values = ", ".join(
                set(ctr.name for ctr, _ in reset_counters) | {"Hit Points", "Death Saves", "Spell Slots"}
            )
            embed.add_field(name="Reset Values", value=values)
        else:
            # hp
            hp_delta = character.hp - old_hp
            hp_delta_str = ""
            if hp_delta:
                hp_delta_str = f" ({hp_delta:+})"
            embed.add_field(name="Hit Points", value=f"{character.hp_str()}{hp_delta_str}")

            # slots
            slots_out = []
            slots_delta = {lvl: character.spellbook.get_slots(lvl) - old_slots[lvl] for lvl in range(1, 10)}
            for lvl in range(1, 10):
                if character.spellbook.get_max_slots(lvl):
                    if slots_delta[lvl]:
                        slots_out.append(f"{character.spellbook.slots_str(lvl)} ({slots_delta[lvl]:+})")
                    else:
                        slots_out.append(character.spellbook.slots_str(lvl))
            if slots_out:
                embed.add_field(name="Spell Slots", value="\n".join(slots_out))

            # ccs
            counters_out = []
            for counter, result in reset_counters:
                if result.new_value != result.old_value:
                    counters_out.append(f"{counter.name}: {str(counter)} ({result.delta})")
                else:
                    counters_out.append(f"{counter.name}: {str(counter)}")
            if counters_out:
                embed.add_field(name="Reset Counters", value="\n".join(counters_out))

        await character.commit(ctx)
        await ctx.send(embed=embed)

    @game.command(name="longrest", aliases=["lr"])
    async def game_longrest(self, ctx, *args):
        """Performs a long rest, resetting applicable counters.
        __Valid Arguments__
        -h - Hides the character summary output."""
        await self._rest(ctx, "long", *args)

    @game.command(name="shortrest", aliases=["sr"])
    async def game_shortrest(self, ctx, *args):
        """Performs a short rest, resetting applicable counters.
        __Valid Arguments__
        -h - Hides the character summary output."""
        await self._rest(ctx, "short", *args)

    @game.group(name="coinpurse", aliases=["coins", "coin"], invoke_without_command=True)
    async def game_coinpurse(self, ctx, *, args=None):
        """Manage your character's coinpurse.
        __Valid Subcommands__
        `!game coins` - Show your current coinpurse.
        `!game coins [pp|gp|ep|sp|cp]` - Show the amount of a single currency contained in your coinpurse.
        `!game coins <amount>` - Add or remove a given amount of currency. The amount can either be a number like `+102.13` (gold pieces), or explicit numbers of currencies like `+10pp +2gp +1sp +3cp`.
        """
        character: Character = await ctx.get_character()

        if args is None:
            return await gameutils.send_current_coin(ctx, character)

        if re.fullmatch(r"[pgesc]p", args, re.IGNORECASE):
            return await gameutils.send_current_coin(ctx, character, args)

        coins = gameutils.parse_coin_args(args)
        deltas = await resolve_strict_coins(character.coinpurse, coins, ctx, character.options.autoconvert_coins)
        character.coinpurse.update_currency(deltas)
        await character.commit(ctx)
        return await gameutils.send_current_coin(ctx, character, deltas=deltas)

    @game_coinpurse.command(name="convert", aliases=["consolidate"])
    async def game_coinpurse_convert(self, ctx):
        """Converts all of your coins into the highest value coins possible.
        100cp turns into 1gp, 5sp turns into 1ep, etc."""
        character: Character = await ctx.get_character()
        deltas = character.coinpurse.consolidate_coins()
        await character.commit(ctx)
        return await gameutils.send_current_coin(ctx, character, deltas=deltas)

    @game.group(name="hp", invoke_without_command=True)
    async def game_hp(self, ctx, *, hp: str = None):
        """Modifies the HP of the current active character."""
        character: Character = await ctx.get_character()
        caster = await targetutils.maybe_combat_caster(ctx, character)

        if hp is None:
            return await gameutils.send_hp_result(ctx, caster)

        hp_roll = d20.roll(hp)
        caster.modify_hp(hp_roll.total)
        await character.commit(ctx)
        if "d" in hp:
            delta = hp_roll.result
        else:
            delta = f"{hp_roll.total:+}"
        await gameutils.send_hp_result(ctx, caster, delta)

    @game_hp.command(name="max")
    async def game_hp_max(self, ctx):
        """Sets the character's HP to their maximum."""
        character: Character = await ctx.get_character()
        caster = await targetutils.maybe_combat_caster(ctx, character)

        before = caster.hp
        caster.hp = caster.max_hp
        await character.commit(ctx)
        await gameutils.send_hp_result(ctx, caster, f"{caster.hp - before:+}")

    @game_hp.command(name="mod", hidden=True)
    async def game_hp_mod(self, ctx, *, hp):
        """Modifies the character's current HP."""
        await ctx.invoke(self.game_hp, hp=hp)

    @game_hp.command(name="set")
    async def game_hp_set(self, ctx, *, hp):
        """Sets the character's HP to a certain value."""
        character: Character = await ctx.get_character()
        caster = await targetutils.maybe_combat_caster(ctx, character)

        before = caster.hp
        hp_roll = d20.roll(hp)
        caster.hp = hp_roll.total
        await character.commit(ctx)
        await gameutils.send_hp_result(ctx, caster, f"{caster.hp - before:+}")

    @game.command(name="thp")
    async def game_thp(self, ctx, *, thp: str = None):
        """Modifies the temp HP of the current active character.
        If positive, assumes set; if negative, assumes mod."""
        character: Character = await ctx.get_character()
        caster = await targetutils.maybe_combat_caster(ctx, character)

        if thp is None:
            return await gameutils.send_hp_result(ctx, caster)

        thp_roll = d20.roll(thp)
        value = thp_roll.total

        if value >= 0:
            caster.temp_hp = value
        else:
            caster.temp_hp += value

        await character.commit(ctx)

        delta = ""
        if "d" in thp:
            delta = f"({thp_roll.result})"
        await gameutils.send_hp_result(ctx, caster, delta)

    @game.group(name="deathsave", aliases=["ds"], invoke_without_command=True)
    async def game_deathsave(self, ctx, *, args=""):
        """Commands to manage character death saves.
        __Valid Arguments__
        See `!help save`."""
        character: Character = await ctx.get_character()

        embed = EmbedWithCharacter(character, name=False)

        args = await helpers.parse_snippets(args, ctx, character=character)
        args = argparse(args)
        checkutils.update_csetting_args(character, args)
        caster, _, _ = await targetutils.maybe_combat(ctx, character, args)
        result = checkutils.run_save("death", caster, args, embed)

        dc = result.skill_roll_result.dc or 10
        death_phrase = ""

        for save_roll in result.skill_roll_result.rolls:
            if save_roll.crit == d20.CritType.CRIT:
                character.hp = 1
            elif save_roll.crit == d20.CritType.FAIL:
                character.death_saves.fail(2)
            elif save_roll.total >= dc:
                character.death_saves.succeed()
            else:
                character.death_saves.fail()

            if save_roll.crit == d20.CritType.CRIT:
                death_phrase = f"{character.name} is UP with 1 HP!"
                break
            elif character.death_saves.is_dead():
                death_phrase = f"{character.name} is DEAD!"
                break
            elif character.death_saves.is_stable():
                death_phrase = f"{character.name} is STABLE!"
                break

        if death_phrase:
            embed.set_footer(text=death_phrase)
        embed.add_field(name="Death Saves", value=str(character.death_saves), inline=False)

        await character.commit(ctx)
        await ctx.send(embed=embed)
        await try_delete(ctx.message)
        if gamelog := self.bot.get_cog("GameLog"):
            await gamelog.send_save(ctx, character, result.skill_name, result.rolls)

    @game_deathsave.command(name="success", aliases=["s", "save"])
    async def game_deathsave_save(self, ctx):
        """Adds a successful death save."""
        character: Character = await ctx.get_character()

        embed = EmbedWithCharacter(character)
        embed.title = f"{character.name} succeeds a Death Save!"

        character.death_saves.succeed()
        await character.commit(ctx)

        if character.death_saves.is_stable():
            embed.set_footer(text=f"{character.name} is STABLE!")
        embed.description = "Added 1 successful death save."
        embed.add_field(name="Death Saves", value=str(character.death_saves))

        await ctx.send(embed=embed)

    @game_deathsave.command(name="fail", aliases=["f"])
    async def game_deathsave_fail(self, ctx):
        """Adds a failed death save."""
        character: Character = await ctx.get_character()

        embed = EmbedWithCharacter(character)
        embed.title = f"{character.name} fails a Death Save!"

        character.death_saves.fail()
        await character.commit(ctx)

        if character.death_saves.is_dead():
            embed.set_footer(text=f"{character.name} is DEAD!")
        embed.description = "Added 1 failed death save."
        embed.add_field(name="Death Saves", value=str(character.death_saves))

        await ctx.send(embed=embed)

    @game_deathsave.command(name="reset")
    async def game_deathsave_reset(self, ctx):
        """Resets all death saves."""
        character: Character = await ctx.get_character()
        character.death_saves.reset()
        await character.commit(ctx)

        embed = EmbedWithCharacter(character)
        embed.title = f"{character.name} reset Death Saves!"
        embed.add_field(name="Death Saves", value=str(character.death_saves))

        await ctx.send(embed=embed)

    @commands.group(invoke_without_command=True, name="spellbook", aliases=["sb"])
    async def spellbook(self, ctx, *args):
        """
        Commands to display a character's known spells and metadata.
        __Valid Arguments__
        all - Display all of a character's known spells, including unprepared ones.
        """
        await ctx.trigger_typing()

        character: Character = await ctx.get_character()
        ep = embeds.EmbedPaginator(EmbedWithCharacter(character))
        ep.add_field(name="DC", value=str(character.spellbook.dc), inline=True)
        ep.add_field(name="Spell Attack Bonus", value=str(character.spellbook.sab), inline=True)
        ep.add_field(name="Spell Slots", value=character.spellbook.slots_str() or "None", inline=True)

        show_unprepared = "all" in args
        known_count = len(character.spellbook.spells)
        prepared_count = sum(1 for spell in character.spellbook.spells if spell.prepared)

        if known_count == prepared_count:
            ep.add_description(f"{character.name} knows {known_count} spells.")
        else:
            ep.add_description(f"{character.name} has {prepared_count} spells prepared and knows {known_count} spells.")

        # dynamic help flags
        flag_show_multiple_source_help = False
        flag_show_homebrew_help = False
        flag_show_prepared_help = False
        flag_show_prepared_underline_help = False

        spells_known = collections.defaultdict(lambda: [])
        choices = await get_spell_choices(ctx)
        for sb_spell in character.spellbook.spells:
            if not (sb_spell.prepared or show_unprepared):
                flag_show_prepared_help = True
                continue

            # homebrew / multisource formatting
            results, strict = search(choices, sb_spell.name, lambda sp: sp.name, strict=True)
            if not strict:
                known_level = "unknown"
                if len(results) > 1:
                    formatted = f"*{sb_spell.name} ({'*' * len(results)})*"
                    flag_show_multiple_source_help = True
                else:
                    formatted = f"*{sb_spell.name}*"
                flag_show_homebrew_help = True
            else:
                spell = results
                known_level = str(spell.level)
                if spell.homebrew:
                    formatted = f"*{spell.name}*"
                    flag_show_homebrew_help = True
                else:
                    formatted = spell.name

            # prepared formatting
            if show_unprepared and sb_spell.prepared:
                formatted = f"__{formatted}__"
                flag_show_prepared_underline_help = True

            spells_known[known_level].append(formatted)

        level_name = {
            "0": "Cantrips",
            "1": "1st Level",
            "2": "2nd Level",
            "3": "3rd Level",
            "4": "4th Level",
            "5": "5th Level",
            "6": "6th Level",
            "7": "7th Level",
            "8": "8th Level",
            "9": "9th Level",
        }
        for level, spells in sorted(list(spells_known.items()), key=lambda k: k[0]):
            if spells:
                spells.sort(key=lambda s: s.lstrip("*_"))
                ep.add_field(name=level_name.get(level, "Unknown"), value=", ".join(spells), inline=False)

        # dynamic help
        footer_out = []
        if flag_show_homebrew_help:
            footer_out.append("An italicized spell indicates that the spell is homebrew.")
        if flag_show_multiple_source_help:
            footer_out.append("Asterisks after a spell indicates that the spell is being provided by multiple sources.")
        if flag_show_prepared_help:
            footer_out.append(f'Unprepared spells were not shown. Use "{ctx.prefix}spellbook all" to view them!')
        if flag_show_prepared_underline_help:
            footer_out.append("Prepared spells are marked with an underline.")

        if footer_out:
            ep.set_footer(value=" ".join(footer_out))
        await ep.send_to(ctx)

    @spellbook.command(name="add")
    async def spellbook_add(self, ctx, spell_name, *, args=""):
        """
        Adds a spell to the spellbook override.

        __Valid Arguments__
        *Note: These arguments do not support calculations.*
        -dc <dc> - When cast, this spell always uses this DC.
        -b <sab> - When cast, this spell always uses this spell attack bonus.
        -mod <mod> - When cast, this spell always uses this as the value of its casting stat (usually for healing spells).
        """  # noqa: E501
        spell = await select_spell_full(ctx, spell_name)
        character: Character = await ctx.get_character()
        args = argparse(args)

        dc = args.last("dc", type_=int)
        sab = args.last("b", type_=int)
        mod = args.last("mod", type_=int)
        character.add_known_spell(spell, dc, sab, mod)
        await character.commit(ctx)
        await ctx.send(f"{spell.name} added to known spell list!")

    @spellbook.command(name="remove")
    async def spellbook_remove(self, ctx, *, spell_name):
        """
        Removes a spell from the spellbook override.
        """
        character: Character = await ctx.get_character()

        spell_to_remove = await search_and_select(
            ctx,
            character.overrides.spells,
            spell_name,
            lambda s: s.name,
            message="To remove a spell on your sheet, just delete it there and `!update`.",
        )
        character.remove_known_spell(spell_to_remove)

        await character.commit(ctx)
        await ctx.send(f"{spell_to_remove.name} removed from spellbook override.")

    @spellbook.command(name="remove_all", aliases=["removeall"])
    async def spellbook_remove_all(self, ctx):
        """
        Removes all spell overrides from the spellbook.
        """
        character: Character = await ctx.get_character()

        num_to_remove = len(character.overrides.spells)
        if not num_to_remove:
            return await ctx.send("You have no spellbook overrides.")

        if not await confirm(
            ctx,
            (
                f"This will remove {num_to_remove} override{'s' if num_to_remove>1 else ''} from your spellbook. "
                "Are you *absolutely sure* you want to continue?"
            ),
        ):
            return await ctx.send("Unconfirmed. Cancelling.")

        character.remove_all_known_spells()

        await character.commit(ctx)
        await ctx.send(f"{num_to_remove} spells removed from spellbook override.")

    @commands.group(invoke_without_command=True, name="customcounter", aliases=["cc"])
    async def customcounter(self, ctx, name=None, *, modifier=None):
        """Commands to implement custom counters.
        If a modifier is not supplied, prints the value and metadata of the counter *name*.
        Otherwise, changes the counter *name* by *modifier*. Supports dice.

        The following can be put after the counter *name* to change how the *modifier* is applied:
        `mod` - Add *modifier* counter value
        `set` - Sets the counter value to *modifier*

        *Ex:*
        `!cc Test 1`
        `!cc Test -2*2d4`
        `!cc Test set 1d4`

        """
        if name is None:
            return await self.customcounter_summary(ctx)
        character: Character = await ctx.get_character()
        counter = await character.select_consumable(ctx, name)

        cc_embed_title = counter.title if counter.title is not None else counter.name

        # replace [name] in title
        cc_embed_title = cc_embed_title.replace("[name]", character.name)

        if modifier is None:  # display value
            counter_display_embed = EmbedWithCharacter(character)
            counter_display_embed.add_field(name=counter.name, value=counter.full_str())
            if counter.desc:
                counter_display_embed.add_field(name="Description", value=counter.desc, inline=False)
            return await ctx.send(embed=counter_display_embed)

        operator = None
        if " " in modifier:
            m = modifier.split(" ")
            operator = m[0]
            modifier = m[-1]

        roll_text = ""
        try:
            result = int(modifier)
        except ValueError:
            try:  # if we're not a number, are we dice
                roll_result = d20.roll(str(modifier))
                result = roll_result.total
                roll_text = f"\nRoll: {roll_result}"
            except d20.RollSyntaxError:
                raise InvalidArgument(
                    f"Could not modify counter: {modifier} cannot be interpreted as a number or dice string."
                )

        old_value = counter.value
        result_embed = EmbedWithCharacter(character)
        if not operator or operator == "mod":
            new_value = counter.value + result
        elif operator == "set":
            new_value = result
        elif name in ("set", "mod"):
            return await ctx.send(f"Invalid operator. Did you mean `{ctx.prefix}cc {operator} {name} {modifier}`?")
        else:
            return await ctx.send("Invalid operator. Use mod or set.")

        counter.set(new_value)
        await character.commit(ctx)

        delta = f"({counter.value - old_value:+})"
        out = f"{str(counter)} {delta}{roll_text}"

        if new_value - counter.value:  # we overflowed somewhere
            out += f"\n({abs(new_value - counter.value)} overflow)"

        result_embed.add_field(name=cc_embed_title, value=out)

        if counter.desc:
            result_embed.add_field(name="Description", value=counter.desc, inline=False)

        await try_delete(ctx.message)
        await ctx.send(embed=result_embed)

    @customcounter.command(name="create")
    async def customcounter_create(self, ctx, name, *, args=""):
        """
        Creates a new custom counter.
        __Valid Arguments__
        `-title <title>` - Sets the title for the output when modifying the counter. `[name]` will be replaced with the player's name.
        `-desc <desc>` - Sets the description when setting or viewing the counter.
        `-reset <short|long|none>` - Counter will reset to max on a short/long rest, or not ever when "none". Default - will reset on a call of `!cc reset`.
        `-max <max value>` - The maximum value of the counter.
        `-min <min value>` - The minimum value of the counter.
        `-value <value>` - The initial value for the counter.
        `-type <bubble|square|hex|star|default>` - Whether the counter displays bubbles/squares/hexes/stars to show remaining uses or numbers. Default - numbers.
        `-resetto <value>` - The value to reset the counter to. Default - maximum.
        `-resetby <value>` - Rather than resetting to a certain value, modify the counter by this much per reset. Supports annotated dice strings.
        """  # noqa: E501
        character: Character = await ctx.get_character()

        conflict = next((c for c in character.consumables if c.name.lower() == name.lower()), None)
        if conflict:
            if await confirm(ctx, "Warning: This will overwrite an existing consumable. Continue? (Reply with yes/no)"):
                character.consumables.remove(conflict)
            else:
                return await ctx.send("Overwrite unconfirmed. Cancelling.")

        args = argparse(args)
        _reset = args.last("reset")
        _max = args.last("max")
        _min = args.last("min")
        _type = args.last("type")
        reset_to = args.last("resetto")
        reset_by = args.last("resetby")
        initial_value = args.last("value")
        title = args.last("title")
        desc = args.last("desc")
        try:
            new_counter = CustomCounter.new(
                character,
                name,
                maxv=_max,
                minv=_min,
                reset=_reset,
                display_type=_type,
                reset_to=reset_to,
                reset_by=reset_by,
                initial_value=initial_value,
                title=title,
                desc=desc,
            )
            character.consumables.append(new_counter)
            await character.commit(ctx)
        except InvalidArgument as e:
            return await ctx.send(f"Failed to create counter: {e}")
        else:
            await ctx.send(f"Custom counter created.\n**{name}**\n{new_counter.full_str()}")

    @customcounter.command(name="edit")
    async def customcounter_edit(self, ctx, name, *, args=""):
        """
        Edits an existing custom counter replacing passed arguments.

        Pass `none` to remove an argument entirely.
        Will clamp counter value to new limits if needed.

        __Valid Arguments__
        `-name <name>` - Rename the counter.
        `-title <title>` - Sets the title for the output when modifying the counter. `[name]` will be replaced with the player's name.
        `-desc <desc>` - Sets the description when setting or viewing the counter.
        `-reset <short|long|none>` - Counter will reset to max on a short/long rest, or not ever when "none". Default - will reset on a call of `!cc reset`.
        `-max <max value>` - The maximum value of the counter.
        `-min <min value>` - The minimum value of the counter.
        `-type <bubble|square|hex|star|default>` - Whether the counter displays bubbles/squares/hexes/stars to show remaining uses or numbers. Default - numbers.
        `-resetto <value>` - The value to reset the counter to. Default - maximum.
        `-resetby <value>` - Rather than resetting to a certain value, modify the counter by this much per reset. Supports annotated dice strings.
        """  # noqa: E501
        character: Character = await ctx.get_character()
        counter = await character.select_consumable(ctx, name)
        # pull in the new values, or existing ones
        args = argparse(args)
        e_name = args.last("name", counter.name)
        e_reset = args.last("reset", counter.reset_on)
        e_max = args.last("max", counter.max)
        e_min = args.last("min", counter.min)
        e_type = args.last("type", counter.display_type)
        e_reset_to = args.last("resetto", counter.reset_to)
        e_reset_by = args.last("resetby", counter.reset_by)
        e_title = args.last("title", counter.title)
        e_desc = args.last("desc", counter.desc)
        # Clamp the values to None if we want to remove them instead
        _reset = e_reset if e_reset and e_reset.lower() != "none" else None
        _max = e_max if e_max and e_max.lower() != "none" else None
        _min = e_min if e_min and e_min.lower() != "none" else None
        _type = e_type if e_type and e_type.lower() != "none" else None
        reset_to = e_reset_to if e_reset_to and e_reset_to.lower() != "none" else None
        reset_by = e_reset_by if e_reset_by and e_reset_by.lower() != "none" else None
        title = e_title if e_title and e_title.lower() != "none" else None
        desc = e_desc if e_desc and e_desc.lower() != "none" else None

        try:
            new_counter = CustomCounter.new(
                character,
                name=e_name,
                maxv=_max,
                minv=_min,
                reset=_reset,
                display_type=_type,
                reset_to=reset_to,
                reset_by=reset_by,
                title=title,
                desc=desc,
            )
        except InvalidArgument as e:
            return await ctx.send(f"Failed to edit counter: {e}")
        new_value = new_counter.set(counter.value)
        character.consumables.insert(character.consumables.index(counter), new_counter)
        character.consumables.remove(counter)
        await character.commit(ctx)

        overflow = f" ({abs(new_value - counter.value)} overflow)" if counter.value != new_value else ""
        await ctx.send(f"Custom counter edited{overflow}.\n**{new_counter.name}**\n{new_counter.full_str()}")

    @customcounter.command(name="delete", aliases=["remove"])
    async def customcounter_delete(self, ctx, name):
        """Deletes a custom counter."""
        character: Character = await ctx.get_character()
        counter = await character.select_consumable(ctx, name)
        character.consumables.remove(counter)
        await character.commit(ctx)
        await ctx.send(f"Deleted counter {counter.name}.")

    @customcounter.command(name="summary", aliases=["list"])
    async def customcounter_summary(self, ctx, page: int = 1):
        """
        Prints a summary of all custom counters.
        Use `!cc list <page>` to view pages if you have more than 25 counters.
        """
        character: Character = await ctx.get_character()
        embed = EmbedWithCharacter(character, title="Custom Counters")

        if character.consumables:
            # paginate if > 25
            total = len(character.consumables)
            pages = [character.consumables[i : i + 25] for i in range(0, total, 25)]
            maxpage = len(pages)
            page = max(1, min(page, maxpage))
            for counter in pages[page - 1]:
                embed.add_field(name=counter.name, value=counter.full_str())
            if total > 25:
                embed.set_footer(text=f"Page [{page}/{maxpage}] | {ctx.prefix}cc list <page>")
        else:
            embed.add_field(
                name="No Custom Counters",
                value=f"Check out `{ctx.prefix}help cc create` to see how to create new ones.",
            )

        await ctx.send(embed=embed)

    @customcounter.command(name="reset")
    async def customcounter_reset(self, ctx, *args):
        """Resets custom counters, hp, death saves, and spell slots.
        Will reset all if name is not passed, otherwise the specific passed one.
        A counter can only be reset if it has a maximum value.
        Reset hierarchy: short < long < default < none
        __Valid Arguments__
        -h - Hides the character summary output."""
        try:
            name = args[0]
        except IndexError:
            name = None
        else:
            if name == "-h":
                name = None

        if name:
            character: Character = await ctx.get_character()
            counter = await character.select_consumable(ctx, name)
            try:
                result = counter.reset()
                await character.commit(ctx)
            except ConsumableException as e:
                await ctx.send(f"Counter could not be reset: {e}")
            else:
                await ctx.send(f"{counter.name}: {str(counter)} ({result.delta}).")
        else:
            await self._rest(ctx, "all", *args)

    @commands.command(
        pass_context=True,
        help=f"""
        Casts a spell.
        __**Valid Arguments**__
        {VALID_SPELLCASTING_ARGS}
    
        {VALID_AUTOMATION_ARGS}
        """,
    )
    async def cast(self, ctx, spell_name, *, args=""):
        await try_delete(ctx.message)

        char: Character = await ctx.get_character()

        args = await helpers.parse_snippets(args, ctx, character=char, base_args=[spell_name])
        args = argparse(args)

        if not args.last("i", type_=bool):
            try:
                spell = await select_spell_full(ctx, spell_name, list_filter=lambda s: s.name in char.spellbook)
            except NoSelectionElements:
                return await ctx.send(
                    "No matching spells found. Make sure this spell is in your "
                    f"`{ctx.prefix}spellbook`, or cast with the `-i` argument to ignore restrictions!"
                )
        else:
            spell = await select_spell_full(ctx, spell_name)

        caster, targets, combat = await targetutils.maybe_combat(ctx, char, args)
        result = await actionutils.cast_spell(spell, ctx, caster, targets, args, combat=combat)

        embed = result.embed
        embed.colour = char.get_color()
        if "thumb" not in args and char.options.embed_image and char.image:
            embed.set_thumbnail(url=char.image)

        await ctx.send(embed=embed)
        if (gamelog := self.bot.get_cog("GameLog")) and result.automation_result:
            await gamelog.send_automation(ctx, char, spell.name, result.automation_result)


def setup(bot):
    bot.add_cog(GameTrack(bot))
