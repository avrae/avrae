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
        await asyncio.sleep(1)
    client.subscribe('singleCharacter', [url])
    def update_character(collection, _id, fields):
        if character.get(collection) is None:
            character[collection] = []
        fields['id'] = _id
        character.get(collection).append(fields)
    client.on('added', update_character)
    await asyncio.sleep(10)
    client.close()
    return character
        
def get_sheet(character):
    """Returns an Embed object with character sheet data."""
    embed = discord.Embed()
    embed.colour = random.randint(0, 0xffffff)
    
    try:
        stats = get_stats(character)
        levels = get_levels(character)
        hp = calculate_stat(character, 'hitPoints')
        attacks = get_attacks(character)
        skills = get_skills(character)
    except:
        raise
    
    sheet = {'stats': stats,
             'levels': levels,
             'hp': int(hp),
             'attacks': attacks,
             'skills': skills,
             'saves': {}}
    
    for key, skill in skills.items():
        if 'Save' in key:
            sheet['saves'][key] = skills[key]
    
    embed.title = stats['name']
    embed.set_thumbnail(url=stats['image'])
    embed.add_field(name="HP/Level", value="**HP:** {}\nLevel {}".format(hp, levels['level']), inline=False)
    embed.add_field(name="Stats", value="**STR:** {strength} ({strengthMod:+})\n" \
                                        "**DEX:** {dexterity} ({dexterityMod:+})\n" \
                                        "**CON:** {constitution} ({constitutionMod:+})\n" \
                                        "**INT:** {intelligence} ({intelligenceMod:+})\n" \
                                        "**WIS:** {wisdom} ({wisdomMod:+})\n" \
                                        "**CHA:** {charisma} ({charismaMod:+})".format(**stats))
    embed.add_field(name="Saves", value="**STR:** {strengthSave:+}\n" \
                                        "**DEX:** {dexteritySave:+}\n" \
                                        "**CON:** {constitutionSave:+}\n" \
                                        "**INT:** {intelligenceSave:+}\n" \
                                        "**WIS:** {wisdomSave:+}\n" \
                                        "**CHA:** {charismaSave:+}".format(**skills))
    
    skillsStr = ''
    tempSkills = {}
    for skill, mod in sorted(skills.items()):
        if 'Save' not in skill:
            skillsStr += '**{}**: {:+}\n'.format(re.sub(r'((?<=[a-z])[A-Z]|(?<!\A)[A-Z](?=[a-z]))', r' \1', skill), mod)
            tempSkills[skill] = mod
    sheet['skills'] = tempSkills
            
    embed.add_field(name="Skills", value=skillsStr.title())
    
    tempAttacks = []
    for a in attacks:
        if a['attackBonus'] is not None:
            try:
                bonus = numexpr.evaluate(a['attackBonus'])
            except:
                bonus = a['attackBonus']
            tempAttacks.append("**{0}:** +{1} To Hit, {2} damage.".format(a['name'],
                                                                          bonus,
                                                                          a['damage'] if a['damage'] is not None else 'no'))
        else:
            tempAttacks.append("**{0}:** {1} damage.".format(a['name'],
                                                             a['damage'] if a['damage'] is not None else 'no'))
    if tempAttacks == []:
        tempAttacks = ['No attacks.']
    embed.add_field(name="Attacks", value='\n'.join(tempAttacks))
    
    return {'embed': embed, 'sheet': sheet}
    
def get_stat(character, stat, base=0):
    """Returns the stat value."""
    effects = character.get('effects')
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
    stats = {"name":"", "image":"", "description":"",
             "strength":0, "dexterity":0, "constitution":0, "wisdom":0, "intelligence":0, "charisma":0,
             "strengthMod":0, "dexterityMod":0, "constitutionMod":0, "wisdomMod":0, "intelligenceMod":0, "charismaMod":0,
             "proficiencyBonus":0}
    stats['name'] = character.get('characters')[0].get('name')
    stats['description'] = character.get('characters')[0].get('description')
    stats['image'] = character.get('characters')[0].get('picture')
    profByLevel = floor(get_levels(character)['level'] / 4 + 1.75)
    stats['proficiencyBonus'] = profByLevel + get_stat(character, 'proficiencyBonus', base=0)
    
    for stat in ('strength', 'dexterity', 'constitution', 'wisdom', 'intelligence', 'charisma'):
        stats[stat] = get_stat(character, stat)
        stats[stat + 'Mod'] = floor((int(stats[stat]) - 10) / 2)
    
    return stats
        
def get_levels(character):
    """Returns a dict with the character's level and class levels."""
    levels = {"level":0}
    for level in character.get('classes'):
        if level.get('removed', False): continue
        levels['level'] += level.get('level')
        if levels.get(level.get('name') + 'Level') is None:
            levels[level.get('name') + 'Level'] = level.get('level')
        else:
            levels[level.get('name') + 'Level'] += level.get('level')
    return levels
        
def calculate_stat(character, stat, base=0):
    """Calculates and returns the stat value."""
    replacements = get_stats(character)
    replacements.update(get_levels(character))
    effects = character.get('effects')
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
                try:
                    value = numexpr.evaluate(calculation, local_dict=replacements)
                except SyntaxError:
                    continue
                except KeyError:
                    raise
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
    
    attackBonus = re.split('([-+*/^().<>= ])', atkIn.get('attackBonus', '').replace('{', '').replace('}', ''))
    attack['attackBonus'] = ''.join(str(replacements.get(word, word)) for word in attackBonus)
    if attack['attackBonus'] == '':
        attack['attackBonus'] = None
    
    damage = re.split('([-+*/^().<>= ])', atkIn.get('damage', '').replace('{', '').replace('}', ''))
    attack['damage'] = ''.join(str(replacements.get(word, word)) for word in damage) + ' [{}]'.format(atkIn.get('damageType'))
    if ''.join(str(replacements.get(word, word)) for word in damage) == '':
        attack['damage'] = None
    
    return attack
    
def get_attacks(character):
    """Returns a list of dicts of all of the character's attacks."""
    attacks = []
    for attack in character.get('attacks', []):
        if attack.get('enabled') and not attack.get('removed'):
            attacks.append(get_attack(character, attack))
    return attacks
        
def get_skills(character):
    """Returns a dict of all the character's skills."""
    stats = get_stats(character)
    skillslist = ['acrobatics', 'animalHandling',
                  'arcana', 'athletics',
                  'charismaSave', 'constitutionSave',
                  'deception', 'dexteritySave',
                  'history', 'initiative',
                  'insight', 'intelligenceSave',
                  'intimidation', 'investigation',
                  'medicine', 'nature',
                  'perception', 'performance',
                  'persuasion', 'religion',
                  'sleightOfHand', 'stealth',
                  'strengthSave', 'survival',
                  'wisdomSave']
    skills = {}
    profs = {}
    for skill in skillslist:
        skills[skill] = stats.get(character.get('characters', [])[0].get(skill, {}).get('ability') + 'Mod', 0)
    for prof in character.get('proficiencies'):
        if prof.get('enabled', False) and not prof.get('removed', False):
            profs[prof.get('name')] = prof.get('value') \
                                      if prof.get('value') > profs.get(prof.get('name', 'None'), 0) \
                                      else profs[prof.get('name')]
        
    for skill in skills:
        skills[skill] = floor(skills[skill] + stats.get('proficiencyBonus') * profs.get(skill, 0))
        skills[skill] = int(calculate_stat(character, skill, base=skills[skill]))
        
    for stat in ('strength', 'dexterity', 'constitution', 'wisdom', 'intelligence', 'charisma'):
        skills[stat] = stats.get(stat + 'Mod')
    
    return skills
    
        
        
