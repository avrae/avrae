"""
Created on Jul 28, 2017

Most of this module was coded 5 miles in the air. (Aug 8, 2017)

@author: andrew
"""
import collections
import logging

import d20
import discord
from discord.ext import commands

from aliasing import helpers
from cogs5e.funcs import targetutils
from cogs5e.models.character import Character, CustomCounter
from cogs5e.models.embeds import EmbedWithCharacter
from cogs5e.models.errors import ConsumableException, CounterOutOfBounds, InvalidArgument, NoSelectionElements
from gamedata.lookuputils import get_spell_choices, select_spell_full
from utils.argparser import argparse
from utils.dice import d20_with_adv
from utils.functions import confirm, search, search_and_select, try_delete

log = logging.getLogger(__name__)


class GameTrack(commands.Cog):
    """Commands to help track game resources."""

    def __init__(self, bot):
        self.bot = bot

    @commands.group(name='game', aliases=['g'])
    async def game(self, ctx):
        """Commands to help track character information in a game. Use `!help game` to view subcommands."""
        if ctx.invoked_subcommand is None:
            await ctx.send(f"Incorrect usage. Use {ctx.prefix}help game for help.")
        await try_delete(ctx.message)

    @game.command(name='status', aliases=['summary'])
    async def game_status(self, ctx):
        """Prints the status of the current active character."""
        character: Character = await Character.from_ctx(ctx)
        embed = EmbedWithCharacter(character)
        embed.add_field(name="Hit Points", value=character.hp_str())
        embed.add_field(name="Spell Slots", value=character.spellbook.slots_str())
        if character.death_saves.successes != 0 or character.death_saves.fails != 0:
            embed.add_field(name="Death Saves", value=str(character.death_saves))
        for counter in character.consumables:
            embed.add_field(name=counter.name, value=counter.full_str())
        await ctx.send(embed=embed)

    @game.command(name='spellbook', aliases=['sb'], hidden=True)
    async def game_spellbook(self, ctx):
        """**DEPRECATED** - use `!spellbook` instead."""
        await self.spellbook(ctx)

    @game.command(name='spellslot', aliases=['ss'])
    async def game_spellslot(self, ctx, level: int = None, value: str = None):
        """Views or sets your remaining spell slots."""
        if level is not None:
            try:
                assert 0 < level < 10
            except AssertionError:
                return await ctx.send("Invalid spell level.")
        character: Character = await Character.from_ctx(ctx)
        embed = EmbedWithCharacter(character)
        embed.set_footer(text="\u25c9 = Available / \u3007 = Used")
        if level is None and value is None:  # show remaining
            embed.description = f"__**Remaining Spell Slots**__\n{character.spellbook.slots_str()}"
        elif value is None:
            embed.description = f"__**Remaining Level {level} Spell Slots**__\n" \
                                f"{character.spellbook.slots_str(level)}"
        else:
            try:
                if value.startswith(('+', '-')):
                    value = character.spellbook.get_slots(level) + int(value)
                else:
                    value = int(value)
            except ValueError:
                return await ctx.send(f"{value} is not a valid integer.")
            try:
                assert 0 <= value <= character.spellbook.get_max_slots(level)
            except AssertionError:
                raise CounterOutOfBounds()
            character.spellbook.set_slots(level, value)
            await character.commit(ctx)
            embed.description = f"__**Remaining Level {level} Spell Slots**__\n" \
                                f"{character.spellbook.slots_str(level)}"
        await ctx.send(embed=embed)

    async def _rest(self, ctx, rest_type, *args):
        """
        Runs a rest.

        :param ctx: The Context.
        :param character: The Character.
        :param rest_type: "long", "short", "all"
        :param args: a list of args.
        """
        character: Character = await Character.from_ctx(ctx)
        old_hp = character.hp
        old_slots = {lvl: character.spellbook.get_slots(lvl) for lvl in range(1, 10)}

        embed = EmbedWithCharacter(character, name=False)
        if rest_type == 'long':
            reset = character.long_rest()
            embed.title = f"{character.name} took a Long Rest!"
        elif rest_type == 'short':
            reset = character.short_rest()
            embed.title = f"{character.name} took a Short Rest!"
        elif rest_type == 'all':
            reset = character.reset_all_consumables()
            embed.title = f"{character.name} reset all counters!"
        else:
            raise ValueError(f"Invalid rest type: {rest_type}")

        if '-h' in args:
            values = ', '.join(set(ctr.name for ctr, _ in reset) | {"Hit Points", "Death Saves", "Spell Slots"})
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
                embed.add_field(name="Spell Slots", value='\n'.join(slots_out))

            # ccs
            displayed_counters = set()
            counters_out = []
            for counter, delta in reset:
                if counter.name in displayed_counters:
                    continue
                displayed_counters.add(counter.name)
                if delta:
                    counters_out.append(f"{counter.name}: {str(counter)} ({delta:+})")
                else:
                    counters_out.append(f"{counter.name}: {str(counter)}")
            if counters_out:
                embed.add_field(name="Reset Counters", value='\n'.join(counters_out))

        await character.commit(ctx)
        await ctx.send(embed=embed)

    @game.command(name='longrest', aliases=['lr'])
    async def game_longrest(self, ctx, *args):
        """Performs a long rest, resetting applicable counters.
        __Valid Arguments__
        -h - Hides the character summary output."""
        await self._rest(ctx, 'long', *args)

    @game.command(name='shortrest', aliases=['sr'])
    async def game_shortrest(self, ctx, *args):
        """Performs a short rest, resetting applicable counters.
        __Valid Arguments__
        -h - Hides the character summary output."""
        await self._rest(ctx, 'short', *args)

    @game.group(name='hp', invoke_without_command=True)
    async def game_hp(self, ctx, *, hp: str = None):
        """Modifies the HP of a the current active character."""
        character: Character = await Character.from_ctx(ctx)

        if hp is None:
            return await ctx.send(f"{character.name}: {character.hp_str()}")

        hp_roll = d20.roll(hp)
        character.modify_hp(hp_roll.total)
        await character.commit(ctx)
        if 'd' in hp:
            delta = hp_roll.result
        else:
            delta = f"{hp_roll.total:+}"
        await ctx.send(f"{character.name}: {character.hp_str()} ({delta})")

    @game_hp.command(name='max')
    async def game_hp_max(self, ctx):
        """Sets the character's HP to their maximum."""
        character: Character = await Character.from_ctx(ctx)
        before = character.hp
        character.hp = character.max_hp
        await character.commit(ctx)
        await ctx.send(f"{character.name}: {character.hp_str()} ({character.hp - before:+})")

    @game_hp.command(name='mod', hidden=True)
    async def game_hp_mod(self, ctx, *, hp):
        """Modifies the character's current HP."""
        await ctx.invoke(self.game_hp, hp=hp)

    @game_hp.command(name='set')
    async def game_hp_set(self, ctx, *, hp):
        """Sets the character's HP to a certain value."""
        character: Character = await Character.from_ctx(ctx)
        before = character.hp
        hp_roll = d20.roll(hp)
        character.hp = hp_roll.total
        await character.commit(ctx)
        await ctx.send(f"{character.name}: {character.hp_str()} ({character.hp - before:+})")

    @game.command(name='thp')
    async def game_thp(self, ctx, *, thp: str = None):
        """Modifies the temp HP of a the current active character.
        If positive, assumes set; if negative, assumes mod."""
        character: Character = await Character.from_ctx(ctx)

        if thp is not None:
            thp_roll = d20.roll(thp)
            value = thp_roll.total

            if value >= 0:
                character.temp_hp = value
            else:
                character.temp_hp += value

            await character.commit(ctx)

            delta = ""
            if 'd' in thp:
                delta = f"({thp_roll.result})"
            out = f"{character.name}: {character.hp_str()} {delta}"
        else:
            out = f"{character.name}: {character.hp_str()}"
        await ctx.send(out)

    @game.group(name='deathsave', aliases=['ds'], invoke_without_command=True)
    async def game_deathsave(self, ctx, *args):
        """Commands to manage character death saves.
        __Valid Arguments__
        See `!help save`."""
        character: Character = await Character.from_ctx(ctx)
        args = argparse(args)
        adv = args.adv()
        b = args.join('b', '+')
        phrase = args.join('phrase', '\n')

        if b:
            save_roll = d20.roll(f"{d20_with_adv(adv)}+{b}")
        else:
            save_roll = d20.roll(d20_with_adv(adv))

        embed = discord.Embed()
        embed.title = args.last('title', '') \
                          .replace('[name]', character.name) \
                          .replace('[sname]', 'Death') \
                      or f'{character.name} makes a Death Save!'
        embed.colour = character.get_color()

        death_phrase = ''
        if save_roll.crit == d20.CritType.CRIT:
            character.hp = 1
        elif save_roll.crit == d20.CritType.FAIL:
            character.death_saves.fail(2)
        elif save_roll.total >= 10:
            character.death_saves.succeed()
        else:
            character.death_saves.fail()

        if save_roll.crit == d20.CritType.CRIT:
            death_phrase = f"{character.name} is UP with 1 HP!"
        elif character.death_saves.is_dead():
            death_phrase = f"{character.name} is DEAD!"
        elif character.death_saves.is_stable():
            death_phrase = f"{character.name} is STABLE!"

        await character.commit(ctx)
        embed.description = save_roll.result + (f'\n*{phrase}*' if phrase else '')
        if death_phrase:
            embed.set_footer(text=death_phrase)

        embed.add_field(name="Death Saves", value=str(character.death_saves))

        if args.last('image') is not None:
            embed.set_thumbnail(url=args.last('image'))

        await ctx.send(embed=embed)

    @game_deathsave.command(name='success', aliases=['s', 'save'])
    async def game_deathsave_save(self, ctx):
        """Adds a successful death save."""
        character: Character = await Character.from_ctx(ctx)

        embed = EmbedWithCharacter(character)
        embed.title = f'{character.name} succeeds a Death Save!'

        character.death_saves.succeed()
        await character.commit(ctx)

        if character.death_saves.is_stable():
            embed.set_footer(text=f"{character.name} is STABLE!")
        embed.description = "Added 1 successful death save."
        embed.add_field(name="Death Saves", value=str(character.death_saves))

        await ctx.send(embed=embed)

    @game_deathsave.command(name='fail', aliases=['f'])
    async def game_deathsave_fail(self, ctx):
        """Adds a failed death save."""
        character: Character = await Character.from_ctx(ctx)

        embed = EmbedWithCharacter(character)
        embed.title = f'{character.name} fails a Death Save!'

        character.death_saves.fail()
        await character.commit(ctx)

        if character.death_saves.is_dead():
            embed.set_footer(text=f"{character.name} is DEAD!")
        embed.description = "Added 1 failed death save."
        embed.add_field(name="Death Saves", value=str(character.death_saves))

        await ctx.send(embed=embed)

    @game_deathsave.command(name='reset')
    async def game_deathsave_reset(self, ctx):
        """Resets all death saves."""
        character: Character = await Character.from_ctx(ctx)
        character.death_saves.reset()
        await character.commit(ctx)

        embed = EmbedWithCharacter(character)
        embed.title = f'{character.name} reset Death Saves!'
        embed.add_field(name="Death Saves", value=str(character.death_saves))

        await ctx.send(embed=embed)

    @commands.group(invoke_without_command=True, name='spellbook', aliases=['sb'])
    async def spellbook(self, ctx):
        """Commands to display a character's known spells and metadata."""
        await ctx.trigger_typing()

        character: Character = await Character.from_ctx(ctx)
        embed = EmbedWithCharacter(character)
        embed.description = f"{character.name} knows {len(character.spellbook.spells)} spells."
        embed.add_field(name="DC", value=str(character.spellbook.dc))
        embed.add_field(name="Spell Attack Bonus", value=str(character.spellbook.sab))
        embed.add_field(name="Spell Slots", value=character.spellbook.slots_str() or "None")

        # dynamic help flags
        flag_show_multiple_source_help = False
        flag_show_homebrew_help = False

        spells_known = collections.defaultdict(lambda: [])
        choices = await get_spell_choices(ctx)
        for spell_ in character.spellbook.spells:
            results, strict = search(choices, spell_.name, lambda sp: sp.name, strict=True)
            if not strict:
                if len(results) > 1:
                    spells_known['unknown'].append(f"*{spell_.name} ({'*' * len(results)})*")
                    flag_show_multiple_source_help = True
                else:
                    spells_known['unknown'].append(f"*{spell_.name}*")
                flag_show_homebrew_help = True
            else:
                spell = results
                if spell.homebrew:
                    formatted = f"*{spell.name}*"
                    flag_show_homebrew_help = True
                else:
                    formatted = spell.name
                spells_known[str(spell.level)].append(formatted)

        level_name = {'0': 'Cantrips', '1': '1st Level', '2': '2nd Level', '3': '3rd Level',
                      '4': '4th Level', '5': '5th Level', '6': '6th Level',
                      '7': '7th Level', '8': '8th Level', '9': '9th Level'}
        for level, spells in sorted(list(spells_known.items()), key=lambda k: k[0]):
            if spells:
                spells.sort()
                embed.add_field(name=level_name.get(level, "Unknown"), value=', '.join(spells), inline=False)

        # dynamic help
        footer_out = []
        if flag_show_homebrew_help:
            footer_out.append("An italicized spell indicates that the spell is homebrew.")
        if flag_show_multiple_source_help:
            footer_out.append("Asterisks after a spell indicates that the spell is being provided by multiple sources.")

        if footer_out:
            embed.set_footer(text=' '.join(footer_out))

        await ctx.send(embed=embed)

    @spellbook.command(name='add')
    async def spellbook_add(self, ctx, spell_name, *args):
        """
        Adds a spell to the spellbook override.

        __Valid Arguments__
        *Note: These arguments do not support calculations.*
        -dc <dc> - When cast, this spell always uses this DC.
        -b <sab> - When cast, this spell always uses this spell attack bonus.
        -mod <mod> - When cast, this spell always uses this as the value of its casting stat (usually for healing spells).
        """
        spell = await select_spell_full(ctx, spell_name)
        character: Character = await Character.from_ctx(ctx)
        args = argparse(args)

        dc = args.last('dc', type_=int)
        sab = args.last('b', type_=int)
        mod = args.last('mod', type_=int)
        character.add_known_spell(spell, dc, sab, mod)
        await character.commit(ctx)
        await ctx.send(f"{spell.name} added to known spell list!")

    @spellbook.command(name='remove')
    async def spellbook_remove(self, ctx, *, spell_name):
        """
        Removes a spell from the spellbook override.
        """
        character: Character = await Character.from_ctx(ctx)

        spell_to_remove = await search_and_select(ctx, character.overrides.spells, spell_name, lambda s: s.name,
                                                  message="To remove a spell on your sheet, just delete it there and `!update`.")
        character.remove_known_spell(spell_to_remove)

        await character.commit(ctx)
        await ctx.send(f"{spell_to_remove.name} removed from spellbook override.")

    @commands.group(invoke_without_command=True, name='customcounter', aliases=['cc'])
    async def customcounter(self, ctx, name=None, *, modifier=None):
        """Commands to implement custom counters.
        When called on its own, if modifier is supplied, increases the counter *name* by *modifier*.
        If modifier is not supplied, prints the value and metadata of the counter *name*."""
        if name is None:
            return await self.customcounter_summary(ctx)
        character: Character = await Character.from_ctx(ctx)
        counter = await character.select_consumable(ctx, name)

        if modifier is None:  # display value
            counter_display_embed = EmbedWithCharacter(character)
            counter_display_embed.add_field(name=counter.name, value=counter.full_str())
            return await ctx.send(embed=counter_display_embed)

        operator = None
        if ' ' in modifier:
            m = modifier.split(' ')
            operator = m[0]
            modifier = m[-1]

        change = ''
        old_value = counter.value
        try:
            modifier = int(modifier)
        except ValueError:
            return await ctx.send(f"Could not modify counter: {modifier} is not a number")
        result_embed = EmbedWithCharacter(character)
        if not operator or operator == 'mod':
            new_value = counter.value + modifier
        elif operator == 'set':
            new_value = modifier
        else:
            return await ctx.send("Invalid operator. Use mod or set.")

        counter.set(new_value)
        await character.commit(ctx)

        delta = f"({counter.value - old_value:+})"
        if new_value - counter.value:  # we overflowed somewhere
          out = f"{str(counter)} {delta}\n({abs(new_value - counter.value)} overflow)"
        else:
          out = f"{str(counter)} {delta}"

        result_embed.add_field(name=counter.name, value=out)

        await try_delete(ctx.message)
        await ctx.send(embed=result_embed)

    @customcounter.command(name='create')
    async def customcounter_create(self, ctx, name, *args):
        """Creates a new custom counter.
        __Valid Arguments__
        `-reset <short|long|none>` - Counter will reset to max on a short/long rest, or not ever when "none". Default - will reset on a call of `!cc reset`.
        `-max <max value>` - The maximum value of the counter.
        `-min <min value>` - The minimum value of the counter.
        `-type <bubble|default>` - Whether the counter displays bubbles to show remaining uses or numbers. Default - numbers."""
        character: Character = await Character.from_ctx(ctx)

        conflict = next((c for c in character.consumables if c.name.lower() == name.lower()), None)
        if conflict:
            if await confirm(ctx, "Warning: This will overwrite an existing consumable. Continue?"):
                character.consumables.remove(conflict)
            else:
                return await ctx.send("Overwrite unconfirmed. Aborting.")

        args = argparse(args)
        _reset = args.last('reset')
        _max = args.last('max')
        _min = args.last('min')
        _type = args.last('type')
        try:
            new_counter = CustomCounter.new(character, name, maxv=_max, minv=_min, reset=_reset, display_type=_type)
            character.consumables.append(new_counter)
            await character.commit(ctx)
        except InvalidArgument as e:
            return await ctx.send(f"Failed to create counter: {e}")
        else:
            await ctx.send(f"Custom counter created.")

    @customcounter.command(name='delete', aliases=['remove'])
    async def customcounter_delete(self, ctx, name):
        """Deletes a custom counter."""
        character: Character = await Character.from_ctx(ctx)
        counter = await character.select_consumable(ctx, name)
        character.consumables.remove(counter)
        await character.commit(ctx)
        await ctx.send(f"Deleted counter {counter.name}.")

    @customcounter.command(name='summary', aliases=['list'])
    async def customcounter_summary(self, ctx):
        """Prints a summary of all custom counters."""
        character: Character = await Character.from_ctx(ctx)
        embed = EmbedWithCharacter(character)
        for counter in character.consumables:
            embed.add_field(name=counter.name, value=counter.full_str())
        await ctx.send(embed=embed)

    @customcounter.command(name='reset')
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
            if name == '-h':
                name = None

        if name:
            character: Character = await Character.from_ctx(ctx)
            counter = await character.select_consumable(ctx, name)
            before = counter.value
            try:
                counter.reset()
                await character.commit(ctx)
            except ConsumableException as e:
                await ctx.send(f"Counter could not be reset: {e}")
            else:
                delta = counter.value - before
                await ctx.send(f"{counter.name}: {str(counter)} ({delta:+}).")
        else:
            await self._rest(ctx, 'all', *args)

    @commands.command(pass_context=True)
    async def cast(self, ctx, spell_name, *, args=''):
        """Casts a spell.
        __Valid Arguments__
        -i - Ignores Spellbook restrictions, for demonstrations or rituals.
        -l <level> - Specifies the level to cast the spell at.
        noconc - Ignores concentration requirements.
        -h - Hides rolled values.
        **__Save Spells__**
        -dc <Save DC> - Overrides the spell save DC.
        -dc <+X/-X> - Modifies the DC by a certain amount.
        -save <Save type> - Overrides the spell save type.
        -d <damage> - Adds additional damage.
        pass - Target automatically succeeds save.
        fail - Target automatically fails save.
        adv/dis - Target makes save at advantage/disadvantage.
        **__Attack Spells__**
        See `!a`.
        **__All Spells__**
        -phrase <phrase> - adds flavor text.
        -title <title> - changes the title of the cast. Replaces [sname] with spell name.
        -thumb <url> - adds an image to the cast.
        -dur <duration> - changes the duration of any effect applied by the spell.
        -mod <spellcasting mod> - sets the value of the spellcasting ability modifier.
        int/wis/cha - different skill base for DC/AB (will not account for extra bonuses)
        """
        await try_delete(ctx.message)

        char: Character = await Character.from_ctx(ctx)

        args = await helpers.parse_snippets(args, ctx)
        args = await helpers.parse_with_character(ctx, char, args)
        args = argparse(args)

        if not args.last('i', type_=bool):
            try:
                spell = await select_spell_full(ctx, spell_name, list_filter=lambda s: s.name in char.spellbook)
            except NoSelectionElements:
                return await ctx.send(
                    f"No matching spells found. Make sure this spell is in your "
                    f"`{ctx.prefix}spellbook`, or cast with the `-i` argument to ignore restrictions!")
        else:
            spell = await select_spell_full(ctx, spell_name)

        caster, targets, combat = await targetutils.maybe_combat(ctx, char, args)
        result = await spell.cast(ctx, caster, targets, args, combat=combat)

        embed = result['embed']
        embed.colour = char.get_color()
        if 'thumb' not in args:
            embed.set_thumbnail(url=char.image)

        # save changes: combat state, spell slot usage
        await char.commit(ctx)
        if combat:
            await combat.final()
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(GameTrack(bot))
