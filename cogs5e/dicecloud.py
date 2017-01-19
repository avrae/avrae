'''
Created on Jan 19, 2017

@author: andrew
'''
import asyncio

from DDPClient import DDPClient
from discord.ext import commands


class Dicecloud:
    """Commands to import a character sheet from Dicecloud (https://dicecloud.com). Currently in Beta."""
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command(pass_context=True)
    async def import_sheet(self, ctx, url:str):
        character = {}
        client = DDPClient('ws://dicecloud.com/websocket')
        client.is_connected = False
        client.connect()
        def connected():
            client.is_connected = True
        client.on('connected', connected)
        while not client.is_connected:
            asyncio.sleep(1)
        sub_id = client.subscribe('singleCharacter', [url])
        def update_character(collection, _id, fields):
            if character.get(collection) is None:
                character[collection] = []
            character.get(collection).append(fields)
        client.on('added', update_character)
        loading = await self.bot.say('Loading character data from Dicecloud...')
        await asyncio.sleep(10)
        await self.bot.edit_message(loading, 'Loaded data for {}!'.format(character.get('characters')[0].get('name')))
        client.close()