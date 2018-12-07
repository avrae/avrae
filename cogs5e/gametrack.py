"""
Created on Jul 28, 2017

Most of this module was coded 5 miles in the air. (Aug 8, 2017)

@author: andrew
"""
import logging
import shlex

import MeteorClient
import discord
from discord.ext import commands

from cogs5e.funcs import scripting
from cogs5e.funcs.dice import roll
from cogs5e.funcs.lookupFuncs import c, get_castable_spell, select_spell_full, HOMEBREW_EMOJI
from cogs5e.models.character import Character
from cogs5e.models.dicecloudClient import DicecloudClient
from cogs5e.models.embeds import EmbedWithCharacter, add_fields_from_args
from cogs5e.models.errors import CounterOutOfBounds, InvalidArgument, ConsumableException, ConsumableNotFound
from utils.argparser import argparse
from utils.functions import dicecloud_parse, search_and_select, search

log = logging.getLogger(__name__)


class GameTrack:
    """Commands to help track game resources."""

    def __init__(self, bot):
        self.bot = bot

    @commands.group(pass_context=True, name='game', aliases=['g'])
    async def game(self, ctx):
        """Commands to help track character information in a game. Use `!help game` to view subcommands."""
        if ctx.invoked_subcommand is None:
            await self.bot.say("Incorrect usage. Use !help game for help.")
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass

    @game.command(pass_context=True, name='status', aliases=['summary'])
    async def game_status(self, ctx):
        """Prints the status of the current active character."""
        character = await Character.from_ctx(ctx)
        embed = EmbedWithCharacter(character)
        embed.add_field(name="Hit Points", value=f"{character.get_current_hp()}/{character.get_max_hp()}")
        embed.add_field(name="Spell Slots", value=character.get_remaining_slots_str())
        for name, counter in character.get_all_consumables().items():
            val = self._get_cc_value(character, counter)
            embed.add_field(name=name, value=val)
        await self.bot.say(embed=embed)

    @game.command(pass_context=True, name='spellbook', aliases=['sb'], hidden=True)
    async def game_spellbook(self, ctx):
        """**DEPRECATED** - use `!spellbook` instead."""
        await ctx.invoke(self.bot.get_command('spellbook'))

    @game.command(pass_context=True, name='spellslot', aliases=['ss'])
    async def game_spellslot(self, ctx, level: int = None, value: str = None):
        """Views or sets your remaining spell slots."""
        if level is not None:
            try:
                assert 0 < level < 10
            except AssertionError:
                return await self.bot.say("Invalid spell level.")
        character = await Character.from_ctx(ctx)
        embed = EmbedWithCharacter(character)
        embed.set_footer(text="\u25c9 = Available / \u3007 = Used")
        if level is None and value is None:  # show remaining
            embed.description = f"__**Remaining Spell Slots**__\n{character.get_remaining_slots_str()}"
        elif value is None:
            embed.description = f"__**Remaining Level {level} Spell Slots**__\n{character.get_remaining_slots_str(level)}"
        else:
            try:
                if value.startswith(('+', '-')):
                    value = character.get_remaining_slots(level) + int(value)
                else:
                    value = int(value)
            except ValueError:
                return await self.bot.say(f"{value} is not a valid integer.")
            try:
                assert 0 <= value <= character.get_max_spellslots(level)
            except AssertionError:
                raise CounterOutOfBounds()
            character.set_remaining_slots(level, value)
            await character.commit(ctx)
            embed.description = f"__**Remaining Level {level} Spell Slots**__\n{character.get_remaining_slots_str(level)}"
        await self.bot.say(embed=embed)

    @game.command(pass_context=True, name='longrest', aliases=['lr'])
    async def game_longrest(self, ctx, *args):
        """Performs a long rest, resetting applicable counters.
        __Valid Arguments__
        -h - Hides the character summary output."""
        character = await Character.from_ctx(ctx)
        reset = character.long_rest()
        embed = EmbedWithCharacter(character, name=False)
        embed.title = f"{character.get_name()} took a Long Rest!"
        embed.add_field(name="Reset Values", value=', '.join(set(reset)))
        await character.commit(ctx)
        await self.bot.say(embed=embed)
        if not '-h' in args:
            await ctx.invoke(self.game_status)

    @game.command(pass_context=True, name='shortrest', aliases=['sr'])
    async def game_shortrest(self, ctx, *args):
        """Performs a short rest, resetting applicable counters.
        __Valid Arguments__
        -h - Hides the character summary output."""
        character = await Character.from_ctx(ctx)
        reset = character.short_rest()
        embed = EmbedWithCharacter(character, name=False)
        embed.title = f"{character.get_name()} took a Short Rest!"
        embed.add_field(name="Reset Values", value=', '.join(set(reset)))
        await character.commit(ctx)
        await self.bot.say(embed=embed)
        if not '-h' in args:
            await ctx.invoke(self.game_status)

    @game.command(pass_context=True, name='hp')
    async def game_hp(self, ctx, operator='', *, hp=''):
        """Modifies the HP of a the current active character. Synchronizes live with Dicecloud.
        If operator is not passed, assumes `mod`.
        Operators: `mod`, `set`."""
        character = await Character.from_ctx(ctx)

        if not operator == '':
            hp_roll = roll(hp, inline=True, show_blurbs=False)

            if 'mod' in operator.lower():
                character.modify_hp(hp_roll.total)
            elif 'set' in operator.lower():
                character.set_hp(hp_roll.total, True)
            elif 'max' in operator.lower() and not hp:
                character.set_hp(character.get_max_hp(), True)
            elif hp == '':
                hp_roll = roll(operator, inline=True, show_blurbs=False)
                hp = operator
                character.modify_hp(hp_roll.total)
            else:
                await self.bot.say("Incorrect operator. Use mod or set.")
                return

            await character.commit(ctx)
            out = "{}: {}".format(character.get_name(), character.get_hp_str())
            if 'd' in hp: out += '\n' + hp_roll.skeleton
        else:
            out = "{}: {}".format(character.get_name(), character.get_hp_str())

        await self.bot.say(out)

    @game.command(pass_context=True, name='thp')
    async def game_thp(self, ctx, thp: int = None):
        """Modifies the temp HP of a the current active character.
        If positive, assumes set; if negative, assumes mod."""
        character = await Character.from_ctx(ctx)

        if thp is not None:
            if thp >= 0:
                character.set_temp_hp(thp)
            else:
                character.set_temp_hp(character.get_temp_hp() + thp)

            await character.commit(ctx)

        out = "{}: {}".format(character.get_name(), character.get_hp_str())
        await self.bot.say(out)

    @game.group(pass_context=True, name='deathsave', aliases=['ds'], invoke_without_command=True)
    async def game_deathsave(self, ctx, *args):
        """Commands to manage character death saves.
        __Valid Arguments__
        See `!help save`."""
        character = await Character.from_ctx(ctx)
        args = argparse(args)
        adv = args.adv()
        b = args.join('b', '+')
        phrase = args.join('phrase', '\n')

        if b:
            save_roll = roll('1d20+' + b, adv=adv, inline=True)
        else:
            save_roll = roll('1d20', adv=adv, inline=True)

        embed = discord.Embed()
        embed.title = args.last('title', '') \
                          .replace('[charname]', character.get_name()) \
                          .replace('[sname]', 'Death') \
                      or '{} makes {}!'.format(character.get_name(), "a Death Save")
        embed.colour = character.get_color()

        death_phrase = ''
        if save_roll.crit == 1:
            character.set_hp(1)
            death_phrase = f"{character.get_name()} is UP with 1 HP!"
        elif save_roll.crit == 2:
            if character.add_failed_ds():
                death_phrase = f"{character.get_name()} is DEAD!"
            else:
                if character.add_failed_ds(): death_phrase = f"{character.get_name()} is DEAD!"
        elif save_roll.total >= 10:
            if character.add_successful_ds(): death_phrase = f"{character.get_name()} is STABLE!"
        else:
            if character.add_failed_ds(): death_phrase = f"{character.get_name()} is DEAD!"

        await character.commit(ctx)
        embed.description = save_roll.skeleton + ('\n*' + phrase + '*' if phrase else '')
        if death_phrase: embed.set_footer(text=death_phrase)

        embed.add_field(name="Death Saves", value=character.get_ds_str())

        if args.last('image') is not None:
            embed.set_thumbnail(url=args.last('image'))

        await self.bot.say(embed=embed)

    @game_deathsave.command(pass_context=True, name='success', aliases=['s', 'save'])
    async def game_deathsave_save(self, ctx):
        """Adds a successful death save."""
        character = await Character.from_ctx(ctx)

        embed = EmbedWithCharacter(character)
        embed.title = f'{character.get_name()} succeeds a Death Save!'

        death_phrase = ''
        if character.add_successful_ds(): death_phrase = f"{character.get_name()} is STABLE!"

        await character.commit(ctx)
        embed.description = "Added 1 successful death save."
        if death_phrase: embed.set_footer(text=death_phrase)

        embed.add_field(name="Death Saves", value=character.get_ds_str())

        await self.bot.say(embed=embed)

    @game_deathsave.command(pass_context=True, name='fail', aliases=['f'])
    async def game_deathsave_fail(self, ctx):
        """Adds a failed death save."""
        character = await Character.from_ctx(ctx)

        embed = EmbedWithCharacter(character)
        embed.title = f'{character.get_name()} fails a Death Save!'

        death_phrase = ''
        if character.add_failed_ds(): death_phrase = f"{character.get_name()} is DEAD!"

        await character.commit(ctx)
        embed.description = "Added 1 failed death save."
        if death_phrase: embed.set_footer(text=death_phrase)

        embed.add_field(name="Death Saves", value=character.get_ds_str())

        await self.bot.say(embed=embed)

    @game_deathsave.command(pass_context=True, name='reset')
    async def game_deathsave_reset(self, ctx):
        """Resets all death saves."""
        character = await Character.from_ctx(ctx)
        character.reset_death_saves()
        embed = EmbedWithCharacter(character)
        embed.title = f'{character.get_name()} reset Death Saves!'

        await character.commit(ctx)

        embed.add_field(name="Death Saves", value=character.get_ds_str())

        await self.bot.say(embed=embed)

    @commands.group(pass_context=True, invoke_without_command=True, name='spellbook', aliases=['sb'])
    async def spellbook(self, ctx):
        """Commands to display a character's known spells and metadata."""
        character = await Character.from_ctx(ctx)
        embed = EmbedWithCharacter(character)
        embed.description = f"{character.get_name()} knows {len(character.get_spell_list())} spells."
        embed.add_field(name="DC", value=str(character.get_save_dc()))
        embed.add_field(name="Spell Attack Bonus", value=str(character.get_spell_ab()))
        embed.add_field(name="Spell Slots", value=character.get_remaining_slots_str() or "None")
        spells_known = {}
        for spell_ in character.get_raw_spells():
            if isinstance(spell_, str):
                spell, strict = search(c.spells, spell_, lambda sp: sp.name)
                if spell is None or not strict:
                    continue
                spells_known[str(spell.level)] = spells_known.get(str(spell.level), []) + [spell.name]
            else:
                spellname = spell_['name']
                strict = spell_['strict']
                spell = await get_castable_spell(ctx, spellname)
                if spell is None and strict:
                    continue
                elif spell is None:
                    spells_known['unknown'] = spells_known.get('unknown', []) + [f"*{spellname}*"]
                else:
                    if spell.source == 'homebrew':
                        formatted = f"{spell.name} ({HOMEBREW_EMOJI})"
                    else:
                        formatted = spell.name
                    spells_known[str(spell.level)] = spells_known.get(str(spell.level), []) + [formatted]

        level_name = {'0': 'Cantrips', '1': '1st Level', '2': '2nd Level', '3': '3rd Level',
                      '4': '4th Level', '5': '5th Level', '6': '6th Level',
                      '7': '7th Level', '8': '8th Level', '9': '9th Level'}
        for level, spells in sorted(list(spells_known.items()), key=lambda k: k[0]):
            if spells:
                embed.add_field(name=level_name.get(level, "Unknown"), value=', '.join(spells))
        await self.bot.say(embed=embed)

    @spellbook.command(pass_context=True, name='add')
    async def spellbook_add(self, ctx, *, spell_name):
        """Adds a spell to the spellbook override. If character is live, will add to sheet as well."""
        spell = await select_spell_full(ctx, spell_name)

        character = await Character.from_ctx(ctx)
        if character.live:
            try:
                await DicecloudClient.getInstance().sync_add_spell(character, dicecloud_parse(spell))
            except MeteorClient.MeteorClientException:
                return await self.bot.say("Error: Failed to connect to Dicecloud. The site may be down.")
        character.add_known_spell(spell)
        await character.commit(ctx)
        live = "Spell added to Dicecloud!" if character.live else ''
        await self.bot.say(f"{spell.name} added to known spell list!\n{live}")

    @spellbook.command(pass_context=True, name='addall')
    async def spellbook_addall(self, ctx, _class, level: int, spell_list=None):
        """Adds all spells of a given level from a given class list to the spellbook override. Requires live sheet.
        If `spell_list` is passed, will add these spells to the list named so in Dicecloud."""
        character = await Character.from_ctx(ctx)
        if not character.live:
            return await self.bot.say("This command requires a live Dicecloud sheet. To set up, share your Dicecloud "
                                      "sheet with `avrae` with edit permissions, then `!update`.")
        if not 0 <= level < 10:
            return await self.bot.say("Invalid spell level.")
        class_spells = [sp for sp in c.spells if _class.lower() in [cl.lower() for cl in sp.classes]]
        if len(class_spells) == 0:
            return await self.bot.say("No spells for that class found.")
        level_spells = [s for s in class_spells if level == s.level]
        try:
            await DicecloudClient.getInstance().sync_add_mass_spells(character,
                                                                     [dicecloud_parse(s) for s in level_spells],
                                                                     spell_list)
            await character.commit(ctx)
        except MeteorClient.MeteorClientException:
            return await self.bot.say("Error: Failed to connect to Dicecloud. The site may be down.")
        await self.bot.say(f"{len(level_spells)} spells added to {character.get_name()}'s spell list on Dicecloud.")

    @spellbook.command(pass_context=True, name='remove')
    async def spellbook_remove(self, ctx, *, spell_name):
        """
        Removes a spell from the spellbook override. Must type in full name.
        """
        character = await Character.from_ctx(ctx)
        if character.live:
            return await self.bot.say("Just delete the spell from your character sheet!")
        spell = character.remove_known_spell(spell_name)
        if spell:
            await character.commit(ctx)
            await self.bot.say(f"{spell} removed from spellbook override.")
        else:
            await self.bot.say(
                f"Spell not in spellbook override. Make sure you typed the full spell name. "
                f"To remove a spell on your sheet, just delete it from your sheet.")

    @commands.group(pass_context=True, invoke_without_command=True, name='customcounter', aliases=['cc'])
    async def customcounter(self, ctx, name=None, *, modifier=None):
        """Commands to implement custom counters.
        When called on its own, if modifier is supplied, increases the counter *name* by *modifier*.
        If modifier is not supplied, prints the value and metadata of the counter *name*."""
        if name is None:
            return await ctx.invoke(self.bot.get_command("customcounter list"))
        character = await Character.from_ctx(ctx)
        sel = await character.select_consumable(ctx, name)
        if sel is None:
            return await self.bot.say("Selection timed out or was cancelled.")

        name = sel[0]
        counter = sel[1]

        assert character is not None
        assert counter is not None

        if modifier is None:  # display value
            counterDisplayEmbed = EmbedWithCharacter(character)
            val = self._get_cc_value(character, counter)
            counterDisplayEmbed.add_field(name=name, value=val)
            return await self.bot.say(embed=counterDisplayEmbed)

        operator = None
        if ' ' in modifier:
            m = modifier.split(' ')
            operator = m[0]
            modifier = m[-1]

        try:
            modifier = int(modifier)
        except ValueError:
            return await self.bot.say(f"Could not modify counter: {modifier} is not a number")
        resultEmbed = EmbedWithCharacter(character)
        if not operator or operator == 'mod':
            consValue = int(counter.get('value', 0))
            newValue = consValue + modifier
        elif operator == 'set':
            newValue = modifier
        else:
            return await self.bot.say("Invalid operator. Use mod or set.")
        try:
            character.set_consumable(name, newValue)
            await character.commit(ctx)
            _max = self._get_cc_max(character, counter)
            actualValue = int(character.get_consumable(name).get('value', 0))

            if counter.get('type') == 'bubble':
                assert _max not in ('N/A', None)
                numEmpty = _max - counter.get('value', 0)
                filled = '\u25c9' * counter.get('value', 0)
                empty = '\u3007' * numEmpty
                out = f"{filled}{empty}"
            else:
                out = f"{counter.get('value', 0)}"
            if (not _max in (None, 'N/A')) and not counter.get('type') == 'bubble':
                resultEmbed.description = f"**__{name}__**\n{out}/{_max}"
            else:
                resultEmbed.description = f"**__{name}__**\n{out}"

            if newValue - actualValue:
                resultEmbed.description += f"\n({abs(newValue - actualValue)} overflow)"
        except CounterOutOfBounds:
            resultEmbed.description = f"Could not modify counter: new value out of bounds"
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass
        await self.bot.say(embed=resultEmbed)

    @customcounter.command(pass_context=True, name='create')
    async def customcounter_create(self, ctx, name, *args):
        """Creates a new custom counter.
        __Valid Arguments__
        `-reset <short|long|none>` - Counter will reset to max on a short/long rest, or not ever when "none". Default - will reset on a call of `!cc reset`.
        `-max <max value>` - The maximum value of the counter.
        `-min <min value>` - The minimum value of the counter.
        `-type <bubble|default>` - Whether the counter displays bubbles to show remaining uses or numbers. Default - numbers."""
        character = await Character.from_ctx(ctx)
        args = argparse(args)
        _reset = args.last('reset')
        _max = args.last('max')
        _min = args.last('min')
        _type = args.last('type')
        try:
            character.create_consumable(name, maxValue=_max, minValue=_min, reset=_reset, displayType=_type)
            await character.commit(ctx)
        except InvalidArgument as e:
            return await self.bot.say(f"Failed to create counter: {e}")
        else:
            await self.bot.say(f"Custom counter created.")

    @customcounter.command(pass_context=True, name='delete', aliases=['remove'])
    async def customcounter_delete(self, ctx, name):
        """Deletes a custom counter."""
        character = await Character.from_ctx(ctx)
        try:
            character.delete_consumable(name)
            await character.commit(ctx)
        except ConsumableNotFound:
            return await self.bot.say("Counter not found. Make sure you're using the full name, case-sensitive.")
        await self.bot.say(f"Deleted counter {name}.")

    @customcounter.command(pass_context=True, name='summary', aliases=['list'])
    async def customcounter_summary(self, ctx):
        """Prints a summary of all custom counters."""
        character = await Character.from_ctx(ctx)
        embed = EmbedWithCharacter(character)
        for name, counter in character.get_all_consumables().items():
            val = self._get_cc_value(character, counter)
            embed.add_field(name=name, value=val)
        await self.bot.say(embed=embed)

    @customcounter.command(pass_context=True, name='reset')
    async def customcounter_reset(self, ctx, *args):
        """Resets custom counters, hp, death saves, and spell slots.
        Will reset all if name is not passed, otherwise the specific passed one.
        A counter can only be reset if it has a maximum value.
        Reset hierarchy: short < long < default < none
        __Valid Arguments__
        -h - Hides the character summary output."""
        character = await Character.from_ctx(ctx)
        try:
            name = args[0]
        except IndexError:
            name = None
        else:
            if name == '-h': name = None
        if name:
            try:
                character.reset_consumable(name)
                await character.commit(ctx)
            except ConsumableException as e:
                return await self.bot.say(f"Counter could not be reset: {e}")
            else:
                return await self.bot.say(f"Counter reset to {character.get_consumable(name)['value']}.")
        else:
            reset_consumables = character.reset_all_consumables()
            await character.commit(ctx)
            await self.bot.say(f"Reset counters: {', '.join(set(reset_consumables)) or 'none'}")
        if not '-h' in args:
            await ctx.invoke(self.game_status)

    def _get_cc_value(self, character, counter):
        _min = self._get_cc_min(character, counter)
        _max = self._get_cc_max(character, counter)
        _reset = self._get_cc_reset(character, counter)

        if counter.get('type') == 'bubble':
            assert _max not in ('N/A', None)
            numEmpty = _max - counter.get('value', 0)
            filled = '\u25c9' * counter.get('value', 0)
            empty = '\u3007' * numEmpty
            val = f"{filled}{empty}\n"
        else:
            val = f"**Current Value**: {counter.get('value', 0)}\n"
            if _min is not None and _max is not None:
                val += f"**Range**: {_min} - {_max}\n"
        if _reset:
            val += f"**Resets When**: {_reset}\n"
        return val

    def _get_cc_max(self, character, counter):
        _max = None
        if any(r in counter for r in ('max', 'min')):
            _max = counter.get('max')
            if _max is not None:
                _max = character.evaluate_cvar(_max)
            else:
                _max = "N/A"
        return _max

    def _get_cc_min(self, character, counter):
        _min = None
        if any(r in counter for r in ('max', 'min')):
            _min = counter.get('min')
            if _min is not None:
                _min = character.evaluate_cvar(_min)
            else:
                _min = "N/A"
        return _min

    def _get_cc_reset(self, character, counter):
        _reset = None
        if any(r in counter for r in ('max', 'min')):
            if not counter.get('reset') == 'none':
                _resetMap = {'short': "Short Rest completed (`!game shortrest`)",
                             'long': "Long Rest completed (`!game longrest`)",
                             'reset': "`!cc reset` is called",
                             'hp': "Character has >0 HP",
                             None: "Unknown Reset"}
                _reset = _resetMap.get(counter.get('reset', 'reset'), _resetMap[None])
        return _reset

    @commands.command(pass_context=True)
    async def cast(self, ctx, spell_name, *, args=''):
        """Casts a spell.
        __Valid Arguments:__
        -i - Ignores Spellbook restrictions, for demonstrations or rituals.
        -l [level] - Specifies the level to cast the spell at.
        **__Save Spells__**
        -dc [Save DC] - Default: Pulls a cvar called `dc`.
        -save [Save type] - Default: The spell's default save.
        -d [damage] - adds additional damage.
        **__Attack Spells__**
        See `!a`.
        **__All Spells__**
        -phrase [phrase] - adds flavor text."""
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass

        char = await Character.from_ctx(ctx)

        if not '-i' in args:
            spell = await select_spell_full(ctx, spell_name, list_filter=lambda s: s.name in char.get_spell_list())
        else:
            spell = await select_spell_full(ctx, spell_name)

        args = await scripting.parse_snippets(args, ctx)
        args = await char.parse_cvars(args, ctx)
        args = shlex.split(args)
        args = argparse(args)

        result = await spell.cast(ctx, char, None, args)
        embed = result['embed']

        embed.colour = char.get_color()
        embed.set_thumbnail(url=char.get_image())

        add_fields_from_args(embed, args.get('f'))

        await char.commit(ctx)  # make sure we save changes
        await self.bot.say(embed=embed)


def setup(bot):
    bot.add_cog(GameTrack(bot))
