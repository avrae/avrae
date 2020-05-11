import asyncio
import copy
import itertools
import json
import logging
import os

import newrelic.agent

from gamedata.background import Background
from gamedata.feat import Feat
from gamedata.item import Item
from gamedata.klass import Class, Subclass
from gamedata.monster import Monster
from gamedata.race import Race
from gamedata.shared import SourcedTrait
from gamedata.spell import Spell
from utils import config

log = logging.getLogger(__name__)


class Compendium:
    # noinspection PyUnresolvedReferences
    # prevents pycharm from freaking out over type comments
    def __init__(self):
        # raw data
        self.raw_backgrounds = []  # type: list[dict]
        self.raw_monsters = []  # type: list[dict]
        self.raw_classes = []  # type: list[dict]
        self.raw_feats = []  # type: list[dict]
        self.raw_items = []  # type: list[dict]
        self.raw_races = []  # type: list[dict]
        self.raw_subraces = []  # type: list[dict]
        self.raw_spells = []  # type: list[dict]

        # models
        self.backgrounds = []  # type: list[Background]

        self.cfeats = []  # type: list[SourcedTrait]
        self.classes = []  # type: list[Class]
        self.subclasses = []  # type: list[Subclass]

        self.races = []  # type: list[Race]
        self.subraces = []  # type: list[Race]
        self.rfeats = []  # type: list[SourcedTrait]
        self.subrfeats = []  # type: list[SourcedTrait]

        self.feats = []  # type: list[Feat]
        self.items = []  # type: list[Item]
        self.monsters = []  # type: list[Monster]
        self.spells = []  # type: list[Spell]

        # blobs
        self.names = []
        self.rule_references = []

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

        self.raw_classes = self.read_json('srd-classes.json', [])
        self.raw_feats = self.read_json('srd-feats.json', [])
        self.raw_monsters = self.read_json('srd-bestiary.json', [])
        self.raw_backgrounds = self.read_json('srd-backgrounds.json', [])
        self.raw_items = self.read_json('srd-items.json', [])
        self.raw_races = self.read_json('srd-races.json', [])
        self.raw_subraces = self.read_json('srd-subraces.json', [])
        self.raw_spells = self.read_json('srd-spells.json', [])

        self.names = self.read_json('names.json', [])
        self.rule_references = self.read_json('srd-references.json', [])

    async def load_all_mongodb(self, mdb):
        lookup = {d['key']: d['object'] async for d in mdb.static_data.find({})}

        self.raw_classes = lookup.get('classes', [])
        self.raw_feats = lookup.get('feats', [])
        self.raw_monsters = lookup.get('monsters', [])
        self.raw_backgrounds = lookup.get('backgrounds', [])
        self.raw_items = lookup.get('items', [])
        self.raw_races = lookup.get('races', [])
        self.raw_subraces = lookup.get('subraces', [])
        self.raw_spells = lookup.get('spells', [])

        self.names = lookup.get('names', [])
        self.rule_references = lookup.get('srd-references', [])

    # noinspection DuplicatedCode
    def load_common(self):
        self.backgrounds = [Background.from_data(b) for b in self.raw_backgrounds]
        self.classes = [Class.from_data(c) for c in self.raw_classes]
        self.races = [Race.from_data(r) for r in self.raw_races]
        self.subraces = [Race.from_data(r) for r in self.raw_subraces]
        self.feats = [Feat.from_data(f) for f in self.raw_feats]
        self.items = [Item.from_data(i) for i in self.raw_items]
        self.monsters = [Monster.from_data(m) for m in self.raw_monsters]
        self.spells = [Spell.from_data(s) for s in self.raw_spells]

        # generated
        self._load_classfeats()
        self._load_subclasses()
        self._load_racefeats()

    def _load_subclasses(self):
        self.subclasses = []
        for cls in self.classes:
            for subcls in cls.subclasses:
                copied = copy.copy(subcls)
                copied.name = f"{cls.name}: {subcls.name}"
                self.subclasses.append(copied)

    def _load_classfeats(self):
        """
        Loads all class features as a list of SourcedTraits. Class feature entity IDs inherit the entity ID of their
        parent class.
        """
        self.cfeats = []
        seen = set()

        def handle_class(cls_or_sub):
            for i, level in enumerate(cls_or_sub.levels):
                for feature in level:
                    copied = SourcedTrait.from_trait_and_sourced(feature, cls_or_sub, "classfeat")
                    copied.name = f"{cls_or_sub.name}: {feature.name}"
                    if copied.name in seen:
                        copied.name = f"{copied.name} (Level {i + 1})"
                    seen.add(copied.name)
                    self.cfeats.append(copied)

        for cls in self.classes:
            handle_class(cls)
            for subcls in cls.subclasses:
                handle_class(subcls)

    def _load_racefeats(self):
        self.rfeats = []
        for race in itertools.chain(self.races, self.subraces):
            for feature in race.traits:
                copied = SourcedTrait.from_trait_and_sourced(feature, race, "racefeat")
                copied.name = f"{race.name}: {feature.name}"
                self.rfeats.append(copied)

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
