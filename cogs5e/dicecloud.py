'''
Created on Jan 19, 2017

@author: andrew
'''
import asyncio
from math import floor
import random

from DDPClient import DDPClient
import discord


async def get_character(url):
    character = {}
    client = DDPClient('ws://dicecloud.com/websocket', auto_reconnect=False)
    client.is_connected = False
    client.connect()
    def connected():
        client.is_connected = True
    client.on('connected', connected)
    while not client.is_connected:
        asyncio.sleep(1)
    client.subscribe('singleCharacter', [url])
    def update_character(collection, _id, fields):
        if character.get(collection) is None:
            character[collection] = []
        character.get(collection).append(fields)
    client.on('added', update_character)
    await asyncio.sleep(10)
    client.close()
    return character
        
def get_sheet(character):
    """Returns an Embed object with character sheet data."""
    embed = discord.Embed()
    embed.colour = random.randint(0, 0xffffff)
    stats = get_stats(character)
    embed.title = stats['name']
    embed.set_thumbnail(url=stats['image'])
    embed.add_field(name="Stats", value="**STR:** {strength} ({strengthMod:+}) " \
                                        "**DEX:** {dexterity} ({dexterityMod:+}) " \
                                        "**CON:** {consitution} ({constitutionMod:+}) " \
                                        "**INT:** {intelligence} ({intelligenceMod:+}) " \
                                        "**WIS:** {wisdom} ({wisdomMod:+}) " \
                                        "**CHA:** {charisma} ({charismaMod:+})".format(**stats))
    
    return embed
    
def get_stat(character, stat):
    """Returns the stat value."""
    effects = character.get('effects')
    base = 0
    add = 0
    mult = 1
    maxV = None
    minV = None
    for effect in effects:
        if effect.get('stat') is stat:
            operation = effect.get('operation', 'base')
            value = int(effect.get('value', 0))
            if operation is 'base' and value > base:
                base = value
            elif operation is 'add' and value > add:
                add = value
            elif operation is 'mul' and value > mult:
                mult = value
            elif operation is 'min' and value < min:
                minV = value
            elif operation is 'max' and value > max:
                maxV = value
    out = (base * mult) + add
    if min is not None:
        out = max(out, minV)
    if max is not None:
        out = min(out, maxV)
    return out
    
def get_stats(character):
    """Returns a dict of stats."""
    stats = {"name":"", "image":"",
             "strength":0, "dexterity":0, "constitution":0, "wisdom":0, "intelligence":0, "charisma":0,
             "strengthMod":0, "dexterityMod":0, "constitutionMod":0, "wisdomMod":0, "intelligenceMod":0, "charismaMod":0}
    stats['name'] = character.get('characters')[0].get('name')
    stats['image'] = character.get('characters')[0].get('picture')
    
    for stat in ('strength', 'dexterity', 'constitution', 'wisdom', 'intelligence', 'charisma'):
        stats[stat] = get_stat(character, stat)
        stats[stat+'Mod'] = floor((int(stats[stat])-10)/2)
    
    return stats
        
        
        
        
        
        
        
        