import asyncio
import collections
import copy
import json
import logging
import os
from typing import Callable, List, Type, TypeVar

import motor.motor_asyncio

import gamedata.spell
from gamedata.action import Action
from gamedata.background import Background
from gamedata.book import Book
from gamedata.feat import Feat
from gamedata.item import AdventuringGear, Armor, MagicItem, Weapon
from gamedata.klass import Class, ClassFeature, Subclass
from gamedata.mixins import LimitedUseGrantorMixin
from gamedata.monster import Monster
from gamedata.race import Race, RaceFeature, SubRace
from gamedata.shared import Sourced
from utils import config
import ldclient

log = logging.getLogger(__name__)
T = TypeVar("T")


class Compendium:
    # noinspection PyTypeHints
    # prevents pycharm from freaking out over type comments
    def __init__(self):
        # raw data
        self.raw_backgrounds = []  # type: list[dict]
        self.raw_monsters = []  # type: list[dict]
        self.raw_classes = []  # type: list[dict]
        self.raw_feats = []  # type: list[dict]
        self.raw_adventuring_gear = []  # type: list[dict]
        self.raw_armor = []  # type: list[dict]
        self.raw_magic_items = []  # type: list[dict]
        self.raw_weapons = []  # type: list[dict]
        self.raw_races = []  # type: list[dict]
        self.raw_subraces = []  # type: list[dict]
        self.raw_spells = []  # type: list[dict]
        self.raw_books = []  # type: list[dict]
        self.raw_actions = []  # type: list[dict]

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

        self.adventuring_gear = []  # type: list[AdventuringGear]
        self.armor = []  # type: list[Armor]
        self.magic_items = []  # type: list[MagicItem]
        self.weapons = []  # type: list[Weapon]

        self.feats = []  # type: list[Feat]
        self.monsters = []  # type: list[Monster]
        self.spells = []  # type: list[gamedata.spell.Spell]
        self.books = []  # type: list[Book]
        self.actions = []  # type: list[Action]

        # blobs
        self.names = []
        self.rule_references = []

        # lookup helpers
        self._entity_lookup = {}
        self._book_lookup = {}
        self._actions_by_uid = {}  # {uuid: Action}
        self._actions_by_eid = collections.defaultdict(lambda: [])  # {(tid, eid): [Action]}
        self._epoch = 0

        self._base_path = os.path.relpath("res")

    async def reload_task(self, mdb=None):
        wait_for = int(config.RELOAD_INTERVAL)
        await self.reload(mdb)
        if wait_for > 0:
            log.info("Reloading data every %d seconds", wait_for)
            while True:
                await asyncio.sleep(wait_for)
                await self.reload(mdb)

    async def reload(self, mdb=None):
        log.info("Reloading data")

        loop = asyncio.get_event_loop()

        if mdb is None:
            await loop.run_in_executor(None, self.load_all_json)
        else:
            await self.load_all_mongodb(mdb)

        await loop.run_in_executor(None, self.load_common)
        log.info(f"Done loading data - {len(self._entity_lookup)} lookups registered")

    def load_all_json(self, base_path=None):
        if base_path is not None:
            self._base_path = base_path

        self.raw_classes = self.read_json("classes.json", [])
        self.raw_feats = self.read_json("feats.json", [])
        self.raw_monsters = self.read_json("monsters.json", [])
        self.raw_backgrounds = self.read_json("backgrounds.json", [])
        self.raw_adventuring_gear = self.read_json("adventuring-gear.json", [])
        self.raw_armor = self.read_json("armor.json", [])
        self.raw_magic_items = self.read_json("magic-items.json", [])
        self.raw_weapons = self.read_json("weapons.json", [])
        self.raw_races = self.read_json("races.json", [])
        self.raw_subraces = self.read_json("subraces.json", [])
        self.raw_spells = self.read_json("spells.json", [])
        self.raw_books = self.read_json("books.json", [])
        self.raw_actions = self.read_json("actions.json", [])

        self.names = self.read_json("names.json", [])
        self.rule_references = self.read_json("srd-references.json", [])

    async def load_all_mongodb(self, mdb):
        lookup = {d["key"]: d["object"] async for d in mdb.static_data.find({})}

        self.raw_classes = lookup.get("classes", [])
        self.raw_feats = lookup.get("feats", [])

        ldclient.set_config(ldclient.Config(sdk_key=config.LAUNCHDARKLY_SDK_KEY))

        # TODO: Try importing Context as a standalone method
        context = ldclient.Context.create("anonymous-user-start-bot")
        if ldclient.get().variation("data.monsters.gridfs", context, False) or config.TESTING:
            fs = motor.motor_asyncio.AsyncIOMotorGridFSBucket(mdb)
            data = await fs.open_download_stream_by_name(filename="monsters")
            gridout = await data.read()
            self.raw_monsters = json.loads(gridout)
        else:
            self.raw_monsters = lookup.get("monsters", [])
        self.raw_backgrounds = lookup.get("backgrounds", [])
        self.raw_adventuring_gear = lookup.get("adventuring-gear", [])
        self.raw_armor = lookup.get("armor", [])
        self.raw_magic_items = lookup.get("magic-items", [])
        self.raw_weapons = lookup.get("weapons", [])
        self.raw_races = lookup.get("races", [])
        self.raw_subraces = lookup.get("subraces", [])
        self.raw_spells = lookup.get("spells", [])
        self.raw_books = lookup.get("books", [])
        self.raw_actions = lookup.get("actions", [])

        self.names = lookup.get("names", [])
        self.rule_references = lookup.get("srd-references", [])

    # noinspection DuplicatedCode
    def load_common(self):
        self._entity_lookup = {}
        self._book_lookup = {}

        self.backgrounds = self._deserialize_and_register_lookups(Background, self.raw_backgrounds)
        self.classes = self._deserialize_and_register_lookups(Class, self.raw_classes)
        self.races = self._deserialize_and_register_lookups(Race, self.raw_races)
        self.subraces = self._deserialize_and_register_lookups(SubRace, self.raw_subraces)
        # if a Feat has the hidden attribute, we skip registering it in the lookup list but still register it in
        # entity lookup so it can grant limiteduse/etc
        self.feats = self._deserialize_and_register_lookups(Feat, self.raw_feats, skip_out_filter=lambda f: f.hidden)
        self.adventuring_gear = self._deserialize_and_register_lookups(AdventuringGear, self.raw_adventuring_gear)
        self.armor = self._deserialize_and_register_lookups(Armor, self.raw_armor)
        self.magic_items = self._deserialize_and_register_lookups(MagicItem, self.raw_magic_items)
        self.weapons = self._deserialize_and_register_lookups(Weapon, self.raw_weapons)
        self.monsters = self._deserialize_and_register_lookups(Monster, self.raw_monsters)
        self.spells = self._deserialize_and_register_lookups(gamedata.spell.Spell, self.raw_spells)
        self.books = self._deserialize_and_register_lookups(Book, self.raw_books)

        # generated
        self._load_classfeats()
        self._load_subclasses()
        self._load_racefeats()
        self._load_actions()  # actions don't register as DDB entities, they're their own thing
        self._register_book_lookups()

        # increase epoch for any dependents
        self._epoch += 1

    def _load_subclasses(self):
        self.subclasses = []
        for cls in self.classes:
            for subcls in cls.subclasses:
                copied = copy.copy(subcls)
                copied.name = f"{cls.name}: {subcls.name}"
                # register lookups
                self._register_entity_lookup(subcls)
                self.subclasses.append(copied)

    def _load_classfeats(self):
        """
        Loads all class features by iterating over classes and subclasses.
        """
        self.cfeats = []
        self.optional_cfeats = []
        seen = set()

        def handle_class(cls_or_sub):
            # Certain features are for action/limited use import only
            # load classfeats
            for i, level in enumerate(cls_or_sub.levels):
                for feature in level:
                    copied = copy.copy(feature)
                    copied.name = f"{cls_or_sub.name}: {feature.name}"
                    if copied.name in seen:
                        copied.name = f"{copied.name} (Level {i + 1})"
                    seen.add(copied.name)
                    self.cfeats.append(copied)
                    self._register_entity_lookup(feature)

                    for cfo in feature.options:
                        copied = copy.copy(cfo)
                        copied.name = f"{cls_or_sub.name}: {feature.name}: {cfo.name}"
                        self.cfeats.append(copied)
                        self._register_entity_lookup(cfo)

            # TCoE optional features and options
            for feature in cls_or_sub.optional_features:
                copied = copy.copy(feature)
                copied.name = f"{cls_or_sub.name}: {feature.name}"
                self.optional_cfeats.append(copied)
                self._register_entity_lookup(feature)

                for cfo in feature.options:
                    copied = copy.copy(cfo)
                    copied.name = f"{cls_or_sub.name}: {feature.name}: {cfo.name}"
                    self.optional_cfeats.append(copied)
                    self._register_entity_lookup(cfo)

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

                self._register_entity_lookup(feature, allow_overwrite=not feature.inherited)
                # race feature options (e.g. breath weapon, silver dragon) are registered here as well
                for rfo in feature.options:
                    self._register_entity_lookup(rfo, allow_overwrite=not feature.inherited)

        for base_race in self.races:
            self.rfeats.extend(handle_race(base_race))

        for subrace in self.subraces:
            self.subrfeats.extend(handle_race(subrace))

    def _load_actions(self):
        self.actions = []
        self._actions_by_eid.clear()
        self._actions_by_uid.clear()
        for action_data in self.raw_actions:
            action = Action.from_data(action_data)
            self.actions.append(action)
            self._actions_by_uid[action.uid] = action
            self._actions_by_eid[(action.type_id, action.id)].append(action)

    def _deserialize_and_register_lookups(
        self, cls: Type[T], data_source: List[dict], skip_out_filter: Callable[[T], bool] = None, **kwargs
    ) -> List[T]:
        out = []
        for entity_data in data_source:
            entity = cls.from_data(entity_data, **kwargs)
            self._register_entity_lookup(entity)
            if skip_out_filter is None or not skip_out_filter(entity):
                out.append(entity)
        return out

    def _register_entity_lookup(self, entity: Sourced, allow_overwrite=True):
        k = (entity.entity_type, entity.entity_id)
        if k in self._entity_lookup:
            if not allow_overwrite:
                log.debug(
                    f"Entity was not registered due to overwrite rules: {k} "
                    f"({self._entity_lookup[k].name} -> {entity.name})"
                )
                return
            elif entity.name != self._entity_lookup[k].name:
                log.debug(
                    f"Overwriting existing entity lookup key: {k} ({self._entity_lookup[k].name} -> {entity.name})"
                )
            else:
                log.debug(
                    f"Entity lookup key {k} is registered multiple times: "
                    f"({self._entity_lookup[k].name}, {entity.name})"
                )
        log.debug(f"Registered entity {k}: {entity!r}")
        self._entity_lookup[k] = entity
        kt = (entity.type_id, entity.entity_id)
        self._entity_lookup[kt] = entity

        # if the entity has granted limited uses, register those too
        if isinstance(entity, LimitedUseGrantorMixin):
            for lu in entity.limited_use:
                self._register_entity_lookup(lu)

    def _register_book_lookups(self):
        for book in self.books:
            self._book_lookup[book.source] = book

    def read_json(self, filename, default):
        data = default
        filepath = os.path.join(self._base_path, filename)
        try:
            with open(filepath, "r") as f:
                data = json.load(f)
        except FileNotFoundError:
            log.warning("File not found: {}".format(filepath))
        log.debug("Loaded {} things from file {}".format(len(data), filename))
        return data

    # helpers
    def lookup_entity(self, entity_type, entity_id):
        """
        Gets an entity by its entity type (entitlement str or typeId) and ID.

        :type entity_type: str or int
        :type entity_id: int
        """
        return self._entity_lookup.get((entity_type, entity_id))

    def book_by_source(self, short_source: str):
        """
        Gets a Book by its short code.

        :rtype: Book
        """
        return self._book_lookup.get(short_source)

    def lookup_action(self, uid):
        """
        Gets an action by its unique ID.

        :type uid: str
        :rtype: Action or None
        """
        return self._actions_by_uid.get(uid)

    def lookup_actions_for_entity(self, tid, eid):
        """
        Returns the list of actions (possibly empty) granted by an entity with the given type id/id.

        :rtype: list of Action
        """
        return self._actions_by_eid[(tid, eid)]

    @property
    def epoch(self):
        """
        Returns an integer representing the current gamedata epoch. This number may not decrease, and must increase any
        time any part of the gamedata changes.
        """
        return self._epoch


compendium = Compendium()
