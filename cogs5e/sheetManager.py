"""
Created on Jan 19, 2017

@author: andrew
"""
import asyncio
import copy
import logging
import random
import re
import shlex
import sys
import traceback
from socket import timeout

import discord
import numexpr
import pygsheets
from discord.ext import commands
from discord.ext.commands.cooldowns import BucketType
from googleapiclient.errors import HttpError
from pygsheets.exceptions import SpreadsheetNotFound, NoValidUrlKeyFound
from ws4py.exc import HandshakeError

from cogs5e.funcs.dice import roll
from cogs5e.funcs.sheetFuncs import sheet_attack
from cogs5e.models.character import Character
from cogs5e.models.embeds import EmbedWithCharacter
from cogs5e.models.errors import InvalidArgument
from cogs5e.sheets.beyondPdf import BeyondPDFSheetParser
from cogs5e.sheets.dicecloud import DicecloudParser
from cogs5e.sheets.gsheet import GoogleSheet
from cogs5e.sheets.pdfsheet import PDFSheetParser
from cogs5e.sheets.sheetParser import SheetParser
from utils.functions import extract_gsheet_id_from_url, parse_snippets, generate_token
from utils.functions import list_get, get_positivity, a_or_an, get_selection
from utils.loggers import TextLogger

log = logging.getLogger(__name__)


class SheetManager:
    """Commands to import a character sheet from Dicecloud (https://dicecloud.com) or the fillable Wizards character PDF."""

    def __init__(self, bot):
        self.bot = bot
        self.active_characters = self.bot.db.not_json_get('active_characters', {})
        self.bot.loop.create_task(self.backup_user_data())
        self.logger = TextLogger('dicecloud.txt')

        self.gsheet_client = None
        self.bot.loop.create_task(self.init_gsheet_client())

    async def init_gsheet_client(self):
        def _():
            return pygsheets.authorize(service_file='avrae-0b82f09d7ab3.json')

        self.gsheet_client = await self.bot.loop.run_in_executor(None, _)

    async def backup_user_data(self):
        try:
            await self.bot.wait_until_ready()
            while not self.bot.is_closed:
                await asyncio.sleep(7200)  # every 2 hours
                self.bot.db.jset('active_characters_backup', self.bot.db.jget('active_characters', {}))
                self.bot.db.jset('damage_snippets_backup', self.bot.db.jget('damage_snippets', {}))
                # self.bot.db.jset('char_vars_backup', self.bot.db.jget('char_vars', {}))
        except asyncio.CancelledError:
            pass

    async def new_arg_stuff(self, args, ctx, character):
        args = parse_snippets(args, ctx)
        args = await character.parse_cvars(args, ctx)
        args = shlex.split(args)
        args = self.parse_args(args)
        return args

    def parse_args(self, args):
        out = {}
        index = 0
        cFlag = False
        for a in args:
            if cFlag:
                cFlag = False
                continue
            if a == '-b' or a == '-d' or a == '-c':
                if out.get(a.replace('-', '')) is None:
                    out[a.replace('-', '')] = list_get(index + 1, '0', args)
                else:
                    out[a.replace('-', '')] += ' + ' + list_get(index + 1, '0', args)
            elif re.match(r'-d\d+', a) or a in ('-resist', '-immune', '-vuln'):
                if out.get(a.replace('-', '')) is None:
                    out[a.replace('-', '')] = list_get(index + 1, '0', args)
                else:
                    out[a.replace('-', '')] += '|' + list_get(index + 1, '0', args)
            elif a in ('-phrase',):
                if out.get(a.replace('-', '')) is None:
                    out[a.replace('-', '')] = list_get(index + 1, '0', args)
                else:
                    out[a.replace('-', '')] += '\n' + list_get(index + 1, '0', args)
            elif a == '-f':
                if out.get(a.replace('-', '')) is None:
                    out[a.replace('-', '')] = [list_get(index + 1, '0', args)]
                else:
                    out[a.replace('-', '')].append(list_get(index + 1, '0', args))
            elif a.startswith('-'):
                out[a.replace('-', '')] = list_get(index + 1, 'MISSING_ARGUMENT', args)
            else:
                out[a] = 'True'
                index += 1
                continue
            index += 2
            cFlag = True
        return out

    @commands.command(pass_context=True, aliases=['a'])
    async def attack(self, ctx, atk_name: str = 'list', *, args: str = ''):
        """Rolls an attack for the current active character.
        Valid Arguments: adv/dis
                         adv#/dis# (applies adv to the first # attacks)
                         -ac [target ac]
                         -b [to hit bonus]
                         -d [damage bonus]
                         -d# [applies damage to the first # hits]
                         -rr [times to reroll]
                         -t [target]
                         -c [damage bonus on crit]
                         -phrase [flavor text]
                         -title [title] *note: [charname], [aname], and [target] will be replaced automatically*
                         -resist [damage resistance]
                         -immune [damage immunity]
                         -vuln [damage vulnerability]
                         crit (automatically crit)
                         ea (Elven Accuracy double advantage)
                         -f "Field Title|Field Text" (see !embed)
                         [user snippet]"""
        char = Character.from_ctx(ctx)

        attacks = char.get_attacks()

        if atk_name == 'list':
            tempAttacks = []
            for a in attacks:
                if a['attackBonus'] is not None:
                    try:
                        bonus = numexpr.evaluate(a['attackBonus'])
                    except:
                        bonus = a['attackBonus']
                    tempAttacks.append("**{0}:** +{1} To Hit, {2} damage.".format(a['name'],
                                                                                  bonus,
                                                                                  a['damage'] if a[
                                                                                                     'damage'] is not None else 'no'))
                else:
                    tempAttacks.append("**{0}:** {1} damage.".format(a['name'],
                                                                     a['damage'] if a['damage'] is not None else 'no'))
            if not tempAttacks:
                tempAttacks = ['No attacks.']
            a = '\n'.join(tempAttacks)
            if len(a) > 2000:
                a = ', '.join(atk['name'] for atk in attacks)
            if len(a) > 2000:
                a = "Too many attacks, values hidden!"
            return await self.bot.say("{}'s attacks:\n{}".format(char.get_name(), a))

        try:  # fuzzy search for atk_name
            attack = next(a for a in attacks if atk_name.lower() == a.get('name').lower())
        except StopIteration:
            try:
                attack = next(a for a in attacks if atk_name.lower() in a.get('name').lower())
            except StopIteration:
                return await self.bot.say('No attack with that name found.')

        args = await self.new_arg_stuff(args, ctx, char)
        args['name'] = char.get_name()
        args['criton'] = args.get('criton') or char.get_setting('criton', 20)
        args['hocrit'] = char.get_setting('hocrit', False)
        args['reroll'] = char.get_setting('reroll', 0)
        args['crittype'] = char.get_setting('crittype', 'default')
        if attack.get('details') is not None:
            attack['details'] = await char.parse_cvars(attack['details'], ctx)

        result = sheet_attack(attack, args, EmbedWithCharacter(char, name=False))
        embed = result['embed']

        _fields = args.get('f', [])
        if type(_fields) == list:
            for f in _fields:
                title = f.split('|')[0] if '|' in f else '\u200b'
                value = "|".join(f.split('|')[1:]) if '|' in f else f
                embed.add_field(name=title, value=value)

        await self.bot.say(embed=embed)
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass

    @commands.command(pass_context=True, aliases=['s'])
    async def save(self, ctx, skill, *, args: str = ''):
        """Rolls a save for your current active character.
        Args: adv/dis
              -b [conditional bonus]
              -phrase [flavor text]
              -title [title] *note: [charname] and [sname] will be replaced automatically*
              -image [image URL]
              -dc [dc] (does not apply to Death Saves)"""
        if skill == 'death':
            ds_cmd = self.bot.get_command('game deathsave')
            if ds_cmd is None:
                return await self.bot.say("Error: GameTrack cog not loaded.")
            return await ctx.invoke(ds_cmd, *shlex.split(args))

        char = Character.from_ctx(ctx)
        saves = char.get_saves()
        if not saves:
            return await self.bot.say('You must update your character sheet first.')
        try:
            save = next(a for a in saves.keys() if skill.lower() == a.lower())
        except StopIteration:
            try:
                save = next(a for a in saves.keys() if skill.lower() in a.lower())
            except StopIteration:
                return await self.bot.say('That\'s not a valid save.')

        embed = EmbedWithCharacter(char, name=False)

        skill_effects = char.get_skill_effects()
        args += ' ' + skill_effects.get(save, '')  # dicecloud v11 - autoadv

        args = await self.new_arg_stuff(args, ctx, char)
        adv = 0 if args.get('adv', False) and args.get('dis', False) else 1 if args.get('adv',
                                                                                        False) else -1 if args.get(
            'dis', False) else 0
        b = args.get('b', None)
        phrase = args.get('phrase', None)
        formatted_d20 = ('1d20' if adv == 0 else '2d20' + ('kh1' if adv == 1 else 'kl1')) \
                        + ('ro{}'.format(char.get_setting('reroll', 0))
                           if not char.get_setting('reroll', '0') == '0' else '')

        if b is not None:
            save_roll = roll(formatted_d20 + '{:+}'.format(saves[save]) + '+' + b, adv=adv, inline=True)
        else:
            save_roll = roll(formatted_d20 + '{:+}'.format(saves[save]), adv=adv, inline=True)

        embed.title = args.get('title', '').replace('[charname]', char.get_name()).replace('[sname]', re.sub(
            r'((?<=[a-z])[A-Z]|(?<!\A)[A-Z](?=[a-z]))', r' \1', save).title()) \
                      or '{} makes {}!'.format(char.get_name(),
                                               a_or_an(re.sub(r'((?<=[a-z])[A-Z]|(?<!\A)[A-Z](?=[a-z]))', r' \1',
                                                              save).title()))

        try:
            dc = int(args.get('dc', None))
        except (ValueError, TypeError):
            dc = None
        dc_phrase = None
        if dc:
            dc_phrase = f"**DC {dc}**"
            embed.set_footer(text="Success!" if save_roll.total >= dc else "Failure!")

        embed.description = (f"{dc_phrase}\n" if dc_phrase is not None else '') + save_roll.skeleton + (
            '\n*' + phrase + '*' if phrase is not None else '')

        if args.get('image') is not None:
            embed.set_thumbnail(url=args.get('image'))

        await self.bot.say(embed=embed)
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass

    @commands.command(pass_context=True, aliases=['c'])
    async def check(self, ctx, check, *, args: str = ''):
        """Rolls a check for your current active character.
        Args: adv/dis
              -b [conditional bonus]
              -mc [minimum roll]
              -phrase [flavor text]
              -title [title] *note: [charname] and [cname] will be replaced automatically*
              -dc [dc]"""
        char = Character.from_ctx(ctx)
        skills = char.get_skills()
        if not skills:
            return await self.bot.say('You must update your character sheet first.')
        try:
            skill = next(a for a in skills.keys() if check.lower() == a.lower())
        except StopIteration:
            try:
                skill = next(a for a in skills.keys() if check.lower() in a.lower())
            except StopIteration:
                return await self.bot.say('That\'s not a valid check.')

        embed = EmbedWithCharacter(char, False)

        skill_effects = char.get_skill_effects()
        args += ' ' + skill_effects.get(skill, '')  # dicecloud v7 - autoadv

        args = await self.new_arg_stuff(args, ctx, char)
        adv = 0 if args.get('adv', False) and args.get('dis', False) else 1 if args.get('adv',
                                                                                        False) else -1 if args.get(
            'dis', False) else 0
        b = args.get('b', None)
        mc = args.get('mc', None)
        phrase = args.get('phrase', None)
        formatted_d20 = ('1d20' if adv == 0 else '2d20' + ('kh1' if adv == 1 else 'kl1')) \
                        + ('ro{}'.format(char.get_setting('reroll', 0))
                           if not char.get_setting('reroll', '0') == '0' else '') \
                        + ('mi{}'.format(mc) if mc is not None else '')

        if b is not None:
            check_roll = roll(formatted_d20 + '{:+}'.format(skills[skill]) + '+' + b, adv=adv, inline=True)
        else:
            check_roll = roll(formatted_d20 + '{:+}'.format(skills[skill]), adv=adv, inline=True)

        embed.title = args.get('title', '').replace('[charname]', char.get_name()).replace('[cname]', re.sub(
            r'((?<=[a-z])[A-Z]|(?<!\A)[A-Z](?=[a-z]))', r' \1', skill).title()) \
                      or '{} makes {} check!'.format(char.get_name(),
                                                     a_or_an(re.sub(r'((?<=[a-z])[A-Z]|(?<!\A)[A-Z](?=[a-z]))', r' \1',
                                                                    skill).title()))

        try:
            dc = int(args.get('dc', None))
        except (ValueError, TypeError):
            dc = None
        dc_phrase = None
        if dc:
            dc_phrase = f"**DC {dc}**"
            embed.set_footer(text="Success!" if check_roll.total >= dc else "Failure!")

        embed.description = (f"{dc_phrase}\n" if dc_phrase is not None else '') + check_roll.skeleton + (
            '\n*' + phrase + '*' if phrase is not None else '')
        if args.get('image') is not None:
            embed.set_thumbnail(url=args.get('image'))
        await self.bot.say(embed=embed)
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass

    @commands.group(pass_context=True, invoke_without_command=True)
    async def desc(self, ctx):
        """Prints or edits a description of your currently active character."""
        user_characters = self.bot.db.not_json_get(ctx.message.author.id + '.characters', {})
        active_character = self.bot.db.not_json_get('active_characters', {}).get(ctx.message.author.id)
        if active_character is None:
            return await self.bot.say('You have no character active.')
        character = user_characters[active_character]
        stats = character.get('stats')
        image = stats.get('image', '')
        desc = stats.get('description', 'No description available.')
        if desc is None:
            desc = 'No description available.'
        if len(desc) > 2048:
            desc = desc[:2044] + '...'
        elif len(desc) < 2:
            desc = 'No description available.'

        embed = discord.Embed()
        embed.title = stats.get('name')
        embed.description = desc
        embed.colour = random.randint(0, 0xffffff) if character.get('settings', {}).get(
            'color') is None else character.get('settings', {}).get('color')
        embed.set_thumbnail(url=image)

        await self.bot.say(embed=embed)
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass

    @desc.command(pass_context=True, name='update', aliases=['edit'])
    async def edit_desc(self, ctx, *, desc):
        """Updates the character description."""
        user_characters = self.bot.db.not_json_get(ctx.message.author.id + '.characters', {})
        active_character = self.bot.db.not_json_get('active_characters', {}).get(ctx.message.author.id)
        if active_character is None:
            return await self.bot.say('You have no character active.')
        character = user_characters[active_character]

        overrides = character.get('overrides', {})
        overrides['desc'] = desc
        character['stats']['description'] = desc

        character['overrides'] = overrides
        user_characters[active_character] = character
        self.bot.db.not_json_set(ctx.message.author.id + '.characters', user_characters)

        await self.bot.say("Description updated!")

    @desc.command(pass_context=True, name='remove', aliases=['delete'])
    async def remove_desc(self, ctx):
        """Removes the character description, returning to the default."""
        user_characters = self.bot.db.not_json_get(ctx.message.author.id + '.characters', {})
        active_character = self.bot.db.not_json_get('active_characters', {}).get(ctx.message.author.id)
        if active_character is None:
            return await self.bot.say('You have no character active.')
        character = user_characters[active_character]

        overrides = character.get('overrides', {})
        if not 'desc' in overrides:
            return await self.bot.say("There is no custom description set.")
        else:
            del overrides['desc']

        character['overrides'] = overrides
        user_characters[active_character] = character
        self.bot.db.not_json_set(ctx.message.author.id + '.characters', user_characters)

        await self.bot.say("Description override removed! Use `!update` to return to the old description.")

    @commands.group(pass_context=True, invoke_without_command=True)
    async def portrait(self, ctx):
        """Shows or edits the image of your currently active character."""
        user_characters = self.bot.db.not_json_get(ctx.message.author.id + '.characters', {})
        active_character = self.bot.db.not_json_get('active_characters', {}).get(ctx.message.author.id)
        if active_character is None:
            return await self.bot.say('You have no character active.')
        character = user_characters[active_character]
        stats = character.get('stats')
        image = stats.get('image', '')
        if image == '': return await self.bot.say('No image available.')
        embed = discord.Embed()
        embed.title = stats.get('name')
        embed.colour = random.randint(0, 0xffffff) if character.get('settings', {}).get(
            'color') is None else character.get('settings', {}).get('color')
        embed.set_image(url=image)

        await self.bot.say(embed=embed)
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass

    @portrait.command(pass_context=True, name='update', aliases=['edit'])
    async def edit_portrait(self, ctx, *, url):
        """Updates the character portrait."""
        user_characters = self.bot.db.not_json_get(ctx.message.author.id + '.characters', {})
        active_character = self.bot.db.not_json_get('active_characters', {}).get(ctx.message.author.id)
        if active_character is None:
            return await self.bot.say('You have no character active.')
        character = user_characters[active_character]

        overrides = character.get('overrides', {})
        overrides['image'] = url
        character['stats']['image'] = url

        character['overrides'] = overrides
        user_characters[active_character] = character
        self.bot.db.not_json_set(ctx.message.author.id + '.characters', user_characters)

        await self.bot.say("Portrait updated!")

    @portrait.command(pass_context=True, name='remove', aliases=['delete'])
    async def remove_portrait(self, ctx):
        """Removes the character portrait, returning to the default."""
        user_characters = self.bot.db.not_json_get(ctx.message.author.id + '.characters', {})
        active_character = self.bot.db.not_json_get('active_characters', {}).get(ctx.message.author.id)
        if active_character is None:
            return await self.bot.say('You have no character active.')
        character = user_characters[active_character]

        overrides = character.get('overrides', {})
        if not 'image' in overrides:
            return await self.bot.say("There is no custom portrait set.")
        else:
            del overrides['image']

        character['overrides'] = overrides
        user_characters[active_character] = character
        self.bot.db.not_json_set(ctx.message.author.id + '.characters', user_characters)

        await self.bot.say("Portrait override removed! Use `!update` to return to the old portrait.")

    @commands.command(pass_context=True, hidden=True)  # hidden, as just called by token command
    async def playertoken(self, ctx):
        """Generates and sends a token for use on VTTs."""

        char = Character.from_ctx(ctx)
        img_url = char.get_image()
        color_override = char.get_setting('color')
        if not img_url:
            return await self.bot.send_message(ctx.message.channel, "This character has no image.")

        try:
            processed = await generate_token(img_url, color_override)
        except Exception as e:
            return await self.bot.send_message(ctx.message.channel, f"Error generating token: {e}")

        await self.bot.send_file(ctx.message.channel, processed, content="I generated this token for you! If it seems "
                                                                         "wrong, you can make your own at "
                                                                         "<http://rolladvantage.com/tokenstamp/>!",
                                 filename="image.png")

    @commands.command(pass_context=True)
    async def sheet(self, ctx):
        """Prints the embed sheet of your currently active character."""
        user_characters = self.bot.db.not_json_get(ctx.message.author.id + '.characters', {})
        active_character = self.bot.db.not_json_get('active_characters', {}).get(ctx.message.author.id)
        if active_character is None:
            return await self.bot.say('You have no character active.')
        character = user_characters[active_character]
        parser = SheetParser(character)
        embed = parser.get_embed()
        embed.colour = embed.colour if character.get('settings', {}).get('color') is None else character.get('settings',
                                                                                                             {}).get(
            'color')

        await self.bot.say(embed=embed)
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass

    @commands.group(pass_context=True, aliases=['char'], invoke_without_command=True)
    async def character(self, ctx, *, name: str = None):
        """Switches the active character.
        Breaks for characters created before Jan. 20, 2017."""
        user_characters = self.bot.db.not_json_get(ctx.message.author.id + '.characters', None)
        self.active_characters = self.bot.db.not_json_get('active_characters', {})
        active_character = self.active_characters.get(ctx.message.author.id)
        if user_characters is None:
            return await self.bot.say('You have no characters.')

        if name is None:
            if active_character is None:
                return await self.bot.say('You have no character active.')
            return await self.bot.say(
                'Currently active: {}'.format(user_characters[active_character].get('stats', {}).get('name')))

        choices = []
        for url, character in user_characters.items():
            if character.get('stats', {}).get('name', '').lower() == name.lower():
                choices.append((character, url))
            elif name.lower() in character.get('stats', {}).get('name', '').lower():
                choices.append((character, url))

        if len(choices) > 1:
            choiceList = [(f"{c[0].get('stats', {}).get('name', 'Unnamed')} (`{c[1]})`", c) for c in choices]

            char = await get_selection(ctx, choiceList, delete=True)
            if char is None:
                return await self.bot.say('Selection timed out or was cancelled.')

            char_name = char[0].get('stats', {}).get('name', 'Unnamed')
            char_url = char[1]
        elif len(choices) == 0:
            return await self.bot.say('Character not found.')
        else:
            char_name = choices[0][0].get('stats', {}).get('name', 'Unnamed')
            char_url = choices[0][1]

        name = char_name

        self.active_characters[ctx.message.author.id] = char_url
        self.bot.db.not_json_set('active_characters', self.active_characters)

        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass

        await self.bot.say("Active character changed to {}.".format(name), delete_after=20)

    @character.command(pass_context=True, name='list')
    async def character_list(self, ctx):
        """Lists your characters."""
        user_characters = self.bot.db.not_json_get(ctx.message.author.id + '.characters', None)
        if user_characters is None:
            return await self.bot.say('You have no characters.')

        await self.bot.say('Your characters:\n{}'.format(
            ', '.join([user_characters[c].get('stats', {}).get('name', '') for c in user_characters])))

    @character.command(pass_context=True, name='delete')
    async def character_delete(self, ctx, *, name):
        """Deletes a character."""
        user_characters = self.bot.db.not_json_get(ctx.message.author.id + '.characters', None)
        self.active_characters = self.bot.db.not_json_get('active_characters', {})
        if user_characters is None:
            return await self.bot.say('You have no characters.')

        choices = []
        for url, character in user_characters.items():
            if character.get('stats', {}).get('name', '').lower() == name.lower():
                choices.append((character, url))
            elif name.lower() in character.get('stats', {}).get('name', '').lower():
                choices.append((character, url))

        if len(choices) > 1:
            choiceList = [(f"{c[0].get('stats', {}).get('name', 'Unnamed')} (`{c[1]})`", c) for c in choices]

            char = await get_selection(ctx, choiceList, delete=True)
            if char is None:
                return await self.bot.say('Selection timed out or was cancelled.')

            char_name = char[0].get('stats', {}).get('name', 'Unnamed')
            char_url = char[1]
        elif len(choices) == 0:
            return await self.bot.say('Character not found.')
        else:
            char_name = choices[0][0].get('stats', {}).get('name', 'Unnamed')
            char_url = choices[0][1]

        name = char_name

        await self.bot.say('Are you sure you want to delete {}? (Reply with yes/no)'.format(name))
        reply = await self.bot.wait_for_message(timeout=30, author=ctx.message.author)
        reply = get_positivity(reply.content) if reply is not None else None
        if reply is None:
            return await self.bot.say('Timed out waiting for a response or invalid response.')
        elif reply:
            self.active_characters[ctx.message.author.id] = None
            del user_characters[char_url]
            self.bot.db.not_json_set(ctx.message.author.id + '.characters', user_characters)
            self.bot.db.not_json_set('active_characters', self.active_characters)
            return await self.bot.say('{} has been deleted.'.format(name))
        else:
            return await self.bot.say("OK, cancelling.")

    @commands.command(pass_context=True)
    @commands.cooldown(1, 15, BucketType.user)
    async def update(self, ctx, *, args=''):
        """Updates the current character sheet, preserving all settings.
        Valid Arguments: `-v` - Shows character sheet after update is complete.
        `-cc` - Updates custom counters from Dicecloud."""
        active_character = self.bot.db.not_json_get('active_characters', {}).get(ctx.message.author.id)
        user_characters = self.bot.db.not_json_get(ctx.message.author.id + '.characters', {})
        if active_character is None:
            return await self.bot.say('You have no character active.')
        url = active_character
        old_character = user_characters[url]
        prefixes = 'dicecloud-', 'pdf-', 'google-', 'beyondpdf-'
        _id = copy.copy(url)
        for p in prefixes:
            if url.startswith(p):
                _id = url[len(p):]
                break
        sheet_type = old_character.get('type', 'dicecloud')
        if sheet_type == 'dicecloud':
            parser = DicecloudParser(_id)
            loading = await self.bot.say('Updating character data from Dicecloud...')
            self.logger.text_log(ctx, "Dicecloud Request ({}): ".format(_id))
        elif sheet_type == 'pdf':
            if not 0 < len(ctx.message.attachments) < 2:
                return await self.bot.say('You must call this command in the same message you upload a PDF sheet.')

            file = ctx.message.attachments[0]

            loading = await self.bot.say('Updating character data from PDF...')
            parser = PDFSheetParser(file)
        elif sheet_type == 'google':
            try:
                parser = GoogleSheet(_id, self.gsheet_client)
            except AssertionError:
                return await self.bot.say("I am still connecting to Google. Try again in 15-30 seconds.")
            loading = await self.bot.say('Updating character data from Google...')
        elif sheet_type == 'beyond-pdf':
            if not 0 < len(ctx.message.attachments) < 2:
                return await self.bot.say('You must call this command in the same message you upload a PDF sheet.')

            file = ctx.message.attachments[0]

            loading = await self.bot.say('Updating character data from Beyond PDF...')
            parser = BeyondPDFSheetParser(file)
        else:
            return await self.bot.say("Error: Unknown sheet type.")
        try:
            character = await parser.get_character()
        except timeout:
            return await self.bot.say(
                "We're having some issues connecting to Dicecloud or Google right now. Please try again in a few minutes.")
        except HttpError:
            return await self.bot.edit_message(loading,
                                               "Google returned an error trying to access your sheet. Please ensure your sheet is shared and try again in a few minutes.")
        except Exception as e:
            return await self.bot.edit_message(loading, 'Error: Invalid character sheet.\n' + str(e))

        try:
            if sheet_type == 'dicecloud':
                fmt = character.get('characters')[0].get('name')
                sheet = parser.get_sheet()
                if '-cc' in args:
                    counters = parser.get_custom_counters()
            elif sheet_type == 'pdf':
                fmt = character.get('CharacterName')
                sheet = parser.get_sheet()
            elif sheet_type == 'google':
                fmt = character.cell("C6").value
                sheet = await parser.get_sheet()
            elif sheet_type == 'beyond-pdf':
                fmt = character.get('CharacterName')
                sheet = parser.get_sheet()
            await self.bot.edit_message(loading, 'Updated and saved data for {}!'.format(fmt))
        except TypeError as e:
            log.info(f"Exception in parser.get_sheet: {e}")
            log.debug('\n'.join(traceback.format_exception(type(e), e, e.__traceback__)))
            return await self.bot.edit_message(loading,
                                               'Invalid character sheet. '
                                               'If you are using a dicecloud sheet, '
                                               'make sure you have shared the sheet so that anyone with the '
                                               'link can view.')
        except Exception as e:
            return await self.bot.edit_message(loading, 'Error: Invalid character sheet.\n' + str(e))

        embed = sheet['embed']
        sheet = sheet['sheet']
        sheet['settings'] = old_character.get('settings', {})
        sheet['overrides'] = old_character.get('overrides', {})
        sheet['cvars'] = old_character.get('cvars', {})
        sheet['consumables'] = old_character.get('consumables', {})

        overrides = old_character.get('overrides', {})
        sheet['stats']['description'] = overrides.get('desc') or sheet.get('stats', {}).get("description",
                                                                                            "No description available.")
        sheet['stats']['image'] = overrides.get('image') or sheet.get('stats', {}).get('image', '')
        spells = set(sheet['spellbook']['spells'])
        spells.update(overrides.get('spells', []))
        sheet['spellbook']['spells'] = list(spells)

        c = Character(sheet, url).initialize_consumables()

        if '-cc' in args and sheet_type == 'dicecloud':
            for counter in counters:
                displayType = 'bubble' if c.evaluate_cvar(counter['max']) < 6 else None
                try:
                    c.create_consumable(counter['name'], maxValue=str(counter['max']),
                                        minValue=str(counter['min']),
                                        reset=counter['reset'], displayType=displayType, live=counter['live'])
                except InvalidArgument:
                    pass

        # print(sheet)
        embed.colour = embed.colour if sheet.get('settings', {}).get('color') is None else sheet.get('settings',
                                                                                                     {}).get('color')

        if c.get_combat_id() and not self.bot.db.exists(c.get_combat_id()):
            c.leave_combat()

        c.commit(ctx).set_active(ctx)
        del user_characters, character, parser, old_character  # pls don't freak out avrae
        if '-v' in args:
            await self.bot.say(embed=embed)

    @commands.command(pass_context=True)
    async def transferchar(self, ctx, user: discord.Member):
        """Gives a copy of the active character to another user."""
        character = Character.from_ctx(ctx)
        overwrite = ''

        user_characters = self.bot.db.not_json_get(f'{user.id}.characters', {})
        if character.id in user_characters:
            overwrite = "**WARNING**: This will overwrite an existing character."

        await self.bot.say(f"{user.mention}, accept a copy of {character.get_name()}? (Type yes/no)\n{overwrite}")
        m = await self.bot.wait_for_message(timeout=300, author=user, channel=ctx.message.channel,
                                            check=lambda m: get_positivity(m.content) is not None)

        if m is None or not get_positivity(m.content): return await self.bot.say("Transfer not confirmed, aborting.")

        character.manual_commit(self.bot, user.id)
        await self.bot.say(f"Copied {character.get_name()} to {user.display_name}'s storage.")

    @commands.command(pass_context=True)
    async def csettings(self, ctx, *, args):
        """Updates personalization settings for the currently active character.
        Valid Arguments:
        `color <hex color>` - Colors all embeds this color.
        `criton <number>` - Makes attacks crit on something other than a 20.
        `reroll <number>` - Defines a number that a check will automatically reroll on, for cases such as Halfling Luck.
        `hocrit true/false` - Enables/disables a half-orc's Brutal Critical.
        `srslots true/false` - Enables/disables whether spell slots reset on a Short Rest.
        `embedimage true/false` - Enables/disables whether a character's image is automatically embedded.
        `crittype 2x/default` - Sets whether crits double damage or dice."""
        user_characters = self.bot.db.not_json_get(ctx.message.author.id + '.characters', {})
        active_character = self.bot.db.not_json_get('active_characters', {}).get(ctx.message.author.id)
        if active_character is None:
            return await self.bot.say('You have no character active.')
        character = user_characters[active_character]
        args = shlex.split(args)

        if character.get('settings') is None:
            character['settings'] = {}

        out = 'Operations complete!\n'
        index = 0
        for arg in args:
            if arg == 'color':
                color = list_get(index + 1, None, args)
                if color is None:
                    out += '\u2139 Your character\'s current color is {}. Use "!csettings color reset" to reset it to random.\n' \
                        .format(hex(character['settings'].get('color')) if character['settings'].get(
                        'color') is not None else "random")
                elif color.lower() == 'reset':
                    character['settings']['color'] = None
                    out += "\u2705 Color reset to random.\n"
                else:
                    try:
                        color = int(color, base=16)
                    except (ValueError, TypeError):
                        out += '\u274c Unknown color. Use "!csettings color reset" to reset it to random.\n'
                    else:
                        if not 0 <= color <= 0xffffff:
                            out += '\u274c Invalid color.\n'
                        else:
                            character['settings']['color'] = color
                            out += "\u2705 Color set to {}.\n".format(hex(color))
            if arg == 'criton':
                criton = list_get(index + 1, None, args)
                if criton is None:
                    out += '\u2139 Your character\'s current crit range is {}. Use "!csettings criton reset" to reset it to 20.\n' \
                        .format(str(character['settings'].get('criton')) + '-20' if character['settings'].get(
                        'criton') is not None else "20")
                elif criton.lower() == 'reset':
                    character['settings']['criton'] = None
                    out += "\u2705 Crit range reset to 20.\n"
                else:
                    try:
                        criton = int(criton)
                    except (ValueError, TypeError):
                        out += '\u274c Invalid number. Use "!csettings criton reset" to reset it to 20.\n'
                    else:
                        if not 0 < criton <= 20:
                            out += '\u274c Crit range must be between 1 and 20.\n'
                        elif criton == 20:
                            character['settings']['criton'] = None
                            out += "\u2705 Crit range reset to 20.\n"
                        else:
                            character['settings']['criton'] = criton
                            out += "\u2705 Crit range set to {}-20.\n".format(criton)
            if arg == 'reroll':
                reroll = list_get(index + 1, None, args)
                if reroll is None:
                    out += '\u2139 Your character\'s current reroll is {}. Use "!csettings reroll reset" to reset it.\n' \
                        .format(str(character['settings'].get('reroll')) if character['settings'].get(
                        'reroll') is not '0' else "0")
                elif reroll.lower() == 'reset':
                    character['settings']['reroll'] = '0'
                    out += "\u2705 Reroll reset.\n"
                else:
                    try:
                        reroll = int(reroll)
                    except (ValueError, TypeError):
                        out += '\u274c Invalid number. Use "!csettings reroll reset" to reset it.\n'
                    else:
                        if not 1 <= reroll <= 20:
                            out += '\u274c Reroll must be between 1 and 20.\n'
                        else:
                            character['settings']['reroll'] = reroll
                            out += "\u2705 Reroll set to {}.\n".format(reroll)
            if arg == 'critdmg':  # DEPRECATED
                critdmg = list_get(index + 1, None, args)
                if critdmg is None:
                    out += '\u2139 Your character\'s current critdmg is {}. Use "!csettings critdmg reset" to reset it.\n' \
                        .format(str(character['settings'].get('critdmg')) if character['settings'].get(
                        'critdmg') is not '0' else "0")
                elif critdmg.lower() == 'reset':
                    del character['settings']['critdmg']
                    out += "\u2705 Critdmg reset.\n"
                else:
                    character['settings']['critdmg'] = critdmg
                    out += "\u2705 Critdmg set to {}.\n".format(critdmg)
            if arg == 'hocrit':
                hocrit = list_get(index + 1, None, args)
                if hocrit is None:
                    out += '\u2139 Half-orc crits are currently {}.\n' \
                        .format("enabled" if character['settings'].get('hocrit') else "disabled")
                else:
                    try:
                        hocrit = get_positivity(hocrit)
                    except AttributeError:
                        out += '\u274c Invalid input. Use "!csettings hocrit false" to reset it.\n'
                    else:
                        character['settings']['hocrit'] = hocrit
                        out += "\u2705 Half-orc crits {}.\n".format(
                            "enabled" if character['settings'].get('hocrit') else "disabled")
            if arg == 'srslots':
                srslots = list_get(index + 1, None, args)
                if srslots is None:
                    out += '\u2139 Short rest slots are currently {}.\n' \
                        .format("enabled" if character['settings'].get('srslots') else "disabled")
                else:
                    try:
                        srslots = get_positivity(srslots)
                    except AttributeError:
                        out += '\u274c Invalid input. Use "!csettings srslots false" to reset it.\n'
                    else:
                        character['settings']['srslots'] = srslots
                        out += "\u2705 Short Rest slots {}.\n".format(
                            "enabled" if character['settings'].get('srslots') else "disabled")
            if arg == 'embedimage':
                embedimage = list_get(index + 1, None, args)
                if embedimage is None:
                    out += '\u2139 Embed Image is currently {}.\n' \
                        .format("enabled" if character['settings'].get('embedimage') else "disabled")
                else:
                    try:
                        embedimage = get_positivity(embedimage)
                    except AttributeError:
                        out += '\u274c Invalid input. Use "!csettings embedimage true" to reset it.\n'
                    else:
                        character['settings']['embedimage'] = embedimage
                        out += "\u2705 Embed Image {}.\n".format(
                            "enabled" if character['settings'].get('embedimage') else "disabled")
            if arg == 'crittype':
                crittype = list_get(index + 1, None, args)
                if crittype is None:
                    out += '\u2139 Crit type is currently {}.\n' \
                        .format(character['settings'].get('crittype', 'default'))
                else:
                    try:
                        assert crittype in ('2x', 'default')
                    except AssertionError:
                        out += '\u274c Invalid input. Use "!csettings crittype default" to reset it.\n'
                    else:
                        character['settings']['crittype'] = crittype
                        out += "\u2705 Crit type set to {}.\n".format(character['settings'].get('crittype'))
            index += 1
        user_characters[active_character] = character
        self.bot.db.not_json_set(ctx.message.author.id + '.characters', user_characters)
        await self.bot.say(out)

    @commands.group(pass_context=True, invoke_without_command=True)
    async def cvar(self, ctx, name, *, value=None):
        """Commands to manage character variables for use in snippets and aliases.
        Character variables can be called in the `-phrase` tag by surrounding the variable name with `{}` (calculates) or `<>` (prints).
        Arguments surrounded with `{{}}` will be evaluated as a custom script.
        See http://avrae.io/cheatsheets/aliasing for more help.
        Dicecloud `statMod` and `stat` variables are also available."""
        character = Character.from_ctx(ctx)

        if value is None:  # display value
            cvar = character.get_cvar(name)
            if cvar is None: cvar = 'Not defined.'
            return await self.bot.say('**' + name + '**:\n' + cvar)

        try:
            assert not name in character.get_stat_vars()
            assert not any(c in name for c in '-/()[]\\.^$*+?|{}')
        except AssertionError:
            return await self.bot.say("Could not create cvar: already builtin, or contains invalid character!")

        character.set_cvar(name, value).commit(ctx)
        await self.bot.say('Character variable `{}` set to: `{}`'.format(name, value))

    @cvar.command(pass_context=True, name='remove', aliases=['delete'])
    async def remove_cvar(self, ctx, name):
        """Deletes a cvar from the currently active character."""
        user_characters = self.bot.db.not_json_get(ctx.message.author.id + '.characters', {})
        active_character = self.bot.db.not_json_get('active_characters', {}).get(ctx.message.author.id)
        if active_character is None:
            return await self.bot.say('You have no character active.')
        character = user_characters[active_character]

        try:
            del character.get('cvars', {})[name]
        except KeyError:
            return await self.bot.say('Character variable not found.')

        user_characters[active_character] = character  # commit
        self.bot.db.not_json_set(ctx.message.author.id + '.characters', user_characters)

        await self.bot.say('Character variable {} removed.'.format(name))

    @cvar.command(pass_context=True, name='list')
    async def list_cvar(self, ctx):
        """Lists all cvars for the currently active character."""
        character = Character.from_ctx(ctx)
        cvars = character.get_cvars()

        await self.bot.say('{}\'s character variables:\n{}'.format(character.get_name(),
                                                                   ', '.join(sorted([name for name in cvars.keys()]))))

    async def _confirm_overwrite(self, ctx, _id):
        """Prompts the user if command would overwrite another character.
        Returns True to overwrite, False or None otherwise."""
        user_characters = self.bot.db.not_json_get(f'{ctx.message.author.id}.characters', {})
        if _id in user_characters:
            await ctx.bot.send_message(ctx.message.channel,
                                       "Warning: This will overwrite a character with the same ID. Do you wish to continue (reply yes/no)?\n"
                                       "If you only wanted to update your character, run `!update` instead.")
            reply = await self.bot.wait_for_message(timeout=30, author=ctx.message.author)
            replyBool = get_positivity(reply.content) if reply is not None else None
            return replyBool
        return True

    @commands.command(pass_context=True)
    async def dicecloud(self, ctx, url: str, *, args=""):
        """Loads a character sheet from [Dicecloud](https://dicecloud.com/), resetting all settings.
        Share your character with `avrae` on Dicecloud (edit perms) for live updates.
        __Valid Arguments__
        `-cc` - Will automatically create custom counters for class resources and features."""
        if 'dicecloud.com' in url:
            url = url.split('/character/')[-1].split('/')[0]

        override = await self._confirm_overwrite(ctx, f"dicecloud-{url}")
        if not override: return await self.bot.say("Character overwrite unconfirmed. Aborting.")

        self.logger.text_log(ctx, "Dicecloud Request ({}): ".format(url))

        loading = await self.bot.say('Loading character data from Dicecloud...')
        parser = DicecloudParser(url)
        try:
            character = await parser.get_character()
        except (timeout, HandshakeError):
            return await self.bot.say(
                "I'm having some issues connecting to Dicecloud right now. Please try again in a few minutes.")
        try:
            await self.bot.edit_message(loading, 'Loaded and saved data for {}!'.format(
                character.get('characters')[0].get('name')))
        except TypeError:
            return await self.bot.edit_message(loading,
                                               'Invalid character sheet. Make sure you have shared the sheet so that anyone with the link can view.')

        try:
            sheet = parser.get_sheet()
        except Exception as e:
            traceback.print_exception(type(e), e, e.__traceback__, file=sys.stderr)
            return await self.bot.edit_message(loading,
                                               'Error: Invalid character sheet. Capitalization matters!\n' + str(e))

        c = Character(sheet['sheet'], f"dicecloud-{url}").initialize_consumables()

        if '-cc' in args:
            for counter in parser.get_custom_counters():
                displayType = 'bubble' if c.evaluate_cvar(counter['max']) < 6 else None
                try:
                    c.create_consumable(counter['name'], maxValue=str(counter['max']), minValue=str(counter['min']),
                                        reset=counter['reset'], displayType=displayType, live=counter['live'])
                except InvalidArgument:
                    pass

        c.commit(ctx).set_active(ctx)
        embed = sheet['embed']
        try:
            await self.bot.say(embed=embed)
        except:
            await self.bot.say(
                "...something went wrong generating your character sheet. Don't worry, your character has been saved. This is usually due to an invalid image.")

    @commands.command(pass_context=True)
    async def pdfsheet(self, ctx):
        """Loads a character sheet from [this](http://andrew-zhu.com/avrae/PDFSheet.pdf) PDF, resetting all settings."""

        if not 0 < len(ctx.message.attachments) < 2:
            return await self.bot.say('You must call this command in the same message you upload the sheet.')

        file = ctx.message.attachments[0]

        override = await self._confirm_overwrite(ctx, file['filename'])
        if not override: return await self.bot.say("Character overwrite unconfirmed. Aborting.")

        loading = await self.bot.say('Loading character data from PDF...')
        parser = PDFSheetParser(file)
        try:
            await parser.get_character()
        except Exception as e:
            log.error("Error loading PDFChar sheet:")
            traceback.print_exception(type(e), e, e.__traceback__, file=sys.stderr)
            return await self.bot.edit_message(loading, 'Error: Invalid character sheet.\n' + str(e))

        try:
            sheet = parser.get_sheet()
            await self.bot.edit_message(loading, 'Loaded and saved data for {}!'.format(
                sheet['sheet'].get('stats', {}).get('name')))
        except Exception as e:
            log.error("Error loading PDFChar sheet:")
            traceback.print_exception(type(e), e, e.__traceback__, file=sys.stderr)
            return await self.bot.edit_message(loading, 'Error: Invalid character sheet.\n' + str(e))

        Character(sheet['sheet'], f"pdf-{file['filename']}").initialize_consumables().commit(ctx).set_active(ctx)

        embed = sheet['embed']
        await self.bot.say(embed=embed)

    @commands.command(pass_context=True)
    async def beyond(self, ctx):
        """Loads a character sheet from a D&D Beyond-generated PDF, resetting all settings."""

        if not 0 < len(ctx.message.attachments) < 2:
            return await self.bot.say('You must call this command in the same message you upload the sheet.')

        file = ctx.message.attachments[0]

        override = await self._confirm_overwrite(ctx, file['filename'])
        if not override: return await self.bot.say("Character overwrite unconfirmed. Aborting.")

        loading = await self.bot.say('Loading character data from Beyond PDF...')
        parser = BeyondPDFSheetParser(file)
        try:
            await parser.get_character()
        except Exception as e:
            log.error("Error loading BeyondPDF sheet:")
            traceback.print_exception(type(e), e, e.__traceback__, file=sys.stderr)
            return await self.bot.edit_message(loading, 'Error: Invalid character sheet.\n' + str(e))

        try:
            sheet = parser.get_sheet()
            await self.bot.edit_message(loading, 'Loaded and saved data for {}!'.format(
                sheet['sheet'].get('stats', {}).get('name')))
        except Exception as e:
            log.error("Error loading BeyondPDF sheet:")
            traceback.print_exception(type(e), e, e.__traceback__, file=sys.stderr)
            return await self.bot.edit_message(loading, 'Error: Invalid character sheet.\n' + str(e))

        Character(sheet['sheet'], f"beyondpdf-{file['filename']}").initialize_consumables().commit(ctx).set_active(ctx)

        embed = sheet['embed']
        await self.bot.say(embed=embed)

    @commands.command(pass_context=True)
    async def gsheet(self, ctx, url: str):
        """Loads a character sheet from [this Google sheet](https://docs.google.com/spreadsheets/d/1etrBJ0qCDXACovYHUM4XvjE0erndThwRLcUQzX6ts8w/edit?usp=sharing), resetting all settings. The sheet must be shared with Avrae (see specific command help) for this to work.
        Avrae's google account is `avrae-320@avrae-bot.iam.gserviceaccount.com`."""

        loading = await self.bot.say('Loading character data from Google... (This usually takes ~30 sec)')
        try:
            url = extract_gsheet_id_from_url(url)
        except NoValidUrlKeyFound:
            return await self.bot.edit_message(loading, "This is not a Google Sheets link.")

        override = await self._confirm_overwrite(ctx, f"google-{url}")
        if not override: return await self.bot.say("Character overwrite unconfirmed. Aborting.")

        try:
            parser = GoogleSheet(url, self.gsheet_client)
        except AssertionError:
            return await self.bot.edit_message(loading, "I am still connecting to Google. Try again in 15-30 seconds.")

        try:
            character = await parser.get_character()
        except (KeyError, SpreadsheetNotFound):
            return await self.bot.edit_message(loading,
                                               "Invalid character sheet. Make sure you've shared it with me at `avrae-320@avrae-bot.iam.gserviceaccount.com`!")
        except HttpError:
            return await self.bot.edit_message(loading,
                                               "Error: Google returned an error. Please ensure your sheet is shared with `avrae-320@avrae-bot.iam.gserviceaccount.com` and try again in a few minutes.")

        try:
            sheet = await parser.get_sheet()
        except Exception as e:
            traceback.print_exception(type(e), e, e.__traceback__, file=sys.stderr)
            return await self.bot.edit_message(loading, 'Error: Invalid character sheet.\n' + str(e))

        try:
            await self.bot.edit_message(loading, 'Loaded and saved data for {}!'.format(character.cell("C6").value))
        except TypeError as e:
            traceback.print_exception(type(e), e, e.__traceback__, file=sys.stderr)
            return await self.bot.edit_message(loading,
                                               'Invalid character sheet. Make sure you have shared the sheet so that anyone with the link can view.')

        Character(sheet['sheet'], f"google-{url}").initialize_consumables().commit(ctx).set_active(ctx)

        embed = sheet['embed']
        try:
            await self.bot.say(embed=embed)
        except:
            await self.bot.say(
                "...something went wrong generating your character sheet. Don't worry, your character has been saved. This is usually due to an invalid image.")
