'''
Created on Jul 28, 2017

Most of this module was coded 5 miles in the air. (Aug 8, 2017)

@author: andrew
'''
import copy
import json
import logging
import random
import re
import shlex

import discord
from discord.ext import commands

from cogs5e.funcs.dice import roll
from cogs5e.funcs.lookupFuncs import getSpell, searchSpellNameFull
from cogs5e.funcs.sheetFuncs import sheet_attack
from cogs5e.models.character import Character
from cogs5e.models.embeds import EmbedWithCharacter
from cogs5e.models.errors import CounterOutOfBounds, InvalidArgument, ConsumableException, AvraeException
from utils.functions import parse_cvars, parse_args_3, \
    evaluate_cvar, strict_search

log = logging.getLogger(__name__)


class GameTrack:
    """Commands to help track game resources."""

    def __init__(self, bot):
        self.bot = bot
        with open('./res/auto_spells.json', 'r') as f:
            self.autospells = json.load(f)

    async def on_command_error(self, error, ctx):
        if isinstance(error, AvraeException):
            await self.bot.send_message(ctx.message.channel, f"{type(error)}: {str(error)}")
        else: raise error # not my problem

    @commands.group(pass_context=True, invoke_without_command=True, name='cc')
    async def customcounter(self, ctx, name, modifier=None):
        """Commands to implement custom counters.
        When called on its own, if modifier is supplied, increases the counter *name* by *modifier*.
        If modifier is not supplied, prints the value and metadata of the counter *name*."""
        character = Character(ctx)
        counter = character.get_consumable(name)

        assert character is not None
        assert counter is not None

        if modifier is None:  # display value
            counterDisplayEmbed = EmbedWithCharacter(character)
            counterDisplayEmbed.title = name
            counterDisplayEmbed.description = f"**Current Value**: {counter.get('value', 0)}"
            if any(r in counter for r in ('max', 'min')):
                _min = counter.get('min', 'N/A')
                _max = counter.get('max', 'N/A')
                counterDisplayEmbed.add_field(name="Range",
                                              value=f"{_min} - {_max}")

                _resetMap = {'short': "Short Rest completed (`!shortrest`)",  # TODO
                             'long': "Long Rest completed (`!longrest`)", # TODO
                             'reset': "`!cc reset` is called",
                             'hp': "Character has >0 HP", # TODO
                             'none': "Does not reset",
                             None: "Unknown Reset"}

                _reset = _resetMap.get(counter.get('reset', 'reset'), _resetMap[None])
                counterDisplayEmbed.add_field(name="Resets When",
                                              value=_reset)

            return await self.bot.say(embed=counterDisplayEmbed)

        try:
            modifier = int(modifier)
        except ValueError:
            return await self.bot.say(f"Could not modify counter: {modifier} is not a number")
        resultEmbed = EmbedWithCharacter(character)
        consValue = counter.get('value', 0)
        newValue = consValue + modifier
        try:
            character.set_consumable(name, newValue).commit(ctx) #  I really love this
            resultEmbed.description = f"Modified counter: new value = {newValue}"
        except CounterOutOfBounds:
            resultEmbed.description = f"Could not modify counter: new value out of bounds"
        await self.bot.say(embed=resultEmbed)

    @customcounter.command(pass_context=True, name='create')
    async def customcounter_create(self, ctx, name, *args):
        """Creates a new custom counter.
        __Valid Arguments__
        `-reset <short|long|none>` - Counter will reset to max on a short/long rest, or not ever when "none". Default - will reset on a call of `!cc reset`.
        `-max <max value>` - The maximum value of the counter.
        `-min <min value>` - The minimum value of the counter."""
        character = Character(ctx)
        args = parse_args_3(args)
        _reset = args.get('reset', [None])[-1]
        _max = args.get('max', [None])[-1]
        _min = args.get('min', [None])[-1]
        _max = evaluate_cvar(_max, character) if _max else None
        _min = evaluate_cvar(_min, character) if _min else None
        try:
            character.create_consumable(name, maxValue=_max, minValue=_min, reset=_reset).commit(ctx)
        except InvalidArgument as e:
            return await self.bot.say(f"Failed to create counter: {e}")
        else:
            await self.bot.say(f"Custom counter created.")

    @customcounter.command(pass_context=True, name='delete')
    async def customcounter_delete(self, ctx, name):
        """Deletes a custom counter."""
        character = Character(ctx)
        character.delete_consumable(name).commit(ctx)
        await self.bot.say(f"Deleted counter {name}.")

    @customcounter.command(pass_context=True, name='summary', aliases=['list'])
    async def customcounter_summary(self, ctx):
        """Prints a summary of all custom counters."""
        character = Character(ctx)
        embed = EmbedWithCharacter(character)
        for name, counter in character.get_all_consumables().items():
            val = f"**Current Value**: {counter.get('value', 0)}\n"
            if any(r in counter for r in ('max', 'min')):
                _min = counter.get('min', 'N/A')
                _max = counter.get('max', 'N/A')
                val += f"**Range**: {_min} - {_max}"
                if not counter.get('reset') == 'none':
                    _resetMap = {'short': "Short Rest completed (`!shortrest`)",
                                 'long': "Long Rest completed (`!longrest`)",
                                 'reset': "`!cc reset` is called",
                                 'hp': "Character has >0 HP",
                                 None: "Unknown Reset"}
                    _reset = _resetMap.get(counter.get('reset', 'reset'), _resetMap[None])
                    val += f"**Resets When**: {_resetMap.get(_reset)}\n"
            embed.add_field(name=name, value=val)
        await self.bot.say(embed=embed)

    @customcounter.command(pass_context=True, name='reset')
    async def customcounter_reset(self, ctx, name=None):
        """Resets custom counters.
        Will reset all if name is not passed, otherwise the specific passed one.
        A counter can only be reset if it has a maximum value.
        Reset hierarchy: short < long < default < none"""
        character = Character(ctx)
        if name:
            try:
                character.reset_consumable(name).commit(ctx)
            except ConsumableException as e:
                return await self.bot.say(f"Counter could not be reset: {e}")
            else:
                return await self.bot.say(f"Counter reset to {character.get_consumable(name)['value']}.")
        else:
            reset_consumables = character.reset_all_consumables()
            character.commit(ctx)
            await self.bot.say(f"Reset counters: {', '.join(reset_consumables) or 'none'}")


    @commands.command(pass_context=True)
    async def cast(self, ctx, spell_name, *args):
        """Casts a spell.
        Valid Arguments:
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

        spell_name = await searchSpellNameFull(spell_name, ctx)

        if spell_name is None: return

        spell = strict_search(self.autospells, 'name', spell_name)
        if spell is None: return await self._old_cast(ctx, spell_name + " " + " ".join(args),
                                                      fallback=True)  # fall back to old cast

        user_characters = self.bot.db.not_json_get(ctx.message.author.id + '.characters', {})  # grab user's characters
        active_character = self.bot.db.not_json_get('active_characters', {}).get(
            ctx.message.author.id)  # get user's active
        if active_character is None:
            return await self.bot.say('You have no character active.')
        character = user_characters[active_character]  # get Sheet of character

        tempargs = list(args)
        user_snippets = self.bot.db.not_json_get('damage_snippets', {}).get(ctx.message.author.id, {})
        for index, arg in enumerate(tempargs):  # parse snippets
            snippet_value = user_snippets.get(arg)
            if snippet_value:
                tempargs[index] = snippet_value
            elif ' ' in arg:
                tempargs[index] = shlex.quote(arg)

        args = " ".join(tempargs)
        args = parse_cvars(args, character)
        args = shlex.split(args)
        args = parse_args_3(args)

        embed = discord.Embed()
        if args.get('phrase') is not None:  # parse phrase
            embed.description = '*' + '\n'.join(args.get('phrase')) + '*'
        else:
            embed.description = '~~' + ' ' * 500 + '~~'

        if args.get('title') is not None:
            embed.title = args.get('title')[-1].replace('[charname]', args.get('name')).replace('[sname]',
                                                                                                spell['name']).replace(
                '[target]', args.get('t', ''))
        else:
            embed.title = '{} casts {}!'.format(character.get('stats', {}).get('name', "NONAME"), spell['name'])

        spell_type = spell.get('type')
        if spell_type == 'save':  # save spell
            calculated_dc = evaluate_cvar(character.get('cvars', {}).get('dc', ''), character) or None
            dc = args.get('dc', [None])[-1] or calculated_dc
            if dc is None:
                return await self.bot.say(embed=discord.Embed(title="Error: Save DC not set.",
                                                              description="Your spell save DC is not set. You can set it for this character by running `!cvar dc [DC]`, where `[DC]` is your spell save DC, or by passing in `-dc [DC]`."))
            try:
                dc = int(dc)
            except:
                return await self.bot.say(embed=discord.Embed(title="Error: Save DC malformed.",
                                                              description="Your spell save DC is malformed. You can reset it for this character by running `!cvar dc [DC]`, where `[DC]` is your spell save DC, or by passing in `-dc [DC]`."))

            save_skill = args.get('save', [None])[-1] or spell.get('save', {}).get('save')
            try:
                save_skill = next(s for s in ('strengthSave',
                                              'dexteritySave',
                                              'constitutionSave',
                                              'intelligenceSave',
                                              'wisdomSave',
                                              'charismaSave') if save_skill.lower() in s.lower())
            except StopIteration:
                return await self.bot.say(embed=discord.Embed(title="Invalid save!",
                                                              description="{} is not a valid save.".format(save_skill)))
            save = spell['save']

            if save['damage'] is None:  # save against effect
                embed.add_field(name="DC", value=str(dc) + "\n{} Save".format(spell['save']['save']))
            else:  # damage spell
                dmg = save['damage']

                if spell['level'] == '0' and spell.get('scales', True):
                    def lsub(matchobj):
                        level = character.get('levels', {}).get('level', 0)
                        if level < 5:
                            levelDice = "1"
                        elif level < 11:
                            levelDice = "2"
                        elif level < 17:
                            levelDice = "3"
                        else:
                            levelDice = "4"
                        return levelDice + 'd' + matchobj.group(2)

                    dmg = re.sub(r'(\d+)d(\d+)', lsub, dmg)

                if args.get('d') is not None:
                    dmg = dmg + '+' + "+".join(args.get('d', []))

                dmgroll = roll(dmg, rollFor="Damage", inline=True, show_blurbs=False)
                embed.add_field(name="Damage/DC",
                                value=dmgroll.result + "\n**DC**: {}\n{} Save".format(str(dc), spell['save']['save']))
        elif spell['type'] == 'attack':  # attack spell
            outargs = copy.copy(args)
            outargs['d'] = "+".join(args.get('d', [])) or None
            for _arg, _value in outargs.items():
                if isinstance(_value, list):
                    outargs[_arg] = _value[-1]
            attack = copy.copy(spell['atk'])
            if not 'SPELL' in character.get('cvars', {}):
                return await self.bot.say(embed=discord.Embed(title="Error: Casting ability not set.",
                                                              description="Your casting ability is not set. You can set it for this character by running `!cvar SPELL [ABILITY]`, where `[ABILITY]` is your spellcasting modifier.\nFor example, a sorcerer (CHA caster) with 20 CHA would use `!cvar SPELL 5.`"))
            attack['attackBonus'] = str(evaluate_cvar(attack['attackBonus'], character))

            if spell['level'] == '0' and spell.get('scales', True):
                def lsub(matchobj):
                    level = character.get('levels', {}).get('level', 0)
                    if level < 5:
                        levelDice = "1"
                    elif level < 11:
                        levelDice = "2"
                    elif level < 17:
                        levelDice = "3"
                    else:
                        levelDice = "4"
                    return levelDice + 'd' + matchobj.group(2)

                attack['damage'] = re.sub(r'(\d+)d(\d+)', lsub, attack['damage'])

            result = sheet_attack(attack, outargs)
            for f in result['embed'].fields:
                embed.add_field(name=f.name, value=f.value, inline=f.inline)
        else:  # special spell (MM)
            outargs = copy.copy(args)  # just make an attack for it
            outargs['d'] = "+".join(args.get('d', [])) or None
            for _arg, _value in outargs.items():
                if isinstance(_value, list):
                    outargs[_arg] = _value[-1]
            attack = {"name": spell['name'],
                      "damage": spell.get("damage", "0"),
                      "attackBonus": None}
            result = sheet_attack(attack, outargs)
            for f in result['embed'].fields:
                embed.add_field(name=f.name, value=f.value, inline=f.inline)

        if spell['type'] == 'save':  # context!
            if isinstance(spell['text'], list):
                text = '\n'.join(spell['text'])
            else:
                text = spell['text']
            sentences = text.split('.')
            context = ""
            for i, s in enumerate(sentences):
                if spell.get('save', {}).get('save').lower() + " saving throw" in s.lower():
                    if i + 2 < len(sentences):
                        _ctx = s + '. ' + sentences[i + 1] + '. ' + sentences[i + 2] + '. '
                        context += _ctx.strip()
                    elif i + 1 < len(sentences):
                        _ctx = s + '. ' + sentences[i + 1] + '. '
                        context += _ctx.strip()
                    else:
                        _ctx = s + '. '
                        context += _ctx.strip()
                    context += '\n'
            embed.add_field(name="Effect", value=context)
        elif spell['type'] == 'attack':
            if isinstance(spell['text'], list):
                text = '\n'.join(spell['text'])
            else:
                text = spell['text']
            sentences = text.split('.')
            context = ""
            for i, s in enumerate(sentences):
                if " spell attack" in s.lower():
                    if i + 2 < len(sentences):
                        _ctx = s + '. ' + sentences[i + 1] + '. ' + sentences[i + 2] + '. '
                        context += _ctx.strip()
                    elif i + 1 < len(sentences):
                        _ctx = s + '. ' + sentences[i + 1] + '. '
                        context += _ctx.strip()
                    else:
                        _ctx = s + '. '
                        context += _ctx.strip()
                    context += '\n'
            embed.add_field(name="Effect", value=context)

        embed.colour = character.get('settings', {}).get('color') or random.randint(0, 0xffffff)
        await self.bot.say(embed=embed)

    def parse_roll_args(self, args, character):
        return args.replace('SPELL', str(parse_cvars("SPELL", character)).replace('PROF', str(
            character.get('stats', {}).get('proficiencyBonus', "0"))))

    async def _old_cast(self, ctx, args, fallback=False):
        try:
            guild_id = ctx.message.server.id
            pm = self.bot.db.not_json_get("lookup_settings", {}).get(guild_id, {}).get("pm_result", False)

        except:
            pm = False

        args = args.split('-r')
        args = [a.strip() for a in args]
        spellName = args[0].strip()

        spell = getSpell(spellName, return_spell=True)
        self.bot.botStats["spells_looked_up_session"] += 1
        self.bot.db.incr('spells_looked_up_life')
        if spell['spell'] is None:
            return await self.bot.say(spell['string'][0], delete_after=15)
        result = spell['string']
        spell = spell['spell']

        if len(args) == 1:
            rolls = spell.get('roll', None)
            if isinstance(rolls, list):
                active_character = self.bot.db.not_json_get('active_characters', {}).get(
                    ctx.message.author.id)  # get user's active
                if active_character is not None:
                    user_characters = self.bot.db.not_json_get(ctx.message.author.id + '.characters',
                                                               {})  # grab user's characters
                    character = user_characters[active_character]  # get Sheet of character
                    rolls = self.parse_roll_args('\n'.join(rolls), character)
                    rolls = rolls.split('\n')
                out = "**{} casts {}:** ".format(ctx.message.author.mention, spell['name']) + '\n'.join(
                    roll(r, inline=True).skeleton for r in rolls)
            elif rolls is not None:
                active_character = self.bot.db.not_json_get('active_characters', {}).get(
                    ctx.message.author.id)  # get user's active
                if active_character is not None:
                    user_characters = self.bot.db.not_json_get(ctx.message.author.id + '.characters',
                                                               {})  # grab user's characters
                    character = user_characters[active_character]  # get Sheet of character
                    rolls = self.parse_roll_args(rolls, character)
                out = "**{} casts {}:** ".format(ctx.message.author.mention, spell['name']) + roll(rolls,
                                                                                                   inline=True).skeleton
            else:
                out = "**{} casts {}!** ".format(ctx.message.author.mention, spell['name'])
        else:
            rolls = args[1:]
            roll_results = ""
            for r in rolls:
                res = roll(r, inline=True)
                if res.total is not None:
                    roll_results += res.result + '\n'
                else:
                    roll_results += "**Effect:** " + r
            out = "**{} casts {}:**\n".format(ctx.message.author.mention, spell['name']) + roll_results

        if fallback: out = "Spell not supported by new cast, falling back to old cast.\n" + out
        await self.bot.say(out)
        for r in result:
            if pm:
                await self.bot.send_message(ctx.message.author, r)
            else:
                await self.bot.say(r, delete_after=15)
