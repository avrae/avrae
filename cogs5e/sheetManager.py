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

import discord
from discord.ext import commands

from cogs5e.dice import roll
from cogs5e.dicecloud import get_character, get_sheet
from utils.functions import list_get


class SheetManager:
    """Commands to import a character sheet from Dicecloud (https://dicecloud.com). Currently in Beta."""
    
    def __init__(self, bot):
        self.bot = bot
        self.active_characters = bot.db.not_json_get('active_characters', {})
        
    @commands.command(pass_context=True, aliases=['a'])
    async def attack(self, ctx, atk_name:str, *, args:str=''):
        """Rolls an attack for the current active character.
        Valid Arguments: adv/dis
                         -ac [target ac]
                         -b [to hit bonus]
                         -d [damage bonus]
                         -rr [times to reroll]
                         -t [target]
                         crit (automatically crit)"""
        user_characters = self.bot.db.not_json_get(ctx.message.author.id + '.characters', {})
        active_character = self.active_characters.get(ctx.message.author.id)
        if active_character is None:
            return await self.bot.say('You have no characters loaded.')
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
        embed.colour = random.randint(0, 0xffffff)
        embed.description = '~~' + ' '*500 + '~~'
        
        args = shlex.split(args)
        adv = 0
        target = None
        ac = None
        b = None
        d = None
        rr = 1
        crit = 0
        total_damage = 0
        if '-t' in args:
            target = list_get(args.index('-t') + 1, None, args)
        if '-ac' in args:
            try:
                ac = int(list_get(args.index('-ac') + 1, None, args))
            except ValueError:
                pass
        if '-b' in args:
            b = list_get(args.index('-b') + 1, None, args)
        if '-d' in args:
            d = list_get(args.index('-d') + 1, None, args)
        if '-rr' in args:
            try:
                rr = int(list_get(args.index('-rr') + 1, 1, args))
            except ValueError:
                pass
        if 'crit' in args:
            crit = 1
        if 'adv' in args or 'dis' in args:
            adv = 1 if 'adv' in args else -1
            
        if target is not None:
            embed.title = '{} attacks with a {} at {}!'.format(character.get('stats').get('name'), attack.get('name'), target)
        else:
            embed.title = '{} attacks with a {}!'.format(character.get('stats').get('name'), attack.get('name'))
        
        for r in range(rr):
            if attack.get('attackBonus') is not None:
                if b is not None:
                    toHit = roll('1d20+' + attack.get('attackBonus') + '+' + b, adv=adv, rollFor='To Hit', inline=True, show_blurbs=False)
                else:
                    toHit = roll('1d20+' + attack.get('attackBonus'), adv=adv, rollFor='To Hit', inline=True, show_blurbs=False)
    
                out = ''
                out += toHit.result + '\n'
                itercrit = toHit.crit if crit == 0 else crit
                if ac is not None:
                    if toHit.total < ac and itercrit == 0:
                        itercrit = 2 # miss!
                
                if attack.get('damage') is not None:
                    if d is not None:
                        damage = attack.get('damage') + '+' + d
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
                    if d is not None:
                        damage = attack.get('damage') + '+' + d
                    else:
                        damage = attack.get('damage')
                    
                    dmgroll = roll(damage, rollFor='Damage', inline=True, show_blurbs=False)
                    out += dmgroll.result + '\n'
                    total_damage += dmgroll.total
            
            if out is not '':
                if rr > 1:
                    embed.add_field(name='Attack {}'.format(r+1), value=out, inline=False)
                else:
                    embed.add_field(name='Attack', value=out, inline=False)
            
        if rr > 1 and attack.get('damage') is not None:
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
              -b [conditional bonus]"""
        user_characters = self.bot.db.not_json_get(ctx.message.author.id + '.characters', {})
        active_character = self.active_characters.get(ctx.message.author.id)
        if active_character is None:
            return await self.bot.say('You have no characters loaded.')
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
        embed.colour = random.randint(0, 0xffffff)
        
        args = shlex.split(args)
        adv = 0
        b = None
        if '-b' in args:
            b = list_get(args.index('-b') + 1, None, args)
        if 'adv' in args or 'dis' in args:
            adv = 1 if 'adv' in args else -1
        
        if b is not None:
            save_roll = roll('1d20' + '{:+}'.format(saves[save]) + '+' + b, adv=adv, inline=True)
        else:
            save_roll = roll('1d20' + '{:+}'.format(saves[save]), adv=adv, inline=True)
            
        embed.add_field(name='{} makes a {}!'.format(character.get('stats', {}).get('name'),
                                                     re.sub(r'((?<=[a-z])[A-Z]|(?<!\A)[A-Z](?=[a-z]))', r' \1', save).title()),
                        value=save_roll.skeleton)
        
        await self.bot.say(embed=embed)
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass
    
    @commands.command(pass_context=True, aliases=['c'])
    async def check(self, ctx, check, *, args:str=''):
        """Rolls a check for your current active character.
        Args: adv/dis
              -b [conditional bonus]"""
        user_characters = self.bot.db.not_json_get(ctx.message.author.id + '.characters', {})
        active_character = self.active_characters.get(ctx.message.author.id)
        if active_character is None:
            return await self.bot.say('You have no characters loaded.')
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
        embed.colour = random.randint(0, 0xffffff)
        
        args = shlex.split(args)
        adv = 0
        b = None
        if '-b' in args:
            b = list_get(args.index('-b') + 1, None, args)
        if 'adv' in args or 'dis' in args:
            adv = 1 if 'adv' in args else -1
        
        if b is not None:
            check_roll = roll('1d20' + '{:+}'.format(skills[skill]) + '+' + b, adv=adv, inline=True)
        else:
            check_roll = roll('1d20' + '{:+}'.format(skills[skill]), adv=adv, inline=True)
            
        embed.add_field(name='{} makes a {} check!'.format(character.get('stats', {}).get('name'),
                                                     re.sub(r'((?<=[a-z])[A-Z]|(?<!\A)[A-Z](?=[a-z]))', r' \1', skill).title()),
                        value=check_roll.skeleton)
        
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
            return await self.bot.say('You have no characters loaded.')
        character = user_characters[active_character]
        stats = character.get('stats')
        image = stats.get('image', '')
        desc = stats.get('description', 'No description available.')
        
        embed = discord.Embed()
        embed.colour = random.randint(0, 0xffffff)
        embed.add_field(name=stats.get('name'), value=desc)
        embed.set_thumbnail(url=image)
        
        await self.bot.say(embed=embed)
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass
            
    @commands.command(pass_context=True)
    async def character(self, ctx, name:str):
        """Switches the active character.
        Breaks for characters created before Jan. 20, 2017."""
        user_characters = self.bot.db.not_json_get(ctx.message.author.id + '.characters', None)
        if user_characters is None:
            return await self.bot.say('You have no characters.')
        
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
        
        self.active_characters[ctx.message.author.id] = char_url
        self.bot.db.not_json_set('active_characters', self.active_characters)
        
        await self.bot.say("Active character changed to {}.".format(name))
        
    @commands.command(pass_context=True)
    async def dicecloud(self, ctx, url:str):
        """Loads a character sheet from Dicecloud."""
        if 'dicecloud.com' in url:
            url = url.split('/character/')[-1].split('/')[0]
        
        loading = await self.bot.say('Loading character data from Dicecloud...')
        character = await get_character(url)
        try:
            await self.bot.edit_message(loading, 'Loaded and saved data for {}!'.format(character.get('characters')[0].get('name')))
        except TypeError:
            return await self.bot.edit_message(loading, 'Invalid character sheet. Make sure you have shared the sheet so that anyone with the link can view.')
        
        self.active_characters[ctx.message.author.id] = url
        self.bot.db.not_json_set('active_characters', self.active_characters)
        
        sheet = get_sheet(character)
        print(sheet)
        embed = sheet['embed']
        await self.bot.say(embed=embed)
        
        user_characters = self.bot.db.not_json_get(ctx.message.author.id + '.characters', {})
        user_characters[url] = sheet['sheet']
        self.bot.db.not_json_set(ctx.message.author.id + '.characters', user_characters)
        