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
            self.races = copy.deepcopy(_raw)
            for race in _raw:
                one_rfeats = race.get('trait', [])
                for i, rfeat in enumerate(one_rfeats):
                    one_rfeats[i]['name'] = "{}: {}".format(race['name'], rfeat['name'])
                self.rfeats += one_rfeats
        with open('./res/classes.json', 'r') as f:
            _raw = json.load(f)
            self.cfeats = []
            self.classes = copy.deepcopy(_raw)
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

def searchRace(name):
    return fuzzywuzzy_search_all_3(c.races, 'name', name)

def getRace(name):
    return strict_search(c.races, 'name', name)

def searchClassFeat(name):
    return fuzzywuzzy_search_all_3(c.cfeats, 'name', name)

def getClassFeat(feat):
    return strict_search(c.cfeats, 'name', feat)

def searchClass(name):
    return fuzzywuzzy_search_all_3(c.classes, 'name', name)

def getClass(name):
    return strict_search(c.classes, 'name', name)

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
    embed.colour = random.randint(0, 0xffffff)
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

def old_searchMonster(name):
    return fuzzywuzzy_search_all_3(c.monsters, 'name', name, return_key=True)

def searchMonster(name):
    return fuzzywuzzy_search_all_3(c.monsters, 'name', name)

def getMonster(name):
    return strict_search(c.monsters, 'name', name)

async def searchMonsterFull(name, ctx, pm=False):
    result = old_searchMonster(name)
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

    result = old_getMonster(result, visible=True, return_monster=True)
    return result

def old_getMonster(monstername, visible=True, return_monster=False):
    monsterDesc = []
    monster = strict_search(c.monsters, 'name', monstername)
    if monster is None:
        monsterDesc.append("Monster does not exist or is misspelled.")
        if return_monster: return {'monster': None, 'string': monsterDesc}
        return monsterDesc

    if return_monster:
        return {'monster': monster, 'string': 'deprecated'}
    else:
        return discord_trim('deprecated')

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

def getSpell(spellname):
    return strict_search(c.spells, 'name', spellname)

def searchItem(name):
    return fuzzywuzzy_search_all_3(c.items, 'name', name)

def getItem(itemname):
    return strict_search(c.items, 'name', itemname)






