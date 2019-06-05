"""
Created on Jan 13, 2017

@author: andrew
"""
import itertools
import json
import logging
import os

from cogs5e.models.background import Background
from cogs5e.models.errors import NoActiveBrew
from cogs5e.models.homebrew.bestiary import Bestiary
from cogs5e.models.homebrew.tome import Tome
from cogs5e.models.monster import Monster
from cogs5e.models.race import Race
from cogs5e.models.spell import Spell
from utils.functions import parse_data_entry, search_and_select, search

HOMEBREW_EMOJI = "<:homebrew:434140566834511872>"
HOMEBREW_ICON = "https://avrae.io/assets/img/homebrew.png"

log = logging.getLogger(__name__)


class Compendium:
    def __init__(self):
        self.cfeats = self.load_json('srd-classfeats.json', [])
        self.classes = self.load_json('srd-classes.json', [])
        self.conditions = self.load_json('conditions.json', [])
        self.feats = self.load_json('srd-feats.json', [])
        self.itemprops = self.load_json('itemprops.json', {})
        self.monsters = self.load_json('srd-bestiary.json', [])
        self.names = self.load_json('names.json', [])
        self.rules = self.load_json('rules.json', [])
        self.spells = self.load_json('srd-spells.json', [])

        self.backgrounds = [Background.from_data(b) for b in self.load_json('srd-backgrounds.json', [])]
        self.items = [i for i in self.load_json('srd-items.json', []) if i.get('type') is not '$']
        self.monster_mash = [Monster.from_data(m) for m in self.monsters]
        
        self.subclasses = self.load_subclasses()

        srd_races = self.load_json('srd-races.json', [])
        self.fancyraces = [Race.from_data(r) for r in srd_races]
        self.rfeats = []
        for race in srd_races:
            for entry in race['entries']:
                if isinstance(entry, dict) and 'name' in entry:
                    temp = {'name': "{}: {}".format(race['name'], entry['name']),
                            'text': parse_data_entry(entry['entries']), 'srd': race['srd']}
                    self.rfeats.append(temp)

    def load_subclasses(self):
        s = []
        for _class in self.classes:
            subclasses = _class.get('subclasses', [])
            for sc in subclasses:
                sc['name'] = f"{_class['name']}: {sc['name']}"
            s.extend(subclasses)
        return s

    def load_json(self, filename, default):
        data = default
        filepath = os.path.join('res', filename)
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
        except FileNotFoundError:
            log.error("File not found: {}".format(filepath))
            pass
        return data

c = Compendium()


# ----- Monster stuff
async def select_monster_full(ctx, name, cutoff=5, return_key=False, pm=False, message=None, list_filter=None,
                              return_metadata=False):
    """
    Gets a Monster from the compendium and active bestiary/ies.
    """
    try:
        bestiary = await Bestiary.from_ctx(ctx)
        custom_monsters = bestiary.monsters
        bestiary_id = bestiary.id
    except NoActiveBrew:
        custom_monsters = []
        bestiary_id = None
    choices = list(itertools.chain(c.monster_mash, custom_monsters))
    if ctx.guild:
        async for servbestiary in ctx.bot.mdb.bestiaries.find({"server_active": str(ctx.guild.id)}, ['monsters']):
            choices.extend(
                Monster.from_bestiary(m) for m in servbestiary['monsters'] if servbestiary['_id'] != bestiary_id)

    def get_homebrew_formatted_name(monster):
        if monster.source == 'homebrew':
            return f"{monster.name} ({HOMEBREW_EMOJI})"
        return monster.name

    return await search_and_select(ctx, choices, name, lambda e: e.name, cutoff, return_key, pm, message, list_filter,
                                   selectkey=get_homebrew_formatted_name, return_metadata=return_metadata)


# ---- SPELL STUFF ----
async def select_spell_full(ctx, name, cutoff=5, return_key=False, pm=False, message=None, list_filter=None,
                            search_func=None, return_metadata=False):
    """
    Gets a Spell from the compendium and active tome(s).
    """
    choices = await get_spell_choices(ctx)

    def get_homebrew_formatted_name(spell):
        if spell.source == 'homebrew':
            return f"{spell.name} ({HOMEBREW_EMOJI})"
        return spell.name

    return await search_and_select(ctx, choices, name, lambda e: e.name, cutoff, return_key, pm, message, list_filter,
                                   selectkey=get_homebrew_formatted_name, search_func=search_func,
                                   return_metadata=return_metadata)


async def get_spell_choices(ctx):
    try:
        tome = await Tome.from_ctx(ctx)
        custom_spells = tome.spells
        tome_id = tome.id
    except NoActiveBrew:
        custom_spells = []
        tome_id = None
    choices = list(itertools.chain(c.spells, custom_spells))
    if ctx.guild:
        async for servtome in ctx.bot.mdb.tomes.find({"server_active": str(ctx.guild.id)}, ['spells']):
            choices.extend(Spell.from_dict(s) for s in servtome['spells'] if servtome['_id'] != tome_id)
    return choices


async def get_castable_spell(ctx, name, choices=None):
    if choices is None:
        choices = await get_spell_choices(ctx)

    result = search(choices, name, lambda sp: sp.name)
    if result and result[1]:
        return result[0]
    return None
