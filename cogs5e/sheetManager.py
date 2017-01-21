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
            
            if rr > 1:
                embed.add_field(name='Attack {}'.format(r+1), value=out, inline=False)
            else:
                embed.add_field(name='Attack', value=out, inline=False)
            
        if rr > 1:
            embed.add_field(name='Total Damage', value=str(total_damage))
        
        if attack.get('details') is not None:
            embed.add_field(name='Effect', value=(attack.get('details', '')))
        
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
            if character.get('stats', {}).get('name').lower() == name.lower():
                char_url = url
                name = character.get('stats').get('name')
                break
            
            if name.lower() in character.get('stats', {}).get('name').lower():
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
        