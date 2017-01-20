'''
Created on Jan 19, 2017

@author: andrew
'''
import asyncio
from math import floor
import random
import re

from DDPClient import DDPClient
import discord
import numexpr


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
    levels = get_levels(character)
    hp = calculate_stat(character, 'hitPoints')
    attacks = get_attacks(character)
    
    sheet = {'stats': stats,
             'levels': levels,
             'hp': hp,
             'attacks': attacks}
    
    embed.title = stats['name']
    embed.set_thumbnail(url=stats['image'])
    embed.add_field(name="HP/Level", value="**HP:** {}\nLevel {}".format(hp, levels['level']))
    embed.add_field(name="Stats", value="**STR:** {strength} ({strengthMod:+}) " \
                                        "**DEX:** {dexterity} ({dexterityMod:+}) " \
                                        "**CON:** {constitution} ({constitutionMod:+}) " \
                                        "**INT:** {intelligence} ({intelligenceMod:+}) " \
                                        "**WIS:** {wisdom} ({wisdomMod:+}) " \
                                        "**CHA:** {charisma} ({charismaMod:+})".format(**stats))
    embed.add_field(name="Attacks", value='\n'.join("**{name}:** {attackBonus} To Hit, {damage} damage.".format(**a)
                                                    for a in attacks))
    
    return {'embed': embed, 'sheet': sheet}
    
def get_stat(character, stat):
    """Returns the stat value."""
    effects = character.get('effects')
    base = 0
    add = 0
    mult = 1
    maxV = None
    minV = None
    for effect in effects:
        if effect.get('stat') == stat and effect.get('enabled', True) and not effect.get('removed', False):
            operation = effect.get('operation', 'base')
            value = int(effect.get('value', 0))
            if operation == 'base' and value > base:
                base = value
            elif operation == 'add':
                add += value
            elif operation == 'mul' and value > mult:
                mult = value
            elif operation == 'min':
                minV = value if minV is None else value if value < minV else minV
            elif operation == 'max':
                maxV = value if maxV is None else value if value > maxV else maxV
    out = (base * mult) + add
    if minV is not None:
        out = max(out, minV)
    if maxV is not None:
        out = min(out, maxV)
    return out
    
def get_stats(character):
    """Returns a dict of stats."""
    stats = {"name":"", "image":"",
             "strength":0, "dexterity":0, "constitution":0, "wisdom":0, "intelligence":0, "charisma":0,
             "strengthMod":0, "dexterityMod":0, "constitutionMod":0, "wisdomMod":0, "intelligenceMod":0, "charismaMod":0,
             "proficiencyBonus":0}
    stats['name'] = character.get('characters')[0].get('name')
    stats['image'] = character.get('characters')[0].get('picture')
    stats['proficiencyBonus'] = floor(get_levels(character)['level'] / 4 + 1.75)
    
    for stat in ('strength', 'dexterity', 'constitution', 'wisdom', 'intelligence', 'charisma'):
        stats[stat] = get_stat(character, stat)
        stats[stat+'Mod'] = floor((int(stats[stat])-10)/2)
    
    return stats
        
def get_levels(character):
    """Returns a dict with the character's level and class levels."""
    levels = {"level":0}
    for level in character.get('classes'):
        if level.get('removed', False): continue
        levels['level'] += level.get('level')
        if levels.get(level.get('name')+'Level') is None:
            levels[level.get('name')+'Level'] = level.get('level')
        else:
            levels[level.get('name')+'Level'] += level.get('level')
    return levels
        
def calculate_stat(character, stat):
    """Calculates and returns the stat value."""
    replacements = get_stats(character)
    replacements.update(get_levels(character))
    effects = character.get('effects')
    base = 0
    add = 0
    mult = 1
    maxV = None
    minV = None
    for effect in effects:
        if effect.get('stat') == stat and effect.get('enabled', True) and not effect.get('removed', False):
            operation = effect.get('operation', 'base')
            if effect.get('value') is not None:
                value = effect.get('value')
            else:
                calculation = effect.get('calculation', '').replace('{', '').replace('}', '')
                if calculation == '': continue
                value = numexpr.evaluate(calculation, local_dict=replacements)
            if operation == 'base' and value > base:
                base = value
            elif operation == 'add':
                add += value
            elif operation == 'mul' and value > mult:
                mult = value
            elif operation == 'min':
                minV = value if minV is None else value if value < minV else minV
            elif operation == 'max':
                maxV = value if maxV is None else value if value > maxV else maxV
    out = (base * mult) + add
    if minV is not None:
        out = max(out, minV)
    if maxV is not None:
        out = min(out, maxV)
    return out

def get_attack(character, atkIn):
    """Calculates and returns a dict."""
    replacements = get_stats(character)
    replacements.update(get_levels(character))
    attack = {'attackBonus': '0', 'damage':'0', 'name': atkIn.get('name'), 'details': atkIn.get('details')}
    
    attackBonus = re.split('([-+*/^().<>=])', atkIn.get('attackBonus', '').replace('{', '').replace('}', ''))
    attack['attackBonus'] = ''.join(str(replacements.get(word, word) for word in attackBonus))
    
    damage = re.split('([-+*/^().<>=])', atkIn.get('damage', '').replace('{', '').replace('}', ''))
    attack['damage'] = ''.join(str(replacements.get(word, word) for word in damage)) + '[{}]'.format(atkIn.get('damageType'))
    
    return attack
    
def get_attacks(character):
    """Returns a list of dicts of all of the character's attacks."""
    attacks = []
    for attack in character.get('attacks'):
        if attack.get('enabled') and not attack.get('removed'):
            attacks.append(get_attack(character, attack))
    return attacks
        
        
        