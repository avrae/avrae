"""
Created on Jan 13, 2017

@author: andrew
"""
import json
import random
from math import floor

import copy

import discord

from utils.functions import discord_trim, fuzzywuzzy_search_all, strict_search, fuzzywuzzy_search_all_3


class Compendium:
    def __init__(self):
        with open('./res/conditions.json', 'r') as f:
            self.conditions = json.load(f)
        with open('./res/rules.json', 'r') as f:
            self.rules = json.load(f)
        with open('./res/feats.json', 'r') as f:
            self.feats = json.load(f)
        with open('./res/races.json', 'r') as f:
            _raw = json.load(f)
            self.rfeats = []
            for race in _raw:
                one_rfeats = race.get('trait', [])
                for i, rfeat in enumerate(one_rfeats):
                    one_rfeats[i]['name'] = "{}: {}".format(race['name'], rfeat['name'])
                self.rfeats += one_rfeats
        with open('./res/classes.json', 'r') as f:
            _raw = json.load(f)
            self.cfeats = []
            for _class in _raw:
                one_clevels = [f for f in _class.get('autolevel', []) if 'feature' in f]
                for i, clevel in enumerate(one_clevels):
                    for cfeat in clevel.get('feature', []):
                        cfeat['name'] = "{}: {}".format(_class['name'], cfeat['name'])
                        self.cfeats.append(cfeat)
        with open('./res/bestiary.json', 'r') as f:
            self.monsters = json.load(f)
        with open('./res/spells.json', 'r') as f:
            self.spells = json.load(f)
        with open('./res/items.json', 'r') as f:
            self.items = json.load(f)
        with open('./res/auto_spells.json', 'r') as f:
            self.autospells = json.load(f)
        with open('./res/backgrounds.json', 'r') as f:
            self.backgrounds = json.load(f)


c = Compendium()

def searchCondition(condition):
    return fuzzywuzzy_search_all_3(c.conditions, 'name', condition)

def getCondition(condition):
    return strict_search(c.conditions, 'name', condition)

def searchRule(rule):
    return fuzzywuzzy_search_all_3(c.rules, 'name', rule)

def getRule(rule):
    return strict_search(c.rules, 'name', rule)

def searchFeat(name):
    return fuzzywuzzy_search_all_3(c.feats, 'name', name)

def getFeat(feat):
    return strict_search(c.feats, 'name', feat)

def searchRacialFeat(name):
    return fuzzywuzzy_search_all_3(c.rfeats, 'name', name)

def getRacialFeat(feat):
    return strict_search(c.rfeats, 'name', feat)

def searchClassFeat(name):
    return fuzzywuzzy_search_all_3(c.cfeats, 'name', name)

def getClassFeat(feat):
    return strict_search(c.cfeats, 'name', feat)

def searchBackground(name):
    return fuzzywuzzy_search_all_3(c.backgrounds, 'name', name)

def getBackground(name):
    return strict_search(c.backgrounds, 'name', name)

# ----- Monster stuff

async def get_selection(results, ctx, pm=False, name_key=None):
    results = results[:10] # sanity
    if name_key:
        names = [r[name_key] for r in results]
    else:
        names = results
    embed = discord.Embed()
    embed.title = "Multiple Matches Found"
    selectStr = " Which one were you looking for? (Type the number, or \"c\" to cancel)\n"
    for i, r in enumerate(names):
        selectStr += f"**[{i+1}]** - {r}\n"
    embed.description = selectStr
    embed.color = random.randint(0, 0xffffff)
    if not pm:
        selectMsg = await ctx.bot.send_message(ctx.message.channel, embed=embed)
    else:
        embed.add_field(name="Instructions", value="Type your response in the channel you called the command. This message was PMed to you to hide the monster name.")
        selectMsg = await ctx.bot.send_message(ctx.message.author, embed=embed)

    def chk(msg):
        valid = [str(v) for v in range(1, len(results) + 1)] + ["c"]
        return msg.content in valid

    m = await ctx.bot.wait_for_message(timeout=30, author=ctx.message.author, channel=ctx.message.channel,
                                       check=chk)

    if not pm: await ctx.bot.delete_message(selectMsg)
    if m is None: return None
    try: await ctx.bot.delete_message(m)
    except: pass
    if m.content == "c": return None
    return results[int(m.content) - 1]

def searchMonster(name):
    return fuzzywuzzy_search_all_3(c.monsters, 'name', name, return_key=True)

async def searchMonsterFull(name, ctx, pm=False):
    result = searchMonster(name)
    if result is None:
        return {'monster': None, 'string': ["Monster does not exist or is misspelled."]}
    strict = result[1]
    results = result[0]
    bot = ctx.bot

    if strict:
        result = results
    else:
        if len(results) == 1:
            result = results[0]
        else:
            result = await get_selection(results, ctx, pm=pm)
            if result is None:
                return {'monster': None, 'string': ["Selection timed out or was cancelled."]}

    result = getMonster(result, visible=True, return_monster=True)
    return result

def getMonster(monstername, visible=True, return_monster=False):
    monsterDesc = []
    monster = strict_search(c.monsters, 'name', monstername)
    monster = copy.copy(monster)
    if monster is None:
        monsterDesc.append("Monster does not exist or is misspelled.")
        if return_monster: return {'monster': None, 'string': monsterDesc}
        return monsterDesc

    def parsesize (size):
        if size == "T": size = "Tiny";
        if size == "S": size = "Small";
        if size == "M": size = "Medium";
        if size == "L": size = "Large";
        if size == "H": size = "Huge";
        if size == "G": size = "Gargantuan";
        return size

    if visible:
        monster['size'] = parsesize(monster['size'])
        monster['type'] = ','.join(monster['type'].split(',')[:-1])
        for stat in ['str', 'dex', 'con', 'wis', 'int', 'cha']:
            monster[stat + 'Str'] = monster[stat] + " ({:+})".format(floor((int(monster[stat]) - 10) / 2))
        if monster.get('skill') is not None:
            monster['skill'] = monster['skill'][0]
        if monster.get('senses') is None:
            monster['senses'] = "passive Perception {}".format(monster['passive'])
        else:
            monster['senses'] = monster.get('senses') + ", passive Perception {}".format(monster['passive'])

        monsterDesc.append("{name}, {size} {type}. {alignment}.\n**AC:** {ac}.\n**HP:** {hp}.\n**Speed:** {speed}\n".format(**monster))
        monsterDesc.append("**STR:** {strStr} **DEX:** {dexStr} **CON:** {conStr} **WIS:** {wisStr} **INT:** {intStr} **CHA:** {chaStr}\n".format(**monster))
        if monster.get('save') is not None:
            monsterDesc.append("**Saving Throws:** {save}\n".format(**monster))
        if monster.get('skill') is not None:
            monsterDesc.append("**Skills:** {skill}\n".format(**monster))
        monsterDesc.append("**Senses:** {senses}.\n".format(**monster))
        if monster.get('vulnerable', '') is not '':
            monsterDesc.append("**Vulnerabilities:** {vulnerable}\n".format(**monster))
        if monster.get('resist', '') is not '':
            monsterDesc.append("**Resistances:** {resist}\n".format(**monster))
        if monster.get('immune', '') is not '':
            monsterDesc.append("**Damage Immunities:** {immune}\n".format(**monster))
        if monster.get('conditionImmune', '') is not '':
            monsterDesc.append("**Condition Immunities:** {conditionImmune}\n".format(**monster))
        if monster.get('languages', '') is not '':
            monsterDesc.append("**Languages:** {languages}\n".format(**monster))
        else:
            monsterDesc.append("**Languages:** --\n".format(**monster))
        monsterDesc.append("**CR:** {cr}\n".format(**monster))

        attacks = []  # setup things
        if "trait" in monster:
            monsterDesc.append("\n**__Special Abilities:__**\n")
            for a in monster["trait"]:
                if isinstance(a['text'], list):
                    a['text'] = '\n'.join(t for t in a['text'] if t is not None)
                monsterDesc.append("**{name}:** {text}\n".format(**a))
                if 'attack' in a:
                    attacks.append(a)
        if "action" in monster:
            monsterDesc.append("\n**__Actions:__**\n")
            for a in monster["action"]:
                if isinstance(a['text'], list):
                    a['text'] = '\n'.join(t for t in a['text'] if t is not None)
                monsterDesc.append("**{name}:** {text}\n".format(**a))
                if 'attack' in a:
                    attacks.append(a)

        if "reaction" in monster:
            monsterDesc.append("\n**__Reactions:__**\n")
            a = monster["reaction"]
            if isinstance(a['text'], list):
                a['text'] = '\n'.join(t for t in a['text'] if t is not None)
            monsterDesc.append("**{name}:** {text}\n".format(**a))
            if 'attack' in a:
                attacks.append(a)

        if "legendary" in monster:
            monsterDesc.append("\n**__Legendary Actions:__**\n")
            for a in monster["legendary"]:
                if isinstance(a['text'], list):
                    a['text'] = '\n'.join(t for t in a['text'] if t is not None)
                if a['name'] is not '':
                    monsterDesc.append("**{name}:** {text}\n".format(**a))
                else:
                    monsterDesc.append("{text}\n".format(**a))
                if 'attack' in a:
                    attacks.append(a)

    else:
        monster['hp'] = int(monster['hp'].split(' (')[0])
        monster['ac'] = int(monster['ac'].split(' (')[0])
        monster['size'] = parsesize(monster['size'])
        monster['type'] = ','.join(monster['type'].split(',')[:-1])
        if monster["hp"] < 10:
            monster["hp"] = "Very Low"
        elif 10 <= monster["hp"] < 50:
            monster["hp"] = "Low"
        elif 50 <= monster["hp"] < 100:
            monster["hp"] = "Medium"
        elif 100 <= monster["hp"] < 200:
            monster["hp"] = "High"
        elif 200 <= monster["hp"] < 400:
            monster["hp"] = "Very High"
        elif 400 <= monster["hp"]:
            monster["hp"] = "Godly"

        if monster["ac"] < 6:
            monster["ac"] = "Very Low"
        elif 6 <= monster["ac"] < 9:
            monster["ac"] = "Low"
        elif 9 <= monster["ac"] < 15:
            monster["ac"] = "Medium"
        elif 15 <= monster["ac"] < 17:
            monster["ac"] = "High"
        elif 17 <= monster["ac"] < 22:
            monster["ac"] = "Very High"
        elif 22 <= monster["ac"]:
            monster["ac"] = "Godly"

        for stat in ["str", "dex", "con", "wis", "int", "cha"]:
            monster[stat] = int(monster[stat])
            if monster[stat] <= 3:
                monster[stat] = "Very Low"
            elif 3 < monster[stat] <= 7:
                monster[stat] = "Low"
            elif 7 < monster[stat] <= 15:
                monster[stat] = "Medium"
            elif 15 < monster[stat] <= 21:
                monster[stat] = "High"
            elif 21 < monster[stat] <= 25:
                monster[stat] = "Very High"
            elif 25 < monster[stat]:
                monster[stat] = "Godly"

        if monster.get("languages"):
            monster["languages"] = len(monster["languages"].split(", "))
        else:
            monster["languages"] = 0

        monsterDesc.append("{name}, {size} {type}.\n" \
        "**AC:** {ac}.\n**HP:** {hp}.\n**Speed:** {speed}\n" \
        "**STR:** {str} **DEX:** {dex} **CON:** {con} **WIS:** {wis} **INT:** {int} **CHA:** {cha}\n" \
        "**Languages:** {languages}\n".format(**monster))

        if "trait" in monster:
            monsterDesc.append("**__Special Abilities:__** " + str(len(monster["trait"])) + "\n")

        if "action" in monster:
            monsterDesc.append("**__Actions:__** " + str(len(monster["action"])) + "\n")

        if "reaction" in monster:
            monsterDesc.append("**__Reactions:__** " + str(len(monster["reaction"])) + "\n")

        if "legendary" in monster:
            monsterDesc.append("**__Legendary Actions:__** " + str(len(monster["legendary"])) + "\n")

    if return_monster:
        return {'monster': monster, 'string': discord_trim(''.join(monsterDesc))}
    else:
        return discord_trim(''.join(monsterDesc))

def searchSpell(name):
    return fuzzywuzzy_search_all_3(c.spells, 'name', name, return_key=True)

async def searchSpellNameFull(name, ctx):
    result = searchSpell(name)
    if result is None:
        return None
    strict = result[1]
    results = result[0]
    bot = ctx.bot

    if strict:
        result = results
    else:
        if len(results) == 1:
            result = results[0]
        else:
            result = await get_selection(results, ctx)
            if result is None:
                await bot.send_message(ctx.message.channel, 'Selection timed out or was cancelled.')
                return None
    return result

def searchAutoSpell(name):
    return fuzzywuzzy_search_all_3(c.autospells, 'name', name)

async def searchAutoSpellFull(name, ctx):
    result = searchAutoSpell(name)
    if result is None:
        return None
    strict = result[1]
    results = result[0]
    bot = ctx.bot

    if strict:
        result = results
    else:
        if len(results) == 1:
            result = results[0]
        else:
            result = await get_selection(results, ctx, name_key='name')
            if result is None:
                await bot.send_message(ctx.message.channel, 'Selection timed out or was cancelled.')
                return None
    return result

def getSpell(spellname, return_spell=False):
    spellDesc = []

    spell = strict_search(c.spells, 'name', spellname)
    original_spell = copy.copy(spell)
    spell = copy.copy(spell)
    if spell is None:
        spellDesc.append("Spell does not exist or is misspelled (ha).")
        if return_spell: return {'spell': None, 'string': spellDesc}
        return spellDesc

    def parseschool(school):
        if school == "A": return "abjuration"
        if school == "EV": return "evocation"
        if school == "EN": return "enchantment"
        if school == "I": return "illusion"
        if school == "D": return "divination"
        if school == "N": return "necromancy"
        if school == "T": return "transmutation"
        if school == "C": return "conjuration"
        return school


    def parsespelllevel(level):
        if level == "0": return "cantrip"
        if level == "2": return level + "nd level"
        if level == "3": return level + "rd level"
        if level == "1": return level + "st level"
        return level + "th level"

    spell['school'] = parseschool(spell.get('school'))
    spell['ritual'] = spell.get('ritual', 'no').lower()

    if spell.get("source") == "UAMystic":
        spellDesc.append("{name}, {level} Mystic Talent. ({classes})\n".format(**spell))
    else:
        spell['level'] = parsespelllevel(spell['level'])
        spellDesc.append("{name}, {level} {school}. ({classes})\n**Casting Time:** {time}\n**Range:** {range}\n**Components:** {components}\n**Duration:** {duration}\n**Ritual:** {ritual}".format(**spell))

    if isinstance(spell['text'], list):
        for a in spell["text"]:
            if a is '': continue
            spellDesc.append(a.replace("At Higher Levels: ", "**At Higher Levels:** ").replace("This spell can be found in the Elemental Evil Player's Companion", ""))
    else:
        spellDesc.append(spell['text'].replace("At Higher Levels: ", "**At Higher Levels:** ").replace("This spell can be found in the Elemental Evil Player's Companion", ""))

    tempStr = '\n'.join(spellDesc)

    if return_spell:
        return {'spell': original_spell, 'string': discord_trim(tempStr)}
    else:
        return discord_trim(tempStr)

def searchItem(name):
    return fuzzywuzzy_search_all_3(c.items, 'name', name, return_key=True)

def getItem(itemname, return_item=False):
    itemDesc = []
    item = strict_search(c.items, 'name', itemname)
    if item is None:
        itemDesc.append("Item does not exist or is misspelled.")
        if return_item: return {'item': None, 'string': itemDesc}
        return itemDesc

    def parsetype (_type):
        if _type == "G": return "Adventuring Gear"
        if _type == "SCF": return "Spellcasting Focus"
        if _type == "AT": return "Artisan Tool"
        if _type == "T": return "Tool"
        if _type == "GS": return "Gaming Set"
        if _type == "INS": return "Instrument"
        if _type == "A": return "Ammunition"
        if _type == "M": return "Melee Weapon"
        if _type == "R": return "Ranged Weapon"
        if _type == "LA": return "Light Armor"
        if _type == "MA": return "Medium Armor"
        if _type == "HA": return "Heavy Armor"
        if _type == "S": return "Shield"
        if _type == "W": return "Wondrous Item"
        if _type == "P": return "Potion"
        if _type == "ST": return "Staff"
        if _type == "RD": return "Rod"
        if _type == "RG": return "Ring"
        if _type == "WD": return "Wand"
        if _type == "SC": return "Scroll"
        if _type == "EXP": return "Explosive"
        if _type == "GUN": return "Firearm"
        if _type == "SIMW": return "Simple Weapon"
        if _type == "MARW": return "Martial Weapon"
        if _type == "$": return "Valuable Object"
        return "n/a"

    def parsedamagetype (damagetype):
        if damagetype == "B": return "bludgeoning"
        if damagetype == "P": return "piercing"
        if damagetype == "S": return "slashing"
        if damagetype == "N": return "necrotic"
        if damagetype == "R": return "radiant"
        return 'n/a'

    def parseproperty (_property):
        if _property == "A": return "ammunition"
        if _property == "LD": return "loading"
        if _property == "L": return "light"
        if _property == "F": return "finesse"
        if _property == "T": return "thrown"
        if _property == "H": return "heavy"
        if _property == "R": return "reach"
        if _property == "2H": return "two-handed"
        if _property == "V": return "versatile"
        if _property == "S": return "special"
        if _property == "RLD": return "reload"
        if _property == "BF": return "burst fire"
        return "n/a"
    itemDict = {}
    itemDict['name'] = item['name']
    itemDict['type'] = ', '.join(parsetype(t) for t in item['type'].split(','))
    itemDict['rarity'] = item.get('rarity')
    itemDict['type_and_rarity'] = itemDict['type'] + ((', ' + itemDict['rarity']) if itemDict['rarity'] is not None else '')
    itemDict['value'] = (item.get('value', 'n/a') + (', ' if 'weight' in item else '')) if 'value' in item else ''
    itemDict['weight'] = (item.get('weight', 'n/a') + (' lb.' if item.get('weight', 'n/a') == '1' else ' lbs.')) if 'weight' in item else ''
    itemDict['weight_and_value'] = itemDict['value'] + itemDict['weight']
    itemDict['damage'] = ''
    for iType in item['type'].split(','):
        if iType in ('M', 'R', 'GUN'):
            itemDict['damage'] = (item.get('dmg1', 'n/a') + ' ' + parsedamagetype(item.get('dmgType', 'n/a'))) if 'dmg1' in item and 'dmgType' in item else ''
        if iType == 'S': itemDict['damage'] = "AC +" + item.get('ac', 'n/a')
        if iType == 'LA': itemDict['damage'] = "AC " + item.get('ac', 'n/a') + '+ DEX'
        if iType == 'MA': itemDict['damage'] = "AC " + item.get('ac', 'n/a') + '+ DEX (Max 2)'
        if iType == 'HA': itemDict['damage'] = "AC " + item.get('ac', 'n/a')
    itemDict['properties'] = ""
    for prop in item.get('property', '').split(','):
        if prop == '': continue
        a = b = prop
        a = parseproperty(a)
        if b == 'V': a += " (" + item.get('dmg2', 'n/a') + ")"
        if b in ('T', 'A'): a += " (" + item.get('range', 'n/a') + "ft.)"
        if b == 'RLD': a += " (" + item.get('reload', 'n/a') + " shots)"
        if len(itemDict['properties']): a = ', ' + a
        itemDict['properties'] += a
    itemDict['damage_and_properties'] = (itemDict['damage'] + ' - ' + itemDict['properties']) if itemDict['properties'] is not '' else itemDict['damage']
    itemDict['damage_and_properties'] = (' --- ' + itemDict['damage_and_properties']) if itemDict['weight_and_value'] is not '' and itemDict['damage_and_properties'] is not '' else itemDict['damage_and_properties']

    itemDesc.append("**{name}**\n*{type_and_rarity}*\n{weight_and_value}{damage_and_properties}\n".format(**itemDict))
    itemDesc.append('\n'.join(a for a in item['text'] if a is not None and 'Rarity:' not in a and 'Source:' not in a))

    tempStr = '\n'.join(itemDesc)
    if return_item:
        return {'item': item, 'string': discord_trim(tempStr)}
    else:
        return tempStr





