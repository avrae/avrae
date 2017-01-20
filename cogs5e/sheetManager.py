'''
Created on Jan 19, 2017

@author: andrew
'''
import asyncio
from datetime import datetime
import json
import re

from discord.ext import commands

from cogs5e.dice import roll
from cogs5e.dicecloud import get_character, get_sheet


class SheetManager:
    """Commands to import a character sheet from Dicecloud (https://dicecloud.com). Currently in Beta."""
    
    def __init__(self, bot):
        self.bot = bot
        self.active_characters = bot.db.not_json_get('active_characters', {})
        
    @commands.command(pass_context=True, aliases=['a'])
    async def attack(self, ctx, atk_name:str, *, args:str=''):
        """Rolls an attack for the current active character."""
        user_characters = self.bot.db.not_json_get(ctx.message.author.id + '.characters', {})
        character = user_characters[self.active_characters[ctx.message.author.id]]
        attacks = character.get('attacks')
        try:
            attack = next(a for a in attacks if atk_name == a.get('name').lower())
        except StopIteration:
            try:
                attack = next(a for a in attacks if atk_name in a.get('name').lower())
            except StopIteration:
                return await self.bot.say('No attack with that name found.')
        
        adv = 0
        if re.search('(^|\s+)(adv|dis)(\s+|$)', args) is not None:
            adv = 1 if re.search('(^|\s+)adv(\s+|$)', args) is not None else -1
            args = re.sub('(adv|dis)(\s+|$)', '', args)
        
        out = '***{} attacks with a {}!***\n'.format(character.get('stats').get('name'), attack.get('name'))
        out += roll('1d20+' + attack.get('attackBonus'), adv=adv, rollFor='To Hit').result + '\n'
        out += roll(attack.get('damage'), rollFor='Damage').result + '\n'
        out += '**Effect:** ' + attack.get('details') if not attack.get('details', '') == '' else ''
        
        await self.bot.say(out)
        
        
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
        