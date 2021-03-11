import asyncio
import copy
import json
import logging
import os

import newrelic.agent

import gamedata.spell
from gamedata.background import Background
from gamedata.feat import Feat
from gamedata.item import Item
from gamedata.klass import Class, ClassFeature, Subclass
from gamedata.monster import Monster
from gamedata.race import Race, RaceFeature, RaceFeatureOption
from utils import config

log = logging.getLogger(__name__)


class Compendium:
    # noinspection PyTypeHints
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

        self.cfeats = []  # type: list[ClassFeature]
        self.optional_cfeats = []  # type: list[ClassFeature]
        # cfeats uses class as entitlement lookup - optional cfeats uses class-feature
        self.classes = []  # type: list[Class]
        self.subclasses = []  # type: list[Subclass]

        self.races = []  # type: list[Race]
        self.subraces = []  # type: list[Race]
        self.rfeats = []  # type: list[RaceFeature]
        self.subrfeats = []  # type: list[RaceFeature]

        self.feats = []  # type: list[Feat]
        self.items = []  # type: list[Item]
        self.monsters = []  # type: list[Monster]
        self.spells = []  # type: list[Spell]

        # blobs
        self.names = []
        self.rule_references = []

        # lookup helpers
        self._entity_lookup = {}

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
        log.info(f"Done loading data - {len(self._entity_lookup)} objects registered")

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
        self._entity_lookup = {}

        def deserialize_and_register_lookups(cls, data_source, **kwargs):
            out = []
            for entity_data in data_source:
                entity = cls.from_data(entity_data, **kwargs)
                self._register_entity_lookup(entity)
                out.append(entity)
            return out

        self.backgrounds = deserialize_and_register_lookups(Background, self.raw_backgrounds)
        self.classes = deserialize_and_register_lookups(Class, self.raw_classes)
        self.races = deserialize_and_register_lookups(Race, self.raw_races)
        self.subraces = deserialize_and_register_lookups(Race, self.raw_subraces, is_subrace=True)
        self.feats = deserialize_and_register_lookups(Feat, self.raw_feats)
        self.items = deserialize_and_register_lookups(Item, self.raw_items)
        self.monsters = deserialize_and_register_lookups(Monster, self.raw_monsters)
        self.spells = deserialize_and_register_lookups(gamedata.spell.Spell, self.raw_spells)

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
                # register lookups
                self._register_entity_lookup(copied)
                self.subclasses.append(copied)

    def _load_classfeats(self):
        """
        Loads all class features by iterating over classes and subclasses.
        """
        self.cfeats = []
        self.optional_cfeats = []
        seen = set()

        def handle_class(cls_or_sub):
            for i, level in enumerate(cls_or_sub.levels):
                for feature in level:
                    copied = copy.copy(feature)
                    copied.name = f"{cls_or_sub.name}: {feature.name}"
                    if copied.name in seen:
                        copied.name = f"{copied.name} (Level {i + 1})"
                    seen.add(copied.name)
                    self.cfeats.append(copied)
                    self._register_entity_lookup(copied)

            for feature in cls_or_sub.feature_options:
                copied = copy.copy(feature)
                copied.name = f"{cls_or_sub.name}: {feature.name}"
                self.cfeats.append(copied)
                self._register_entity_lookup(copied)

            for feature in cls_or_sub.optional_features:
                copied = copy.copy(feature)
                copied.name = f"{cls_or_sub.name}: {feature.name}"
                self.optional_cfeats.append(copied)
                self._register_entity_lookup(copied)

        for cls in self.classes:
            handle_class(cls)
            for subcls in cls.subclasses:
                handle_class(subcls)

    def _load_racefeats(self):
        self.rfeats = []
        self.subrfeats = []

        def handle_race(race):
            for feature in race.traits:
                copied = copy.copy(feature)
                copied.name = f"{race.name}: {feature.name}"
                yield copied
                self._register_entity_lookup(feature)
                # race feature options (e.g. breath weapon) are registered here as well, they just link to the
                # race feature
                for option_id in feature.option_ids:
                    rfo = RaceFeatureOption.from_race_feature(feature, option_id)
                    self._register_entity_lookup(rfo)

        for base_race in self.races:
            self.rfeats.extend(handle_race(base_race))

        for subrace in self.subraces:
            self.subrfeats.extend(handle_race(subrace))

    def _register_entity_lookup(self, entity):
        k = (entity.entity_type, entity.entity_id)
        if k in self._entity_lookup:
            if entity.name != self._entity_lookup[k].name:
                log.info(f"Overwriting existing entity lookup key: {k} "
                         f"({self._entity_lookup[k].name} -> {entity.name})")
            else:
                log.debug(f"Entity lookup key {k} is registered multiple times: "
                          f"({self._entity_lookup[k].name}, {entity.name})")
        log.debug(f"Registered entity {k}: {entity!r}")
        self._entity_lookup[k] = entity

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

    # helpers
    def lookup_entity(self, entity_type: str, entity_id: int):
        """Gets an entity by its entitlement data."""
        return self._entity_lookup.get((entity_type, entity_id))


compendium = Compendium()
