"""
Created on Jan 13, 2017

@author: andrew
"""
import copy
import json
import logging

from utils.functions import discord_trim, strict_search, fuzzywuzzy_search_all_3, get_selection, \
    fuzzywuzzy_search_all_3_list, parse_data_entry

log = logging.getLogger(__name__)


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
                if 'trait' in race:
                    one_rfeats = race.get('trait', [])
                    for rfeat in one_rfeats:
                        temp = {'name': "{}: {}".format(race['name'], rfeat['name']),
                                'text': parse_data_entry(rfeat['text']), 'srd': race['srd']}
                        self.rfeats.append(temp)
                else:  # assume entries
                    for entry in race['entries']:
                        temp = {'name': "{}: {}".format(race['name'], entry['name']),
                                'text': parse_data_entry(entry['entries']), 'srd': race['srd']}
                        self.rfeats.append(temp)
        with open('./res/classes.json', 'r', encoding='utf-8-sig') as f:
            _raw = json.load(f)
            self.cfeats = []
            self.classes = copy.deepcopy(_raw)
            for _class in _raw:
                for level in _class.get('classFeatures', []):
                    for feature in level:
                        fe = {'name': f"{_class['name']}: {feature['name']}",
                              'text': parse_data_entry(feature['entries']), 'srd': _class['srd']}
                        self.cfeats.append(fe)
                        options = [e for e in feature['entries'] if
                                   isinstance(e, dict) and e['type'] == 'options']
                        for option in options:
                            for opt_entry in option.get('entries', []):
                                fe = {'name': f"{_class['name']}: {feature['name']}: {_resolve_name(opt_entry)}",
                                      'text': f"{_parse_prereqs(opt_entry)}{parse_data_entry(opt_entry['entries'])}",
                                      'srd': _class['srd']}
                                self.cfeats.append(fe)
                for subclass in _class.get('subclasses', []):
                    for level in subclass.get('subclassFeatures', []):
                        for feature in level:
                            options = [f for f in feature.get('entries', []) if
                                       isinstance(f, dict) and f['type'] == 'options']  # battlemaster only
                            for option in options:
                                for opt_entry in option.get('entries', []):
                                    fe = {'name': f"{_class['name']}: {option['name']}: "
                                                  f"{_resolve_name(opt_entry)}",
                                          'text': parse_data_entry(opt_entry['entries']),
                                          'srd': subclass.get('srd', False)}
                                    self.cfeats.append(fe)
                            for entry in feature.get('entries', []):
                                if not isinstance(entry, dict): continue
                                if not entry.get('type') == 'entries': continue
                                fe = {'name': f"{_class['name']}: {subclass['name']}: {entry['name']}",
                                      'text': parse_data_entry(entry['entries']), 'srd': subclass.get('srd', False)}
                                self.cfeats.append(fe)
                                options = [e for e in entry['entries'] if
                                           isinstance(e, dict) and e['type'] == 'options']
                                for option in options:
                                    for opt_entry in option.get('entries', []):
                                        fe = {'name': f"{_class['name']}: {subclass['name']}: {entry['name']}: "
                                                      f"{_resolve_name(opt_entry)}",
                                              'text': parse_data_entry(opt_entry['entries']),
                                              'srd': subclass.get('srd', False)}
                                        self.cfeats.append(fe)
        with open('./res/bestiary.json', 'r') as f:
            self.monsters = json.load(f)
        with open('./res/spells.json', 'r') as f:
            self.spells = json.load(f)
        with open('./res/items.json', 'r') as f:
            _items = json.load(f)
            self.items = [i for i in _items if i.get('type') is not '$']
        with open('./res/auto_spells.json', 'r') as f:
            self.autospells = json.load(f)
        with open('./res/backgrounds.json', 'r') as f:
            self.backgrounds = json.load(f)
        self.subclasses = self.load_subclasses()

    def load_subclasses(self):
        s = []
        for _class in self.classes:
            subclasses = _class.get('subclasses', [])
            for sc in subclasses:
                sc['name'] = f"{_class['name']}: {sc['name']}"
            s.extend(subclasses)
        return s


def _resolve_name(entry):
    """Resolves the next name of an astranauta entry.
    :param entry (dict) - the entry.
    :returns str - The next found name, or None."""
    if 'entries' in entry and 'name' in entry['entries'][0]:
        return _resolve_name(entry['entries'][0])
    elif 'name' in entry:
        return entry['name']
    else:
        log.warning(f"No name found for {entry}")


def _parse_prereqs(entry):
    if 'prerequisite' in entry:
        return f"*Prerequisite: {entry['prerequisite']}*\n"
    else:
        return ''


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


def searchSubclass(name):
    return fuzzywuzzy_search_all_3(c.subclasses, 'name', name)


def getSubclass(name):
    return strict_search(c.subclasses, 'name', name)


def searchBackground(name):
    return fuzzywuzzy_search_all_3(c.backgrounds, 'name', name)


def getBackground(name):
    return strict_search(c.backgrounds, 'name', name)


# ----- Monster stuff

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

    if strict:
        result = results
    else:
        if len(results) == 1:
            result = results[0]
        else:
            result = await get_selection(ctx, [(r, r) for r in results], pm=pm)
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
            result = await get_selection(ctx, [(r, r) for r in results])
            if result is None:
                await bot.send_message(ctx.message.channel, 'Selection timed out or was cancelled.')
                return None
    return result


async def searchCharacterSpellName(name, ctx, char):
    result = fuzzywuzzy_search_all_3_list(char.get_spell_list(), name)
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
            result = await get_selection(ctx, [(r, r) for r in results])
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
            result = await get_selection(ctx, [(r['name'], r) for r in results])
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
