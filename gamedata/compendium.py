import asyncio
import json
import logging
import os

import newrelic.agent

from cogs5e.models.monster import Monster
from cogs5e.models.spell import Spell
from gamedata.background import Background
from gamedata.race import Race
from utils import config

log = logging.getLogger(__name__)


class Compendium:
    def __init__(self):
        self.backgrounds = []
        self.cfeats = []
        self.classes = []
        self.fancyraces = []
        self.feats = []
        self.itemprops = {}
        self.items = []
        self.monster_mash = []
        self.monsters = []
        self.names = []
        self.rfeats = []
        self.spells = []
        self.rule_references = []
        self.srd_backgrounds = []
        self.srd_races = []
        self.srd_spells = []
        self.subclasses = []

        # non-srd names
        self.all_nsrd_names = {}
        self.nfeat_names = []
        self.nrfeat_names = []
        self.nrace_names = []
        self.ncfeat_names = []
        self.nclass_names = []
        self.nsubclass_names = []
        self.nbackground_names = []
        self.nmonster_names = []
        self.nspell_names = []
        self.nitem_names = []

        self._base_path = os.path.relpath('res')

    async def reload_task(self, mdb=None):
        wait_for = int(config.RELOAD_INTERVAL)
        await self.reload(mdb)
        if wait_for > 0:
            log.info("Reloading data every %d seconds", wait_for)
            while True:
                await asyncio.sleep(wait_for)
                await self.reload(mdb)

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
        self.feats = self.read_json('srd-feats.json', [])
        self.monsters = self.read_json('srd-bestiary.json', [])
        self.names = self.read_json('names.json', [])
        self.rule_references = self.read_json('srd-references.json', [])
        self.srd_backgrounds = self.read_json('srd-backgrounds.json', [])
        self.items = self.read_json('srd-items.json', [])
        self.srd_races = self.read_json('srd-races.json', [])
        self.rfeats = self.read_json('srd-racefeats', [])
        self.srd_spells = self.read_json('srd-spells.json', [])

        # Dictionary!
        self.itemprops = self.read_json('itemprops.json', {})
        self.all_nsrd_names = self.read_json('nsrd-names.json', {})

    async def load_all_mongodb(self, mdb):
        lookup = {d['key']: d['object'] for d in await mdb.static_data.find({}).to_list(length=None)}

        self.cfeats = lookup.get('srd-classfeats', [])
        self.classes = lookup.get('srd-classes', [])
        self.feats = lookup.get('srd-feats', [])
        self.monsters = lookup.get('srd-bestiary', [])
        self.names = lookup.get('names', [])
        self.rule_references = lookup.get('srd-references', [])
        self.srd_backgrounds = lookup.get('srd-backgrounds', [])
        self.items = lookup.get('srd-items', [])
        self.srd_races = lookup.get('srd-races', [])
        self.rfeats = lookup.get('srd-racefeats', [])
        self.srd_spells = lookup.get('srd-spells', [])

        # Dictionary!
        self.itemprops = lookup.get('itemprops', {})
        self.all_nsrd_names = lookup.get('nsrd-names', {})

    def load_common(self):
        self.backgrounds = [Background.from_data(b) for b in self.srd_backgrounds]
        self.fancyraces = [Race.from_data(r) for r in self.srd_races]
        self.monster_mash = [Monster.from_data(m) for m in self.monsters]
        self.spells = [Spell.from_data(s) for s in self.srd_spells]

        self.subclasses = self._load_subclasses()
        self._load_nsrd_names()

    def _load_subclasses(self):
        s = []
        for _class in self.classes:
            subclasses = _class.get('subclasses', [])
            for sc in subclasses:
                sc['name'] = f"{_class['name']}: {sc['name']}"
            s.extend(subclasses)
        return s

    def _load_nsrd_names(self):
        self.nfeat_names = nameify(self.all_nsrd_names.get('feat', []))
        self.nrfeat_names = nameify(self.all_nsrd_names.get('rfeat', []))
        self.nrace_names = nameify(self.all_nsrd_names.get('race', []))
        self.ncfeat_names = nameify(self.all_nsrd_names.get('cfeat', []))
        self.nclass_names = nameify(self.all_nsrd_names.get('class', []))
        self.nsubclass_names = nameify(self.all_nsrd_names.get('subclass', []))
        self.nbackground_names = nameify(self.all_nsrd_names.get('background', []))
        self.nmonster_names = nameify(self.all_nsrd_names.get('monster', []))
        self.nspell_names = nameify(self.all_nsrd_names.get('spell', []))
        self.nitem_names = nameify(self.all_nsrd_names.get('item', []))

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


# ==== nsrd helper class ====
class NSRDName:
    def __init__(self, name):
        self.name = name
        self.srd = False
        self.source = "NSRD"

    def get(self, attr, default=None):
        return self.__getattribute__(attr) if hasattr(self, attr) else default

    def __getitem__(self, item):
        return self.__getattribute__(item)


def nameify(iterable):
    """Takes a list of strings and returns a list of NSRDNames."""
    return list(map(NSRDName, iterable))
