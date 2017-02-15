'''
Created on Jan 19, 2017

@author: andrew
'''
import asyncio
from datetime import datetime
import json
import random
import re
import shlex
import sys
import traceback

import discord
from discord.ext import commands

from cogs5e.dice import roll
from cogs5e.sheets.dicecloud import DicecloudParser
from utils.functions import list_get, embed_trim, get_positivity
from cogs5e.sheets.pdfsheet import PDFSheetParser


class SheetManager:
    """Commands to import a character sheet from Dicecloud (https://dicecloud.com) or the fillable Wizards character PDF. Currently in Beta."""
    
    def __init__(self, bot):
        self.bot = bot
        self.active_characters = bot.db.not_json_get('active_characters', {})
        
    def parse_args(self, args):
        out = {}
        index = 0
        for a in args:
            if a == '-b' or a == '-d':
                if out.get(a.replace('-', '')) is None: out[a.replace('-', '')] = list_get(index + 1, None, args)
                else: out[a.replace('-', '')] += ' + ' + list_get(index + 1, None, args)
            elif a.startswith('-'):
                out[a.replace('-', '')] = list_get(index + 1, None, args)
            else:
                out[a] = True
            index += 1
        return out
        
    @commands.command(pass_context=True, aliases=['a'])
    async def attack(self, ctx, atk_name:str, *, args:str=''):
        """Rolls an attack for the current active character.
        Valid Arguments: adv/dis
                         -ac [target ac]
                         -b [to hit bonus]
                         -d [damage bonus]
                         -rr [times to reroll]
                         -t [target]
                         -phrase [flavor text]
                         crit (automatically crit)"""
        user_characters = self.bot.db.not_json_get(ctx.message.author.id + '.characters', {})
        active_character = self.active_characters.get(ctx.message.author.id)
        if active_character is None:
            return await self.bot.say('You have no character active.')
        character = user_characters[active_character]
        attacks = character.get('attacks')
        try:
            attack = next(a for a in attacks if atk_name.lower() == a.get('name').lower())
        except StopIteration:
            try:
                attack = next(a for a in attacks if atk_name.lower() in a.get('name').lower())
            except StopIteration:
                return await self.bot.say('No attack with that name found.')
        
        embed = discord.Embed()
        embed.colour = random.randint(0, 0xffffff) if character.get('settings', {}).get('color') is None else character.get('settings', {}).get('color')
        
        args = shlex.split(args)
        total_damage = 0
        args = self.parse_args(args)
            
        if args.get('phrase') is not None:
            embed.description = '*' + args.get('phrase') + '*'
        else:
            embed.description = '~~' + ' '*500 + '~~'
            
        if args.get('t') is not None:
            embed.title = '{} attacks with a {} at {}!'.format(character.get('stats').get('name'), attack.get('name'), args.get('t'))
        else:
            embed.title = '{} attacks with a {}!'.format(character.get('stats').get('name'), attack.get('name'))
        
        for arg in ('rr', 'ac'):
            try:
                args[arg] = int(args.get(arg, None))
            except (ValueError, TypeError):
                args[arg] = None
        args['adv'] = 0 if args.get('adv', False) and args.get('dis', False) else 1 if args.get('adv', False) else -1 if args.get('dis', False) else 0
        args['crit'] = 1 if args.get('crit', False) else None
        for r in range(args.get('rr', 1) or 1):
            if attack.get('attackBonus') is not None:
                if args.get('b') is not None:
                    toHit = roll('1d20+' + attack.get('attackBonus') + '+' + args.get('b'), adv=args.get('adv'), rollFor='To Hit', inline=True, show_blurbs=False)
                else:
                    toHit = roll('1d20+' + attack.get('attackBonus'), adv=args.get('adv'), rollFor='To Hit', inline=True, show_blurbs=False)
    
                out = ''
                out += toHit.result + '\n'
                itercrit = toHit.crit if not args.get('crit') else args.get('crit', 0)
                if args.get('ac') is not None:
                    if toHit.total < args.get('ac') and itercrit == 0:
                        itercrit = 2 # miss!
                
                if attack.get('damage') is not None:
                    if args.get('d') is not None:
                        damage = attack.get('damage') + '+' + args.get('d')
                    else:
                        damage = attack.get('damage')
                    
                    if itercrit == 1:
                        dmgroll = roll(damage, rollFor='Damage (CRIT!)', inline=True, double=True, show_blurbs=False)
                        out += dmgroll.result + '\n'
                        total_damage += dmgroll.total
                    elif itercrit == 2:
                        out += '**Miss!**\n'
                    else:
                        dmgroll = roll(damage, rollFor='Damage', inline=True, show_blurbs=False)
                        out += dmgroll.result + '\n'
                        total_damage += dmgroll.total
            else:
                out = ''
                if attack.get('damage') is not None:
                    if args.get('d') is not None:
                        damage = attack.get('damage') + '+' + args.get('d')
                    else:
                        damage = attack.get('damage')
                    
                    dmgroll = roll(damage, rollFor='Damage', inline=True, show_blurbs=False)
                    out += dmgroll.result + '\n'
                    total_damage += dmgroll.total
            
            if out is not '':
                if (args.get('rr', 1) or 1) > 1:
                    embed.add_field(name='Attack {}'.format(r+1), value=out, inline=False)
                else:
                    embed.add_field(name='Attack', value=out, inline=False)
            
        if (args.get('rr', 1) or 1) > 1 and attack.get('damage') is not None:
            embed.add_field(name='Total Damage', value=str(total_damage))
        
        if attack.get('details') is not None:
            embed.add_field(name='Effect', value=(attack.get('details', '')))
        
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
              -phrase [flavor text]"""
        user_characters = self.bot.db.not_json_get(ctx.message.author.id + '.characters', {})
        active_character = self.active_characters.get(ctx.message.author.id)
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
        args = self.parse_args(args)
        adv = 0 if args.get('adv', False) and args.get('dis', False) else 1 if args.get('adv', False) else -1 if args.get('dis', False) else 0
        b = args.get('b', None)
        phrase = args.get('phrase', None)
        
        if b is not None:
            save_roll = roll('1d20' + '{:+}'.format(saves[save]) + '+' + b, adv=adv, inline=True)
        else:
            save_roll = roll('1d20' + '{:+}'.format(saves[save]), adv=adv, inline=True)
            
        embed.title = '{} makes a {}!'.format(character.get('stats', {}).get('name'),
                                              re.sub(r'((?<=[a-z])[A-Z]|(?<!\A)[A-Z](?=[a-z]))', r' \1', save).title())
            
        embed.description = save_roll.skeleton + ('\n*' + phrase + '*' if phrase is not None else '')
        
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
              -phrase [flavor text]"""
        user_characters = self.bot.db.not_json_get(ctx.message.author.id + '.characters', {})
        active_character = self.active_characters.get(ctx.message.author.id)
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
        args = self.parse_args(args)
        adv = 0 if args.get('adv', False) and args.get('dis', False) else 1 if args.get('adv', False) else -1 if args.get('dis', False) else 0
        b = args.get('b', None)
        phrase = args.get('phrase', None)
        
        if b is not None:
            check_roll = roll('1d20' + '{:+}'.format(skills[skill]) + '+' + b, adv=adv, inline=True)
        else:
            check_roll = roll('1d20' + '{:+}'.format(skills[skill]), adv=adv, inline=True)
        
        embed.title = '{} makes a {} check!'.format(character.get('stats', {}).get('name'),
                                                    re.sub(r'((?<=[a-z])[A-Z]|(?<!\A)[A-Z](?=[a-z]))', r' \1', skill).title())
        embed.description = check_roll.skeleton + ('\n*' + phrase + '*' if phrase is not None else '')
        
        await self.bot.say(embed=embed)
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass
            
    @commands.command(pass_context=True)
    async def desc(self, ctx):
        """Prints a description of your currently active character."""
        user_characters = self.bot.db.not_json_get(ctx.message.author.id + '.characters', {})
        active_character = self.active_characters.get(ctx.message.author.id)
        if active_character is None:
            return await self.bot.say('You have no character active.')
        character = user_characters[active_character]
        stats = character.get('stats')
        image = stats.get('image', '')
        desc = stats.get('description', 'No description available.')
        if len(desc) > 1024:
            desc = desc[:1020] + '...'
        elif len(desc) < 2:
            desc = 'No description available.'
        
        embed = discord.Embed()
        embed.add_field(name=stats.get('name'), value=desc)
        embed.colour = random.randint(0, 0xffffff) if character.get('settings', {}).get('color') is None else character.get('settings', {}).get('color')
        embed.set_thumbnail(url=image)
        
        await self.bot.say(embed=embed)
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass
            
    @commands.command(pass_context=True)
    async def character(self, ctx, name:str=None, *, args:str=''):
        """Switches the active character.
        Breaks for characters created before Jan. 20, 2017.
        Valid arguments:
        `delete` - deletes a character."""
        user_characters = self.bot.db.not_json_get(ctx.message.author.id + '.characters', None)
        active_character = self.bot.db.not_json_get('active_characters', {}).get(ctx.message.author.id)
        if user_characters is None:
            return await self.bot.say('You have no characters.')
        
        if name is None:
            return await self.bot.say('Currently active: {}'.format(user_characters[active_character].get('stats', {}).get('name')), delete_after=20)
        
        if name == 'list':
            return await self.bot.say('Your characters:\n{}'.format(', '.join([user_characters[c].get('stats', {}).get('name', '') for c in user_characters])))
        args = shlex.split(args)
        
        char_url = None
        for url, character in user_characters.items():
            if character.get('stats', {}).get('name', '').lower() == name.lower():
                char_url = url
                name = character.get('stats').get('name')
                break
            
            if name.lower() in character.get('stats', {}).get('name', '').lower():
                char_url = url
                name = character.get('stats').get('name')
        
        if char_url is None:
            return await self.bot.say('Character not found.')
        
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
    async def update(self, ctx):
        """Updates the current character sheet, preserving all settings."""
        active_character = self.active_characters.get(ctx.message.author.id)
        if active_character is None:
            return await self.bot.say('You have no character active.')
        url = active_character
        parser = DicecloudParser()
        loading = await self.bot.say('Updating character data from Dicecloud...')
        character = await parser.get_character(url)
        try:
            await self.bot.edit_message(loading, 'Updated and saved data for {}!'.format(character.get('characters')[0].get('name')))
        except TypeError:
            return await self.bot.edit_message(loading, 'Invalid character sheet. Make sure you have shared the sheet so that anyone with the link can view.')
        
        try:
            sheet = parser.get_sheet(character)
        except Exception as e:
            return await self.bot.edit_message(loading, 'Error: Invalid character sheet.\n' + str(e))

        embed = sheet['embed']
        
        user_characters = self.bot.db.not_json_get(ctx.message.author.id + '.characters', {})
        sheet = sheet['sheet']
        sheet['settings'] = user_characters[url].get('settings', {})
        user_characters[url] = sheet
        embed.colour = embed.colour if sheet.get('settings', {}).get('color') is None else sheet.get('settings', {}).get('color')
        self.bot.db.not_json_set(ctx.message.author.id + '.characters', user_characters)
        await self.bot.say(embed=embed)
    
    @commands.command(pass_context=True)
    async def csettings(self, ctx, *, args):
        """Updates personalization settings for the currently active character.
        Valid Arguments:
        `color <hex color>` - Colors all embeds this color."""
        user_characters = self.bot.db.not_json_get(ctx.message.author.id + '.characters', {})
        active_character = self.active_characters.get(ctx.message.author.id)
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
            index += 1
                    
        user_characters[active_character] = character
        self.bot.db.not_json_set(ctx.message.author.id + '.characters', user_characters)
        await self.bot.say(out)
    
    @commands.command(pass_context=True)
    async def dicecloud(self, ctx, url:str):
        """Loads a character sheet from Dicecloud, resetting all settings."""
        if 'dicecloud.com' in url:
            url = url.split('/character/')[-1].split('/')[0]
        
        loading = await self.bot.say('Loading character data from Dicecloud...')
        parser = DicecloudParser()
        character = await parser.get_character(url)
        try:
            await self.bot.edit_message(loading, 'Loaded and saved data for {}!'.format(character.get('characters')[0].get('name')))
        except TypeError:
            return await self.bot.edit_message(loading, 'Invalid character sheet. Make sure you have shared the sheet so that anyone with the link can view.')
        
        try:
            sheet = parser.get_sheet(character)
        except Exception as e:
            traceback.print_exception(type(e), e, e.__traceback__, file=sys.stderr)
            return await self.bot.edit_message(loading, 'Error: Invalid character sheet.\n' + str(e))
        
        self.active_characters[ctx.message.author.id] = url
        self.bot.db.not_json_set('active_characters', self.active_characters)
        
        embed = sheet['embed']
        await self.bot.say(embed=embed)
        
        user_characters = self.bot.db.not_json_get(ctx.message.author.id + '.characters', {})
        user_characters[url] = sheet['sheet']
        self.bot.db.not_json_set(ctx.message.author.id + '.characters', user_characters)
        
    @commands.command(pass_context=True, hidden=True)
    async def pdfsheet(self, ctx):
        """Loads a character sheet from a Wizards PDF, resetting all settings."""
        
        if not 0 < len(ctx.message.attachments) < 2:
            return await self.bot.say('You must call this command in the same message you upload the sheet.')
        
        file = ctx.message.attachments[0]
        
        loading = await self.bot.say('Loading character data from PDF...')
        parser = PDFSheetParser()
        character = await parser.get_character(file)
        
        try:
            sheet = parser.get_sheet(character)
            await self.bot.edit_message(loading, 'Loaded and saved data for {}!'.format(sheet['sheet'].get('stats', {}).get('name')))
        except Exception as e:
            print("Error loading PDFChar sheet:")
            traceback.print_exception(type(e), e, e.__traceback__, file=sys.stderr)
            return await self.bot.edit_message(loading, 'Error: Invalid character sheet.\n' + str(e))
        
        self.active_characters[ctx.message.author.id] = file['filename']
        self.bot.db.not_json_set('active_characters', self.active_characters)
        
        embed = sheet['embed']
        await self.bot.say(embed=embed)
        
        user_characters = self.bot.db.not_json_get(ctx.message.author.id + '.characters', {})
        user_characters[file['filename']] = sheet['sheet']
        self.bot.db.not_json_set(ctx.message.author.id + '.characters', user_characters)
        