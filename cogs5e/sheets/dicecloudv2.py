"""
Created on Nov 08, 2022

@author: lazydope
"""

import ast
import collections
import logging
import re
from math import ceil, floor

import draconic
from cogs5e.models.sheet.coinpurse import Coinpurse

from cogs5e.models.character import Character
from cogs5e.models.dicecloud.clientv2 import DicecloudV2Client
from cogs5e.models.dicecloud.errors import DicecloudException
from cogs5e.models.errors import ExternalImportError
from cogs5e.models.sheet.action import Action, Actions
from cogs5e.models.sheet.attack import Attack, AttackList
from cogs5e.models.sheet.base import BaseStats, Levels, Saves, Skill, Skills
from cogs5e.models.sheet.resistance import Resistances
from cogs5e.models.sheet.spellcasting import Spellbook, SpellbookSpell
from cogs5e.sheets.utils import get_actions_for_names, get_actions_for_name
from gamedata.compendium import compendium
from utils.constants import DAMAGE_TYPES, SAVE_NAMES, SKILL_MAP, SKILL_NAMES, STAT_NAMES
from utils.functions import search
from utils.enums import ActivationType
from .abc import SHEET_VERSION, SheetLoaderABC

API_BASE = "https://beta.dicecloud.com/character/"
DICECLOUDV2_URL_RE = re.compile(r"(?:https?://)?beta\.dicecloud\.com/character/([\d\w]+)/?")

ACTIVATION_DICT = {
    "action": ActivationType.ACTION,
    "bonus": ActivationType.BONUS_ACTION,
    "attack": None,
    "reaction": ActivationType.REACTION,
    "free": ActivationType.NO_ACTION,
    "long": ActivationType.SPECIAL,
}


class DicecloudV2Parser(SheetLoaderABC):
    def __init__(self, url):
        super(DicecloudV2Parser, self).__init__(url)
        self.stats = None
        self.levels = None
        self.args = None
        self.coinpurse = None
        self._by_type = {}
        self._all = {}
        self._seen_action_names = set()

    async def load_character(self, ctx, args):
        """
        Downloads and parses the character data, returning a fully-formed Character object.
        :raises ExternalImportError if something went wrong during the import that we can expect
        :raises Exception if something weirder happened
        """
        self.args = args
        owner_id = str(ctx.author.id)
        try:
            await self.get_character()
        except DicecloudException as e:
            raise ExternalImportError(f"Dicecloud V2 returned an error: {e}")

        upstream = f"dicecloudv2-{self.url}"
        active = False
        sheet_type = "dicecloudv2"
        import_version = SHEET_VERSION
        name = self.character_data["creatures"][0].get("name",'').strip()
        description = None  # TODO
        image = self.character_data["creatures"][0].get("picture", '')

        for prop in self.character_data["creatureProperties"]:
            if prop.get("removed"):
                continue
            prop_type = prop["type"]
            prop_id = prop["_id"]
            if prop_type not in self._by_type:
                self._by_type[prop_type] = {}
            self._by_type[prop_type][prop_id] = self._all[prop_id] = prop

        max_hp, ac, stats = self.get_stats()
        levels = self.get_levels()
        actions, consumables, attacks = self.get_attacks()  # TODO: parser unfinished

        skills, saves = self.get_skills_and_saves()  # TODO

        coinpurse = self.get_coinpurse()  # TODO

        resistances = self.get_resistances()  # TODO
        hp = max_hp
        temp_hp = 0  # TODO: not in SRD, implement anyways?

        cvars = {}
        overrides = {}
        death_saves = {}

        if not args.last("nocc"):
            consumables += self.get_custom_counters()  # TODO
        else:
            consumables = []

        spellbook = self.get_spellbook()  # TODO
        live = None  # TODO: implement live character
        race = next((filler['name'] for filler in self._by_type['slotFiller'].values() if 'race' in filler['tags']), None)
        background = None  # TODO
        actions += self.get_actions()

        actions = Actions(actions)

        character = Character(
            owner_id,
            upstream,
            active,
            sheet_type,
            import_version,
            name,
            description,
            image,
            stats,
            levels,
            attacks,
            skills,
            resistances,
            saves,
            ac,
            max_hp,
            hp,
            temp_hp,
            cvars,
            overrides,
            consumables,
            death_saves,
            spellbook,
            live,
            race,
            background,
            actions=actions,
            coinpurse=coinpurse,
        )
        return character

    async def get_character(self):
        """Saves the character JSON data to this object."""
        url = self.url
        character = await DicecloudV2Client.getInstance().get_character(url)
        character["_id"] = url
        self.character_data = character
        return character

    def get_stats(self) -> BaseStats:
        if self.character_data is None:
            raise Exception("You must call get_character() first.")
        if self.stats:
            return self.stats
        stats = (
            "proficiencyBonus",
            "strength",
            "dexterity",
            "constitution",
            "wisdom",
            "intelligence",
            "charisma",
            "armor",
            "hitPoints",
        )
        stat_dict = {
            attr["variableName"]: attr["total"] for attr in self._by_type["attribute"].values() if attr["variableName"] in stats
        }

        stats = BaseStats(
            stat_dict["proficiencyBonus"],
            stat_dict["strength"],
            stat_dict["dexterity"],
            stat_dict["constitution"],
            stat_dict["intelligence"],
            stat_dict["wisdom"],
            stat_dict["charisma"],
        )

        self.stats = stats
        return stat_dict["hitPoints"], stat_dict["armor"], stats

    def get_levels(self) -> Levels:
        """Returns a dict with the character's level and class levels."""
        if self.character_data is None:
            raise Exception("You must call get_character() first.")
        if self.levels:
            return self.levels

        levels = collections.defaultdict(lambda: 0)
        for level in [Class for Class in self._by_type["class"].values()]:
            level_name = level["variableName"].title()
            levels[level_name] += level["level"]

        out = {}
        for level, v in levels.items():
            cleaned_name = re.sub(r"[.$]", "_", level)
            out[cleaned_name] = v

        level_obj = Levels(out)
        self.levels = level_obj
        return level_obj
    
    def get_coinpurse(self):
        return Coinpurse(0, 0, 0, 0, 0)

    def get_attacks(self):  # TODO: finish parser, get resources
        """Returns a list of dicts of all of the character's attacks."""
        if self.character_data is None:
            raise Exception("You must call get_character() first.")
        character = self.character_data
        attacks = AttackList()
        actions = []
        consumables = []
        atk_names = set()
        for attack in self._by_type.get("action", {}).values():
            if not attack.get("inactive"):
                if (g_actions := get_actions_for_name(attack["name"])) and len(g_actions) <= 20:
                    for g_action in g_actions:
                        if g_action.name in self._seen_action_names:
                            continue
                        self._seen_action_names.add(g_action.name)
                        actions.append(
                            Action(
                                name=g_action.name,
                                uid=g_action.uid,
                                id=g_action.id,
                                type_id=g_action.type_id,
                                activation_type=g_action.activation_type,
                            )
                        )
                    continue
                continue #TODO: remove once attack parser is done
                atk = self.parse_attack(attack)

                # unique naming
                atk_num = 2
                if atk.name in atk_names:
                    while f"{atk.name}{atk_num}" in atk_names:
                        atk_num += 1
                    atk.name = f"{atk.name}{atk_num}"
                atk_names.add(atk.name)

                attacks.append(atk)
        return actions, consumables, attacks
    
    def get_skills_and_saves(self) -> (Skills, Saves):
        return Skills.default(self.stats), Saves.default(self.stats)
    
    def get_resistances(self) -> Resistances:
        return Resistances.from_dict({})

    def get_actions(self):
        feature_names = [f.get("name") for f in self._by_type.get("feature", {}).values() if not f.get("inactive")]
        return get_actions_for_names(feature_names)

    def get_custom_counters(self):  # TODO: get counters
        return []
    
    def get_spellbook(self): #TODO: get spellbook
        return Spellbook()

    # helper functions

    # parse attack into automation TODO
    def parse_attack(self, atk_dict) -> Attack:
        """Calculates and returns a dict."""
        if self.character_data is None:
            raise Exception("You must call get_character() first.")

        log.debug(f"Processing attack {atk_dict.get('name')}")

        auto = parse_children(atk_dict)

        name = atk_dict["name"]
        activation = ACTIVATION_DICT[atk_dict["actionType"]]
        attack = Attack(name, auto, activation_type=activation)

        return attack

    def parse_children(prop):
        pass
