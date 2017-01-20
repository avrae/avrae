'''
Created on Jan 19, 2017

@author: andrew
'''
import asyncio
import json

from DDPClient import DDPClient
from discord.ext import commands

from cogs5e.dicecloud import get_character


class SheetManager:
    """Commands to import a character sheet from Dicecloud (https://dicecloud.com). Currently in Beta."""
    
    def __init__(self, bot):
        self.bot = bot
        
    @commands.command(pass_context=True)
    async def dicecloud(self, ctx, url:str):
        if 'dicecloud.com' in url:
            url = url.split('/character/')[-1].split('/')[0]
        
        loading = await self.bot.say('Loading character data from Dicecloud...')
        character = await get_character(url)
        await self.bot.edit_message(loading, 'Loaded and saved data for {}!'.format(character.get('characters')[0].get('name')))
        
        user_characters = self.bot.db.not_json_get(ctx.message.author.id + '.characters', {})
        user_characters[url] = character
        jsonData = json.dumps(user_characters, skipkeys=True) #bah
        self.bot.db.set(ctx.message.author.id + '.characters', jsonData)
        
        embed = self.get_sheet(character)
        await self.bot.say(embed=embed)