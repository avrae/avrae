'''
Created on Jan 19, 2017

@author: andrew
'''
import asyncio
import copy
from datetime import datetime
import json
import random
import re
import shlex
from socket import timeout
import sys
import traceback

import discord
from discord.ext import commands
from gspread.utils import extract_id_from_url
import numexpr

from cogs5e.funcs.dice import roll
from cogs5e.funcs.sheetFuncs import sheet_attack
from cogs5e.sheets.dicecloud import DicecloudParser
from cogs5e.sheets.gsheet import GoogleSheet
from cogs5e.sheets.pdfsheet import PDFSheetParser
from cogs5e.sheets.sheetParser import SheetParser
from utils.functions import list_get, embed_trim, get_positivity, a_or_an
from gspread.exceptions import SpreadsheetNotFound


class SheetManager:
    """Commands to import a character sheet from Dicecloud (https://dicecloud.com) or the fillable Wizards character PDF. Currently in Beta."""
    
    def __init__(self, bot):
        self.bot = bot
        self.active_characters = self.bot.db.not_json_get('active_characters', {})
        self.snippets = self.bot.db.not_json_get('damage_snippets', {})
        self.cvars = self.bot.db.not_json_get('char_vars', {})
        self.bot.loop.create_task(self.backup_user_data())
        
    async def backup_user_data(self):
        try:
            await self.bot.wait_until_ready()
            while not self.bot.is_closed:
                await asyncio.sleep(1800)  # every half hour
                self.bot.db.jset('active_characters_backup', self.bot.db.jget('active_characters', {}))
                self.bot.db.jset('damage_snippets_backup', self.bot.db.jget('damage_snippets', {}))
                self.bot.db.jset('char_vars_backup', self.bot.db.jget('char_vars', {}))
        except asyncio.CancelledError:
            pass
        
    def arg_stuff(self, args, ctx, character, char_id):
        args = self.parse_snippets(args, ctx.message.author.id)
        args = self.parse_cvars(args, ctx.message.author.id, character, char_id)
        args = self.parse_args(args)
        return args
    
    def parse_cvars(self, args, _id, character, char_id):
        tempargs = []
        user_cvars = copy.copy(self.bot.db.not_json_get('char_vars', {}).get(_id, {}).get(char_id, {}))
        stat_vars = {}
        stats = copy.copy(character['stats'])
        for stat in ('strength', 'dexterity', 'constitution', 'intelligence', 'wisdom', 'charisma'):
            stats[stat+'Score'] = stats[stat]
            del stats[stat]
        stat_vars.update(stats)
        stat_vars.update(character['levels'])
        stat_vars['hp'] = character['hp']
        stat_vars['armor'] = character['armor']
        stat_vars.update(character['saves'])
        for arg in args:
            for var in re.finditer(r'{([^{}]+)}', arg):
                raw = var.group(0)
                out = var.group(1)
                for cvar, value in user_cvars.items():
                    out = out.replace(cvar, str(value))
                for cvar, value in stat_vars.items():
                    out = out.replace(cvar, str(value))
                arg = arg.replace(raw, '{}'.format(roll(out).total))
            for var in re.finditer(r'<([^<>]+)>', arg):
                raw = var.group(0)
                out = var.group(1)
                for cvar, value in user_cvars.items():
                    out = out.replace(cvar, str(value))
                for cvar, value in stat_vars.items():
                    out = out.replace(cvar, str(value))
                arg = arg.replace(raw, out)
            tempargs.append(arg)
        return tempargs
        
    def parse_args(self, args):
        out = {}
        index = 0
        cFlag = False
        for a in args:
            if cFlag:
                cFlag = False
                continue
            if a == '-b' or a == '-d' or a == '-c':
                if out.get(a.replace('-', '')) is None: out[a.replace('-', '')] = list_get(index + 1, '0', args)
                else: out[a.replace('-', '')] += ' + ' + list_get(index + 1, '0', args)
            elif re.match(r'-d\d+', a) or a in ('-resist', '-immune', '-vuln'):
                if out.get(a.replace('-', '')) is None: out[a.replace('-', '')] = list_get(index + 1, '0', args)
                else: out[a.replace('-', '')] += '|' + list_get(index + 1, '0', args)
            elif a in ('-phrase'):
                if out.get(a.replace('-', '')) is None: out[a.replace('-', '')] = list_get(index + 1, '0', args)
                else: out[a.replace('-', '')] += '\n' + list_get(index + 1, '0', args)
            elif a.startswith('-'):
                out[a.replace('-', '')] = list_get(index + 1, 'MISSING_ARGUMENT', args)
            else:
                out[a] = 'True'
                index += 1
                continue
            index += 2
            cFlag = True
        return out
    
    def parse_snippets(self, args, _id):
        tempargs = []
        user_snippets = self.bot.db.not_json_get('damage_snippets', {}).get(_id, {})
        for arg in args: # parse snippets
            for snippet, arguments in user_snippets.items():
                if arg == snippet: 
                    tempargs += shlex.split(arguments)
                    break
            tempargs.append(arg)
        return tempargs
        
    @commands.command(pass_context=True, aliases=['a'])
    async def attack(self, ctx, atk_name:str='list', *, args:str=''):
        """Rolls an attack for the current active character.
        Valid Arguments: adv/dis
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
                         [user snippet]"""
        user_characters = self.bot.db.not_json_get(ctx.message.author.id + '.characters', {}) # grab user's characters
        active_character = self.bot.db.not_json_get('active_characters', {}).get(ctx.message.author.id) # get user's active
        if active_character is None:
            return await self.bot.say('You have no character active.')
        character = user_characters[active_character] # get Sheet of character
        attacks = character.get('attacks') # get attacks
        
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
                                                                                  a['damage'] if a['damage'] is not None else 'no'))
                else:
                    tempAttacks.append("**{0}:** {1} damage.".format(a['name'],
                                                                     a['damage'] if a['damage'] is not None else 'no'))
            if tempAttacks == []:
                tempAttacks = ['No attacks.']
            a = '\n'.join(tempAttacks)
            if len(a) > 2000:
                a = ', '.join(atk['name'] for atk in attacks)
            if len(a) > 2000:
                a = "Too many attacks, values hidden!"
            return await self.bot.say("{}'s attacks:\n{}".format(character.get('stats', {}).get('name', "NONAME"), a))
        
        try: #fuzzy search for atk_name
            attack = next(a for a in attacks if atk_name.lower() == a.get('name').lower())
        except StopIteration:
            try:
                attack = next(a for a in attacks if atk_name.lower() in a.get('name').lower())
            except StopIteration:
                return await self.bot.say('No attack with that name found.')
                
        args = shlex.split(args)
        args = self.arg_stuff(args, ctx, character, active_character)
        args['name'] = character.get('stats', {}).get('name', "NONAME")
        args['criton'] = character.get('settings', {}).get('criton', 20) or 20
        if attack.get('details') is not None:
            attack['details'] = self.parse_cvars([attack['details']], ctx.message.author.id, character, active_character)[0]
        
        result = sheet_attack(attack, args)
        embed = result['embed']
        embed.colour = random.randint(0, 0xffffff) if character.get('settings', {}).get('color') is None else character.get('settings', {}).get('color')
        await self.bot.say(embed=embed)
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass
    
    @commands.command(pass_context=True, aliases=['s'])
    async def save(self, ctx, skill, *, args:str=''):
        """Rolls a save for your current active character.
        Args: adv/dis
              -b [conditional bonus]
              -phrase [flavor text]
              -title [title] *note: [charname] and [sname] will be replaced automatically*"""
        user_characters = self.bot.db.not_json_get(ctx.message.author.id + '.characters', {})
        active_character = self.bot.db.not_json_get('active_characters', {}).get(ctx.message.author.id)
        if active_character is None:
            return await self.bot.say('You have no character active.')
        character = user_characters[active_character]
        saves = character.get('saves')
        if saves is None:
            return await self.bot.say('You must update your character sheet first.')
        try:
            save = next(a for a in saves.keys() if skill.lower() == a.lower())
        except StopIteration:
            try:
                save = next(a for a in saves.keys() if skill.lower() in a.lower())
            except StopIteration:
                return await self.bot.say('That\'s not a valid save.')
        
        embed = discord.Embed()
        embed.colour = random.randint(0, 0xffffff) if character.get('settings', {}).get('color') is None else character.get('settings', {}).get('color')
        
        args = shlex.split(args)
        args = self.arg_stuff(args, ctx, character, active_character)
        adv = 0 if args.get('adv', False) and args.get('dis', False) else 1 if args.get('adv', False) else -1 if args.get('dis', False) else 0
        b = args.get('b', None)
        phrase = args.get('phrase', None)
        
        if b is not None:
            save_roll = roll('1d20' + '{:+}'.format(saves[save]) + '+' + b, adv=adv, inline=True)
        else:
            save_roll = roll('1d20' + '{:+}'.format(saves[save]), adv=adv, inline=True)
            
        embed.title = args.get('title', '').replace('[charname]', character.get('stats', {}).get('name')).replace('[sname]', re.sub(r'((?<=[a-z])[A-Z]|(?<!\A)[A-Z](?=[a-z]))', r' \1', save).title()) \
                      or '{} makes {}!'.format(character.get('stats', {}).get('name'),
                                               a_or_an(re.sub(r'((?<=[a-z])[A-Z]|(?<!\A)[A-Z](?=[a-z]))', r' \1', save).title()))
            
        embed.description = save_roll.skeleton + ('\n*' + phrase + '*' if phrase is not None else '')
        
        if args.get('image') is not None:
            embed.set_thumbnail(url=args.get('image'))
        
        await self.bot.say(embed=embed)
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass
    
    @commands.command(pass_context=True, aliases=['c'])
    async def check(self, ctx, check, *, args:str=''):
        """Rolls a check for your current active character.
        Args: adv/dis
              -b [conditional bonus]
              -mc [minimum roll]
              -phrase [flavor text]
              -title [title] *note: [charname] and [cname] will be replaced automatically*"""
        user_characters = self.bot.db.not_json_get(ctx.message.author.id + '.characters', {})
        active_character = self.bot.db.not_json_get('active_characters', {}).get(ctx.message.author.id)
        if active_character is None:
            return await self.bot.say('You have no character active.')
        character = user_characters[active_character]
        skills = character.get('skills')
        if skills is None:
            return await self.bot.say('You must update your character sheet first.')
        try:
            skill = next(a for a in skills.keys() if check.lower() == a.lower())
        except StopIteration:
            try:
                skill = next(a for a in skills.keys() if check.lower() in a.lower())
            except StopIteration:
                return await self.bot.say('That\'s not a valid check.')
        
        embed = discord.Embed()
        embed.colour = random.randint(0, 0xffffff) if character.get('settings', {}).get('color') is None else character.get('settings', {}).get('color')
        
        args = shlex.split(args)
        args = self.arg_stuff(args, ctx, character, active_character)
        adv = 0 if args.get('adv', False) and args.get('dis', False) else 1 if args.get('adv', False) else -1 if args.get('dis', False) else 0
        b = args.get('b', None)
        mc = args.get('mc', None)
        phrase = args.get('phrase', None)
        formatted_d20 = ('1d20' if adv == 0 else '2d20' + ('kh1' if adv == 1 else 'kl1')) \
                        + ('ro{}'.format(character.get('settings', {}).get('reroll', 0)) 
                        if not character.get('settings', {}).get('reroll', '0') == '0' else '') \
                        + ('mi{}'.format(mc) if mc is not None else '')
#                         ('mi{}'.format(character.get('settings', {}).get('mincheck', 1))
#                         if not character.get('settings', {}).get('mincheck', '1') == '1' else '')
        
        if b is not None:
            check_roll = roll(formatted_d20 + '{:+}'.format(skills[skill]) + '+' + b, adv=adv, inline=True)
        else:
            check_roll = roll(formatted_d20 + '{:+}'.format(skills[skill]), adv=adv, inline=True)
        
        embed.title = args.get('title', '').replace('[charname]', character.get('stats', {}).get('name')).replace('[cname]', re.sub(r'((?<=[a-z])[A-Z]|(?<!\A)[A-Z](?=[a-z]))', r' \1', skill).title()) \
                      or '{} makes {} check!'.format(character.get('stats', {}).get('name'),
                                                     a_or_an(re.sub(r'((?<=[a-z])[A-Z]|(?<!\A)[A-Z](?=[a-z]))', r' \1', skill).title()))
        embed.description = check_roll.skeleton + ('\n*' + phrase + '*' if phrase is not None else '')
        if args.get('image') is not None:
            embed.set_thumbnail(url=args.get('image'))
        await self.bot.say(embed=embed)
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass
            
    @commands.command(pass_context=True)
    async def desc(self, ctx):
        """Prints a description of your currently active character."""
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
        embed.colour = random.randint(0, 0xffffff) if character.get('settings', {}).get('color') is None else character.get('settings', {}).get('color')
        embed.set_thumbnail(url=image)
        
        await self.bot.say(embed=embed)
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass
        
    @commands.command(pass_context=True)
    async def portrait(self, ctx):
        """Shows the image of your currently active character."""
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
        embed.colour = random.randint(0, 0xffffff) if character.get('settings', {}).get('color') is None else character.get('settings', {}).get('color')
        embed.set_image(url=image)
        
        await self.bot.say(embed=embed)
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass
        
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
        embed.colour = embed.colour if character.get('settings', {}).get('color') is None else character.get('settings', {}).get('color')
        
        await self.bot.say(embed=embed)
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass
            
    @commands.command(pass_context=True, aliases=['char'])
    async def character(self, ctx, name:str=None, *, args:str=''):
        """Switches the active character.
        Breaks for characters created before Jan. 20, 2017.
        Valid arguments:
        `delete` - deletes a character.
        `list` - lists all of your characters."""
        user_characters = self.bot.db.not_json_get(ctx.message.author.id + '.characters', None)
        self.active_characters = self.bot.db.not_json_get('active_characters', {})
        active_character = self.active_characters.get(ctx.message.author.id)
        if user_characters is None:
            return await self.bot.say('You have no characters.')
        
        if name is None:
            return await self.bot.say('Currently active: {}'.format(user_characters[active_character].get('stats', {}).get('name')), delete_after=20)
        
        if name == 'list':
            return await self.bot.say('Your characters:\n{}'.format(', '.join([user_characters[c].get('stats', {}).get('name', '') for c in user_characters])))
        args = shlex.split(args)
        
        char_url = None
        char_name = None
        for url, character in user_characters.items():
            if character.get('stats', {}).get('name', '').lower() == name.lower():
                char_url = url
                char_name = character.get('stats').get('name')
                break
            
            if name.lower() in character.get('stats', {}).get('name', '').lower():
                char_url = url
                char_name = character.get('stats').get('name')
        
        if char_url is None:
            return await self.bot.say('Character not found.')
        
        name = char_name
        
        if 'delete' in args:
            await self.bot.say('Are you sure you want to delete {}? (Reply with yes/no)'.format(name))
            reply = await self.bot.wait_for_message(timeout=30, author=ctx.message.author)
            reply = get_positivity(reply.content) if reply is not None else None
            if reply is None:
                return await self.bot.say('Timed out waiting for a response or invalid response.')
            elif reply:
                self.active_characters[ctx.message.author.id] = None
                del user_characters[char_url]
                self.bot.db.not_json_set(ctx.message.author.id + '.characters', user_characters)
                return await self.bot.say('{} has been deleted.'.format(name))
            else:
                return await self.bot.say("OK, cancelling.")
        
        self.active_characters[ctx.message.author.id] = char_url
        self.bot.db.not_json_set('active_characters', self.active_characters)
        
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass
        
        await self.bot.say("Active character changed to {}.".format(name), delete_after=20)
        
    @commands.command(pass_context=True)
    async def update(self, ctx, *, args=''):
        """Updates the current character sheet, preserving all settings.
        Valid Arguments: -h - Hides character sheet after update is complete."""
        active_character = self.bot.db.not_json_get('active_characters', {}).get(ctx.message.author.id)
        user_characters = self.bot.db.not_json_get(ctx.message.author.id + '.characters', {})
        if active_character is None:
            return await self.bot.say('You have no character active.')
        url = active_character
        sheet_type = user_characters[url].get('type', 'dicecloud')
        if sheet_type == 'dicecloud':
            parser = DicecloudParser(url)
            loading = await self.bot.say('Updating character data from Dicecloud...')
        elif sheet_type == 'pdf':
            if not 0 < len(ctx.message.attachments) < 2:
                return await self.bot.say('You must call this command in the same message you upload a PDF sheet.')
            
            file = ctx.message.attachments[0]
            
            loading = await self.bot.say('Updating character data from PDF...')
            parser = PDFSheetParser(file)
        elif sheet_type == 'google':
            parser = GoogleSheet(url)
            loading = await self.bot.say('Updating character data from Google...')
        else:
            return await self.bot.say("Error: Unknown sheet type.")
        try:
            character = await parser.get_character()
        except Exception as e:
            return await self.bot.edit_message(loading, 'Error: Invalid character sheet.\n' + str(e))
        except timeout:
            return await self.bot.say("We're having some issues connecting to Dicecloud or Google right now. Please try again in a few minutes.")
        
        try:
            if sheet_type == 'dicecloud':
                fmt = character.get('characters')[0].get('name')
                sheet = parser.get_sheet()
            elif sheet_type == 'pdf':
                fmt = character.get('CharacterName')
                sheet = parser.get_sheet()
            elif sheet_type == 'google':
                fmt = character.acell("C6").value
                sheet = await parser.get_sheet()
            await self.bot.edit_message(loading, 'Updated and saved data for {}!'.format(fmt))
        except TypeError as e:
            #traceback.print_exc()
            return await self.bot.edit_message(loading, 'Invalid character sheet. Make sure you have shared the sheet so that anyone with the link can view.')
        except Exception as e:
            return await self.bot.edit_message(loading, 'Error: Invalid character sheet.\n' + str(e))

        embed = sheet['embed']
        sheet = sheet['sheet']
        sheet['settings'] = user_characters[url].get('settings', {})
        user_characters[url] = sheet
        embed.colour = embed.colour if sheet.get('settings', {}).get('color') is None else sheet.get('settings', {}).get('color')
        self.bot.db.not_json_set(ctx.message.author.id + '.characters', user_characters)
        if not '-h' in args:
            await self.bot.say(embed=embed)
    
    @commands.command(pass_context=True)
    async def csettings(self, ctx, *, args):
        """Updates personalization settings for the currently active character.
        Valid Arguments:
        `color <hex color>` - Colors all embeds this color.
        `criton <number>` - Makes attacks crit on something other than a 20.
        `mincheck <number>` - Does nothing right now.
        `reroll <number>` - Defines a number that a check will automatically reroll on, for cases such as Halfling Luck."""
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
                           .format(hex(character['settings'].get('color')) if character['settings'].get('color') is not None else "random")
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
                    .format(str(character['settings'].get('criton')) + '-20' if character['settings'].get('criton') is not None else "20")
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
            if arg == 'mincheck':
                mincheck = list_get(index + 1, None, args)
                if mincheck is None:
                    out += '\u2139 Your character\'s current minimum check roll is {}. Use "!csettings mincheck reset" to reset it to 1.\n' \
                    .format(str(character['settings'].get('mincheck')) if character['settings'].get('mincheck') is not '1' else "1")
                elif mincheck.lower() == 'reset':
                    character['settings']['mincheck'] = '1'
                    out += "\u2705 Minimum check roll reset to 1.\n"
                else:
                    try:
                        mincheck = int(mincheck)
                    except (ValueError, TypeError):
                        out += '\u274c Invalid number. Use "!csettings mincheck reset" to reset it to 1.\n'
                    else:
                        if not 1 <= mincheck <= 20:
                            out += '\u274c Minimum check roll must be between 1 and 20.\n'
                        elif mincheck == 1:
                            character['settings']['mincheck'] = '1'
                            out += "\u2705 Minimum check roll reset to 1.\n"
                        else:
                            character['settings']['mincheck'] = mincheck
                            out += "\u2705 Minimum check roll set to {}.\n".format(mincheck)
            if arg == 'reroll':
                reroll = list_get(index + 1, None, args)
                if reroll is None:
                    out += '\u2139 Your character\'s current reroll is {}. Use "!csettings reroll reset" to reset it.\n' \
                    .format(str(character['settings'].get('reroll')) if character['settings'].get('reroll') is not '0' else "0")
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
            index += 1
        user_characters[active_character] = character
        self.bot.db.not_json_set(ctx.message.author.id + '.characters', user_characters)
        await self.bot.say(out)
        
    @commands.command(pass_context=True)
    async def snippet(self, ctx, snipname, *, snippet=None):
        """Creates a snippet to use in attack macros.
        Ex: *!snippet sneak -d "2d6[Sneak Attack]"* can be used as *!a sword sneak*.
        Valid commands: *!snippet list* - lists all user snippets.
        *!snippet [name]* - shows what the snippet is a shortcut for.
        *!snippet remove [name]* - deletes a snippet."""
        user_id = ctx.message.author.id
        self.snippets = self.bot.db.not_json_get('damage_snippets', {})
        user_snippets = self.snippets.get(user_id, {})
        
        if snipname == 'list':
            return await self.bot.say('Your snippets:\n{}'.format(', '.join([name for name in user_snippets.keys()])))
        
        if snippet is None:
            return await self.bot.say('**' + snipname + '**:\n```md\n' + user_snippets.get(snipname, 'Not defined.') + '\n```')
        
        if snipname == 'remove' or snipname == 'delete':
            try:
                del user_snippets[snippet]
            except KeyError:
                return await self.bot.say('Snippet not found.')
            await self.bot.say('Shortcut {} removed.'.format(snippet))
        else:
            user_snippets[snipname] = snippet
            await self.bot.say('Shortcut {} added for arguments:\n`{}`'.format(snipname, snippet))
        
        self.snippets[user_id] = user_snippets
        self.bot.db.not_json_set('damage_snippets', self.snippets)
        
    @commands.group(pass_context=True, invoke_without_command=True)
    async def cvar(self, ctx, name, *, value=None):
        """Commands to manage character variables for use in snippets and aliases.
        Character variables can be called in the `-phrase` tag by surrounding the variable name with `{}` (calculates) or `<>` (prints).
        Dicecloud `statMod` and `statScore` variables are also available."""
        active_character = self.bot.db.not_json_get('active_characters', {}).get(ctx.message.author.id) # get user's active
        if active_character is None:
            return await self.bot.say('You have no character active.')
        user_id = ctx.message.author.id
        self.cvars = self.bot.db.not_json_get('char_vars', {})
        user_cvars = self.cvars.get(user_id, {})
        if value is None:
            cvar = user_cvars.get(active_character, {}).get(name)
            if cvar is None: cvar = 'Not defined.'
            return await self.bot.say('**' + name + '**:\n' + cvar)
        
        if user_cvars.get(active_character) is None: user_cvars[active_character] = {}
        user_cvars[active_character][name] = value
        self.cvars[user_id] = user_cvars
        self.bot.db.not_json_set('char_vars', self.cvars)
        await self.bot.say('Variable `{}` set to: `{}`'.format(name, value))
        
    @cvar.command(pass_context=True, name='remove', aliases=['delete'])
    async def remove_cvar(self, ctx, name):
        """Deletes a cvar from the currently active character."""
        active_character = self.bot.db.not_json_get('active_characters', {}).get(ctx.message.author.id) # get user's active
        if active_character is None:
            return await self.bot.say('You have no character active.')
        user_id = ctx.message.author.id
        self.cvars = self.bot.db.not_json_get('char_vars', {})
        user_cvars = self.cvars.get(user_id, {})
        try:
            del user_cvars.get(active_character, {})[name]
        except KeyError:
            return await self.bot.say('Variable not found.')
        self.cvars[user_id] = user_cvars
        self.bot.db.not_json_set('char_vars', self.cvars)
        await self.bot.say('Variable {} removed.'.format(name))
        
    @cvar.command(pass_context=True, name='list')
    async def list_cvar(self, ctx):
        """Lists all cvars for the currently active character."""
        active_character = self.bot.db.not_json_get('active_characters', {}).get(ctx.message.author.id) # get user's active
        if active_character is None:
            return await self.bot.say('You have no character active.')
        user_id = ctx.message.author.id
        user_cvars = self.bot.db.not_json_get('char_vars', {}).get(user_id, {})
        await self.bot.say('Your variables:\n{}'.format(', '.join([name for name in user_cvars.get(active_character,{}).keys()])))
        
    
    @commands.command(pass_context=True)
    async def dicecloud(self, ctx, url:str):
        """Loads a character sheet from [Dicecloud](https://dicecloud.com/), resetting all settings."""
        if 'dicecloud.com' in url:
            url = url.split('/character/')[-1].split('/')[0]
        
        loading = await self.bot.say('Loading character data from Dicecloud...')
        parser = DicecloudParser(url)
        try:
            character = await parser.get_character()
        except timeout:
            return await self.bot.say("I'm having some issues connecting to Dicecloud right now. Please try again in a few minutes.")
        try:
            await self.bot.edit_message(loading, 'Loaded and saved data for {}!'.format(character.get('characters')[0].get('name')))
        except TypeError:
            return await self.bot.edit_message(loading, 'Invalid character sheet. Make sure you have shared the sheet so that anyone with the link can view.')
        
        try:
            sheet = parser.get_sheet()
        except Exception as e:
            traceback.print_exception(type(e), e, e.__traceback__, file=sys.stderr)
            return await self.bot.edit_message(loading, 'Error: Invalid character sheet. Capitalization matters!\n' + str(e))
        
        self.active_characters = self.bot.db.not_json_get('active_characters', {})
        self.active_characters[ctx.message.author.id] = url
        self.bot.db.not_json_set('active_characters', self.active_characters)
        user_characters = self.bot.db.not_json_get(ctx.message.author.id + '.characters', {})
        user_characters[url] = sheet['sheet']
        self.bot.db.not_json_set(ctx.message.author.id + '.characters', user_characters)
        
        embed = sheet['embed']
        try:
            await self.bot.say(embed=embed)
        except:
            await self.bot.say("...something went wrong generating your character sheet. Don't worry, your character has been saved. This is usually due to an invalid image.")
        
    @commands.command(pass_context=True)
    async def pdfsheet(self, ctx):
        """Loads a character sheet from [this](https://www.reddit.com/r/dndnext/comments/2iyydv/5th_edition_editable_pdf_character_sheets/) PDF, resetting all settings."""
        
        if not 0 < len(ctx.message.attachments) < 2:
            return await self.bot.say('You must call this command in the same message you upload the sheet.')
        
        file = ctx.message.attachments[0]
        
        loading = await self.bot.say('Loading character data from PDF...')
        parser = PDFSheetParser(file)
        try:
            await parser.get_character()
        except Exception as e:
            print("Error loading PDFChar sheet:")
            traceback.print_exception(type(e), e, e.__traceback__, file=sys.stderr)
            return await self.bot.edit_message(loading, 'Error: Invalid character sheet.\n' + str(e))
        
        try:
            sheet = parser.get_sheet()
            await self.bot.edit_message(loading, 'Loaded and saved data for {}!'.format(sheet['sheet'].get('stats', {}).get('name')))
        except Exception as e:
            print("Error loading PDFChar sheet:")
            traceback.print_exception(type(e), e, e.__traceback__, file=sys.stderr)
            return await self.bot.edit_message(loading, 'Error: Invalid character sheet.\n' + str(e))
        
        self.active_characters = self.bot.db.not_json_get('active_characters', {})
        self.active_characters[ctx.message.author.id] = file['filename']
        self.bot.db.not_json_set('active_characters', self.active_characters)
        
        embed = sheet['embed']
        await self.bot.say(embed=embed)
        
        user_characters = self.bot.db.not_json_get(ctx.message.author.id + '.characters', {})
        user_characters[file['filename']] = sheet['sheet']
        self.bot.db.not_json_set(ctx.message.author.id + '.characters', user_characters)
        
    @commands.command(pass_context=True)
    async def gsheet(self, ctx, url:str):
        """Loads a character sheet from [this Google sheet](https://docs.google.com/spreadsheets/d/1etrBJ0qCDXACovYHUM4XvjE0erndThwRLcUQzX6ts8w/edit?usp=sharing), resetting all settings. The sheet must be shared with Avrae (see specific command help) for this to work.
        Avrae's google account is `avrae-320@avrae-bot.iam.gserviceaccount.com`."""
        
        loading = await self.bot.say('Loading character data from Google...')
        url = extract_id_from_url(url)
        parser = GoogleSheet(url)
        
        try:
            character = await parser.get_character()
        except SpreadsheetNotFound:
            return await self.bot.edit_message(loading, "Invalid character sheet. Make sure you've shared it with me at `avrae-320@avrae-bot.iam.gserviceaccount.com`!")
        try:
            await self.bot.edit_message(loading, 'Loaded and saved data for {}!'.format(character.acell("C6").value))
        except TypeError:
            return await self.bot.edit_message(loading, 'Invalid character sheet. Make sure you have shared the sheet so that anyone with the link can view.')
        
        try:
            sheet = await parser.get_sheet()
        except Exception as e:
            traceback.print_exception(type(e), e, e.__traceback__, file=sys.stderr)
            return await self.bot.edit_message(loading, 'Error: Invalid character sheet.\n' + str(e))
        
        self.active_characters = self.bot.db.not_json_get('active_characters', {})
        self.active_characters[ctx.message.author.id] = url
        self.bot.db.not_json_set('active_characters', self.active_characters)
        user_characters = self.bot.db.not_json_get(ctx.message.author.id + '.characters', {})
        user_characters[url] = sheet['sheet']
        self.bot.db.not_json_set(ctx.message.author.id + '.characters', user_characters)
        
        embed = sheet['embed']
        try:
            await self.bot.say(embed=embed)
        except:
            await self.bot.say("...something went wrong generating your character sheet. Don't worry, your character has been saved. This is usually due to an invalid image.")

    
    
        