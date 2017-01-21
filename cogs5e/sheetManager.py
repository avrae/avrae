'''
Created on Jan 19, 2017

@author: andrew
'''
import asyncio
from datetime import datetime
import json
import re
import shlex

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
        Valid Arguments: -t [target]
                         adv/dis"""
        user_characters = self.bot.db.not_json_get(ctx.message.author.id + '.characters', {})
        character = user_characters[self.active_characters[ctx.message.author.id]]
        attacks = character.get('attacks')
        try:
            attack = next(a for a in attacks if atk_name.lower() == a.get('name').lower())
        except StopIteration:
            try:
                attack = next(a for a in attacks if atk_name.lower() in a.get('name').lower())
            except StopIteration:
                return await self.bot.say('No attack with that name found.')
        
        adv = 0
        
        args = shlex.split(args)
        target = None
        if '-t' in args:
            target = list_get(args.index('-t') + 1, None, args)
        
        if 'adv' in args or 'dis' in args:
            adv = 1 if 'adv' in args else -1
            
        toHit = roll('1d20+' + attack.get('attackBonus'), adv=adv, rollFor='To Hit', inline=True)
        
        if target is not None:
            out = '***{} attacks with a {} at {}!***\n'.format(character.get('stats').get('name'), attack.get('name'), target)
        else:
            out = '***{} attacks with a {}!***\n'.format(character.get('stats').get('name'), attack.get('name'))
        out += toHit.result + '\n'
        
        if toHit.crit == 1:
            out += roll(attack.get('damage'), rollFor='Damage', inline=True, double=True).result + '\n'
        elif toHit.crit == 2:
            out += '**Miss!**\n'
        else:
            out += roll(attack.get('damage'), rollFor='Damage', inline=True).result + '\n'
        
        if attack.get('details') is not None:
            out += '**Effect:** ' + attack.get('details', '')
        
        await self.bot.say(out)
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
            if character.get('stats').get('name').lower() == name.lower():
                char_url = url
                name = character.get('stats').get('name')
                break
            
            if name.lower() in character.get('stats').get('name').lower():
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
        