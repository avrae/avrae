"""
Created on Jan 13, 2017

@author: andrew
"""
import asyncio
import itertools
import json
import logging
import os

import newrelic.agent

from cogs5e.models.background import Background
from cogs5e.models.errors import NoActiveBrew
from cogs5e.models.homebrew.bestiary import Bestiary
from cogs5e.models.homebrew.tome import Tome
from cogs5e.models.monster import Monster
from cogs5e.models.race import Race
from cogs5e.models.spell import Spell
from cogsmisc.stats import Stats
from utils.functions import parse_data_entry, search_and_select, search

HOMEBREW_EMOJI = "<:homebrew:434140566834511872>"
HOMEBREW_ICON = "https://avrae.io/assets/img/homebrew.png"

log = logging.getLogger(__name__)


class Compendium:
    def __init__(self):
        self.backgrounds = []
        self.cfeats = []
        self.classes = []
        self.conditions = []
        self.fancyraces = []
        self.feats = []
        self.itemprops = {}
        self.items = []
        self.monster_mash = []
        self.monsters = []
        self.names = []
        self.rfeats = []
        self.rules = []
        self.spells = []
        self.srd_backgrounds = []
        self.srd_items = []
        self.srd_races = []
        self.srd_spells = []
        self.subclasses = []

        self._base_path = os.path.relpath('res')

    async def reload_task(self, mdb=None):
        wait_for = int(os.getenv('RELOAD_INTERVAL', '3600'))
        if wait_for > 0:
            log.info("Reloading data every %d seconds", wait_for)
            while True:
                await self.reload(mdb)
                await asyncio.sleep(wait_for)

    @newrelic.agent.function_trace()
    async def reload(self, mdb=None):
        log.info("Reloading data")

        loop = asyncio.get_event_loop()

        if mdb is None:
            await loop.run_in_executor(None, self.load_all_json)
        else:
            await self.load_all_mongodb(mdb)

        await loop.run_in_executor(None, self.load_common)

    def load_all_json(self, base_path=None):
        if base_path is not None:
            self._base_path = base_path

        self.cfeats = self.read_json('srd-classfeats.json', [])
        self.classes = self.read_json('srd-classes.json', [])
        self.conditions = self.read_json('conditions.json', [])
        self.feats = self.read_json('srd-feats.json', [])
        self.monsters = self.read_json('srd-bestiary.json', [])
        self.names = self.read_json('names.json', [])
        self.rules = self.read_json('rules.json', [])
        self.srd_backgrounds = self.read_json('srd-backgrounds.json', [])
        self.srd_items = self.read_json('srd-items.json', [])
        self.srd_races = self.read_json('srd-races.json', [])
        self.srd_spells = self.read_json('srd-spells.json', [])

        # Dictionary!
        self.itemprops = self.read_json('itemprops.json', {})

    async def load_all_mongodb(self, mdb):
        lookup = {d['key']: d['object'] for d in await mdb.static_data.find({}).to_list(length=None)}

        self.cfeats = lookup.get('srd-classfeats', [])
        self.classes = lookup.get('srd-classes', [])
        self.conditions = lookup.get('conditions', [])
        self.feats = lookup.get('srd-feats', [])
        self.monsters = lookup.get('srd-bestiary', [])
        self.names = lookup.get('names', [])
        self.rules = lookup.get('rules', [])
        self.srd_backgrounds = lookup.get('srd-backgrounds', [])
        self.srd_items = lookup.get('srd-items', [])
        self.srd_races = lookup.get('srd-races', [])
        self.srd_spells = lookup.get('srd-spells', [])

        # Dictionary!
        self.itemprops = lookup.get('itemprops', {})

    def load_common(self):
        self.backgrounds = [Background.from_data(b) for b in self.srd_backgrounds]
        self.fancyraces = [Race.from_data(r) for r in self.srd_races]
        self.monster_mash = [Monster.from_data(m) for m in self.monsters]
        self.spells = [Spell.from_data(s) for s in self.srd_spells]

        self.items = [i for i in self.srd_items if i.get('type') is not '$']

        self.rfeats = self.load_rfeats()
        self.subclasses = self.load_subclasses()

    def load_rfeats(self):
        ret = []
        for race in self.srd_races:
            for entry in race['entries']:
                if isinstance(entry, dict) and 'name' in entry:
                    temp = {'name': "{}: {}".format(race['name'], entry['name']),
                            'text': parse_data_entry(entry['entries']), 'srd': race['srd']}
                    ret.append(temp)
        return ret

    def load_subclasses(self):
        s = []
        for _class in self.classes:
            subclasses = _class.get('subclasses', [])
            for sc in subclasses:
                sc['name'] = f"{_class['name']}: {sc['name']}"
            s.extend(subclasses)
        return s

    def read_json(self, filename, default):
        data = default
        filepath = os.path.join(self._base_path, filename)
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
        except FileNotFoundError:
            log.warning("File not found: {}".format(filepath))
        log.debug("Loaded {} things from file {}".format(len(data), filename))
        return data


compendium = Compendium()


# ----- Monster stuff
async def select_monster_full(ctx, name, cutoff=5, return_key=False, pm=False, message=None, list_filter=None,
                              return_metadata=False):
    """
    Gets a Monster from the compendium and active bestiary/ies.
    """
    try:
        bestiary = await Bestiary.from_ctx(ctx)
        await bestiary.load_monsters(ctx)
        custom_monsters = bestiary.monsters
        bestiary_id = bestiary.id
    except NoActiveBrew:
        custom_monsters = []
        bestiary_id = None
    choices = list(itertools.chain(compendium.monster_mash, custom_monsters))
    if ctx.guild:
        async for servbestiary in Bestiary.server_bestiaries(ctx):
            if servbestiary.id == bestiary_id:
                continue
            await servbestiary.load_monsters(ctx)
            choices.extend(servbestiary.monsters)

    await Stats.increase_stat(ctx, "monsters_looked_up_life")

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

    await Stats.increase_stat(ctx, "spells_looked_up_life")

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
    choices = list(itertools.chain(compendium.spells, custom_spells))
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
