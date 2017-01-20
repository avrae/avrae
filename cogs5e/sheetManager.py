'''
Created on Jan 19, 2017

@author: andrew
'''
import asyncio
from datetime import datetime
import json

from discord.ext import commands

from cogs5e.dicecloud import get_character, get_sheet


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
        def fix_json(o):
            if isinstance(o, datetime):
                return o.timestamp()
            return json.JSONEncoder.default(o)
        jsonData = json.dumps(user_characters, default=fix_json) #bah
        self.bot.db.set(ctx.message.author.id + '.characters', jsonData)
        
        embed = get_sheet(character)
        await self.bot.say(embed=embed)