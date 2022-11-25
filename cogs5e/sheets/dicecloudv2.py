"""
Created on Nov 08, 2022

@author: lazydope
"""

import collections
import logging
import re
from math import ceil, floor

import draconic
from cogs5e.models.sheet.coinpurse import Coinpurse

from cogs5e.models.character import Character
from cogs5e.models.dicecloud.clientv2 import DicecloudV2Client
from cogs5e.models.dicecloud.errors import DicecloudException
from cogs5e.models.dicecloud.autoparser import DCV2AutoParser
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

log = logging.getLogger(__name__)

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

RESET_DICT = {
    "shortRest": "short",
    "longRest": "long",
    None: None,
}

ADV_INT_MAP = {-1: False, 0: None, 1: True}


class DicecloudV2Parser(SheetLoaderABC):
    def __init__(self, url):
        super(DicecloudV2Parser, self).__init__(url)
        self.parsed_attrs = None
        self.levels = None
        self.args = None
        self.coinpurse = None
        self._by_type = collections.defaultdict(lambda: [])
        self._by_id = {}
        self._seen_action_names = set()
        self._seen_consumables = set()
        self._attr_by_name = {}
        self.atk_names = set()

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
        name = self.character_data["creatures"][0].get("name", "").strip()
        desc_note = next((note for note in self._by_type["note"] if "description" in note.get("name", "").lower()), {})
        description = desc_note.get("summary", {}).get("value", "") or desc_note.get("description", {}).get("value", "")
        image = self.character_data["creatures"][0].get("picture", "")

        max_hp, ac, slots, stats, base_checks, consumables = self._parse_attributes()
        levels = self.get_levels()
        actions, attack_consumables, attacks = self.get_attacks()
        consumables += attack_consumables

        skills, saves = self.get_skills_and_saves(base_checks)

        coinpurse = self.get_coinpurse()

        resistances = self.get_resistances()
        hp = max_hp
        temp_hp = 0

        cvars = {}
        overrides = {}
        death_saves = {}

        if args.last("nocc"):
            consumables = []

        spellbook, spell_consumables, spell_attacks = self.get_spellbook(slots)
        consumables += spell_consumables
        attacks.extend(spell_attacks)
        live = None  # TODO: implement live character
        race = "Unknown"
        subrace = ""
        background = ""
        filled = 0
        for filler in self._by_type["slotFiller"]:
            if race == "Unknown" and "race" in filler["tags"]:
                race = filler["name"]
                filled += 1
            elif not subrace and "subrace" in filler["tags"]:
                subrace = filler["name"]
                filled += 1
            elif not background and "background" in filler["tags"]:
                background = filler["name"]
                filled += 1
            if filled == 3:
                break
        if subrace and race in subrace:
            race = subrace
        elif subrace:
            race = subrace + " " + race

        actions += self.get_actions()

        actions = Actions(actions)

        log.debug(f"Parsed character: {name}")

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

        orphans = collections.defaultdict(lambda: [])  # :'(
        for prop in self.character_data["creatureProperties"]:
            if prop.get("removed"):
                continue
            prop_type = prop["type"]
            prop_id = prop["_id"]
            prop["children"] = []
            self._by_id[prop_id] = prop
            self._by_type[prop_type].append(prop)
            if prop["parent"]["id"] != self.url:
                log.debug(
                    "Parent for"
                    f" {prop.get('name') or prop.get('variableName') or (prop.get('damageType') or '') + prop['type']} ({prop['type']},"
                    f" {prop_id}): {prop['parent']['id']}"
                )
                if prop["parent"]["id"] in self._by_id:
                    self._by_id[prop["parent"]["id"]]["children"].append(prop_id)
                else:
                    orphans[prop["parent"]["id"]].append(prop_id)
                    log.debug(f"Oops, {prop.get('name') or prop.get('variableName') or prop['_id']} was ophaned!")

        for prop_id, children in orphans.items():
            if prop_id in self._by_id:
                self._by_id[prop_id]["children"].extend(children)
            else:
                log.debug(f"Oops, {prop.get('name') or prop.get('variableName') or prop['_id']} was still ophaned!")

        return character

    def get_stats(self) -> BaseStats:
        return self._parse_attributes()[3]

    def _parse_attributes(self) -> (int, int, {str: int}, BaseStats, [Skill], [dict]):
        if self.character_data is None:
            raise Exception("You must call get_character() first.")
        if self.parsed_attrs:
            return self.parsed_attrs
        base_stats = (
            "strength",
            "dexterity",
            "constitution",
            "wisdom",
            "intelligence",
            "charisma",
        )

        stats = (
            "proficiencyBonus",
            "armor",
            "hitPoints",
        )

        slots = {str(i): 0 for i in range(1, 10)} | {"pact": {}}
        stat_dict = {}
        base_checks = {}
        consumables = []
        try:
            for attr in self._by_type["attribute"]:
                if not attr.get("inactive"):
                    self._attr_by_name[attr["variableName"]] = attr
                    attr_name = attr["variableName"]
                    if attr_name in base_stats:
                        base_checks[attr_name] = Skill(attr["modifier"], 0, None)
                    if attr_name in stats + base_stats:
                        stat_dict[attr_name] = attr["total"]
                    if attr["attributeType"] == "spellSlot":
                        if attr["variableName"] == "pactSlot":
                            slots["pact"] = {"num": attr["total"], "level": attr["spellSlotLevel"]["value"]}
                        else:
                            slots[str(attr["spellSlotLevel"]["value"])] += attr["total"]
                    if attr["attributeType"] == "resource":
                        log.debug(f"Found resource named: {attr['name']}")
                        self._seen_consumables.add(attr["_id"])
                        uses = attr["total"]
                        display_type = "bubble" if uses < 30 else None
                        consumables.append(
                            {
                                "name": attr["name"],
                                "value": attr.get("value", uses),
                                "minv": "0",
                                "maxv": str(uses),
                                "reset": RESET_DICT[attr.get("reset")],
                                "display_type": display_type,
                            }
                        )

        except KeyError as e:
            if e.args[0] == "total":
                raise ExternalImportError(f"{attr_name} is missing a spell count")
            elif e.args[0] == "value":
                raise ExternalImportError(f"{attr_name} is missing a spell level")
            raise ExternalImportError("Importing stats caused an error") from e

        if not all(stat in stat_dict for stat in stats):
            raise ExternalImportError(f"Missing required stats: {[stat for stat in stats if stat not in stat_dict]}")

        stats = BaseStats(
            stat_dict["proficiencyBonus"],
            stat_dict["strength"],
            stat_dict["dexterity"],
            stat_dict["constitution"],
            stat_dict["intelligence"],
            stat_dict["wisdom"],
            stat_dict["charisma"],
        )

        self.parsed_attrs = (stat_dict["hitPoints"], stat_dict["armor"], slots, stats, base_checks, consumables)
        return stat_dict["hitPoints"], stat_dict["armor"], slots, stats, base_checks, consumables

    def get_levels(self) -> Levels:
        """Returns a dict with the character's level and class levels."""
        if self.character_data is None:
            raise Exception("You must call get_character() first.")
        if self.levels:
            return self.levels

        levels = collections.defaultdict(lambda: 0)
        for level in [Class for Class in self._by_type["class"]]:
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
        """Due to the format of the coin handling in DiceCloud, this is going to be slightly messy."""
        if self.character_data is None:
            raise Exception("You must call get_character() first.")
        if self.coinpurse:
            return self.coinpurse

        coins = {"pp": 0, "gp": 0, "ep": 0, "sp": 0, "cp": 0}

        for i in self._by_type["item"]:
            if re.fullmatch(
                r"^((plat(inum)?|gold|electrum|silver|copper)( coins?| pieces?)?|(pp|gp|ep|sp|cp))",
                i["name"],
                re.IGNORECASE,
            ):
                coins[i["name"][0].lower() + "p"] += int(i["quantity"])

        coinpurse = Coinpurse(pp=coins["pp"], gp=coins["gp"], ep=coins["ep"], sp=coins["sp"], cp=coins["cp"])
        self.coinpurse = coinpurse

        return coinpurse

    def get_attacks(self):  # TODO: finish parser, get resources
        """Returns a list of dicts of all of the character's attacks."""
        if self.character_data is None:
            raise Exception("You must call get_character() first.")
        character = self.character_data
        attacks = AttackList()
        actions = []
        consumables = []
        for attack in self._by_type["action"]:
            if not attack.get("inactive"):
                aname = attack["name"]
                if attack.get("uses", None):
                    uses = attack["uses"]["value"]
                    display_type = "bubble" if uses < 30 else None
                    consumables.append(
                        {
                            "name": aname,
                            "value": attack.get("usesLeft", uses),
                            "minv": "0",
                            "maxv": str(uses),
                            "reset": RESET_DICT[attack.get("reset")],
                            "display_type": display_type,
                        }
                    )
                consumables += self._consumables_from_resources(attack["resources"])

                if atk_actions := self.persist_actions_for_name(aname):
                    actions += atk_actions
                    continue
                atk = self.parse_attack(attack)

                # unique naming
                atk_num = 2
                if atk.name in self.atk_names:
                    while f"{atk.name} {atk_num}" in self.atk_names:
                        atk_num += 1
                    atk.name = f"{atk.name} {atk_num}"
                self.atk_names.add(atk.name)

                attacks.append(atk)
        return actions, consumables, attacks

    def get_skills_and_saves(self, skills) -> (Skills, Saves):
        if self.character_data is None:
            raise Exception("You must call get_character() first.")

        saves = {}

        # calculate skills and saves from skill properties
        for skill in self._by_type["skill"]:
            if not skill.get("inactive"):
                vname = skill["variableName"]
                skill_obj = Skill(skill["value"], prof=skill["proficiency"], adv=ADV_INT_MAP[skill.get("advantage", 0)])
                match skill["skillType"]:
                    case "save":
                        if vname in SAVE_NAMES:
                            saves[vname] = skill_obj
                    case "skill" | "check":
                        if vname in SKILL_NAMES:
                            skills[vname] = skill_obj

        return Skills(skills), Saves(saves)

    def get_resistances(self) -> Resistances:
        if self.character_data is None:
            raise Exception("You must call get_character() first.")
        out = {"resist": set(), "immune": set(), "vuln": set()}
        for dmg_mult in self._by_type["damageMultiplier"]:
            if not dmg_mult.get("inactive"):
                for dmg_type in dmg_mult["damageTypes"]:
                    if dmg_type in DAMAGE_TYPES:
                        if dmg_type in out["immune"]:
                            continue
                        mult = dmg_mult["value"]
                        if mult <= 0:
                            out["immune"].add(dmg_type)
                            out["resist"].discard(dmg_type)
                            out["vuln"].discard(dmg_type)
                        elif mult < 1:
                            out["resist"].add(dmg_type)
                        elif mult > 1:
                            out["vuln"].add(dmg_type)

        return Resistances.from_dict(out)

    def get_actions(self):
        actions = []
        for f in self._by_type["feature"]:
            if not f.get("inactive"):
                actions += self.persist_actions_for_name(f.get("name"))

        return actions

    def get_custom_counters(self):  # TODO: get counters
        return []

    def get_spellbook(self, slots):  # TODO: get spellbook
        if self.character_data is None:
            raise Exception("You must call get_character() first.")

        pact = slots.pop("pact") if "pact" in slots else {}

        spell_lists = {}  # list_id: (name, ab, dc, scam)
        for sl in self._by_type["spellList"]:
            try:
                ab = sl.get("attackRollBonus", {})
                ab_calc = ab.get("calculation", "").lower()
                ab_val = ab.get("value")
                dc = sl.get("dc", {}).get("value")
                try:
                    scam = self.get_stats().get_mod(next(m for m in STAT_NAMES if m in ab_calc))
                except StopIteration:
                    scam = None
                spell_lists[sl["_id"]] = (sl.get("name"), ab_val, dc, scam)
            except:
                pass

        log.debug(f"Got spell lists: {spell_lists}")

        spells = []
        consumables = []
        sabs = []
        dcs = []
        mods = []
        attacks = []
        for spell in self._by_type["spell"]:
            spell_consumables = []
            log.debug(f"Got spell with ancestors: {[spell['parent']['id']] + [k['id'] for k in spell['ancestors']]}")
            sl_name, spell_ab, spell_dc, spell_mod = spell_lists.get(spell["parent"]["id"]) or next(
                (
                    spell_lists[k["id"]]
                    for k in spell["ancestors"]
                    if k["collection"] == "creatureProperties" and k["id"] in spell_lists
                ),
                (None, None, None, None),
            )
            spell["spellListName"] = sl_name
            spell_prepared = spell.get("prepared") or spell.get("alwaysPrepared") or "noprep" in self.args

            if "uses" in spell:
                uses = spell["uses"]["value"]
                display_type = "bubble" if uses < 30 else None
                action_name = f"{sl_name}: {spell['name']}" if sl_name else spell["name"]
                spell_consumables.append(
                    {
                        "name": action_name,
                        "value": spell.get("usesLeft", 0),
                        "minv": "0",
                        "maxv": str(uses),
                        "reset": RESET_DICT[spell.get("reset")],
                        "display_type": display_type,
                    }
                )

            spell_consumables += self._consumables_from_resources(spell["resources"])

            if spell_consumables:
                atk = self.parse_attack(spell)

                # unique naming
                atk_num = 2
                if atk.name in self.atk_names:
                    while f"{atk.name} {atk_num}" in self.atk_names:
                        atk_num += 1
                    atk.name = f"{atk.name} {atk_num}"
                self.atk_names.add(atk.name)

                attacks.append(atk)

            consumables += spell_consumables

            if spell_prepared:
                if spell_ab is not None:
                    sabs.append(spell_ab)
                if spell_dc is not None:
                    dcs.append(spell_dc)
                if spell_mod is not None:
                    mods.append(spell_mod)

            result, strict = search(compendium.spells, spell["name"].strip(), lambda sp: sp.name, strict=True)
            if result and strict:
                spells.append(
                    SpellbookSpell.from_spell(result, sab=spell_ab, dc=spell_dc, mod=spell_mod, prepared=spell_prepared)
                )
            else:
                spells.append(
                    SpellbookSpell(
                        spell["name"].strip(), sab=spell_ab, dc=spell_dc, mod=spell_mod, prepared=spell_prepared
                    )
                )

        dc = max(dcs, key=dcs.count, default=None)
        sab = max(sabs, key=sabs.count, default=None)
        smod = max(mods, key=mods.count, default=None)

        spellbook = Spellbook(
            slots,
            slots,
            spells,
            dc,
            sab,
            self.get_levels().total_level,
            smod,
            pact.get("level"),
            pact.get("num"),
            pact.get("num"),
        )

        log.debug(f"Completed parsing spellbook: {spellbook.to_dict()}")

        return spellbook, consumables, attacks

    # helper functions

    # parse attack into automation
    def parse_attack(self, atk_prop) -> Attack:
        """Calculates and returns an Attack given a property."""
        if self.character_data is None:
            raise Exception("You must call get_character() first.")

        log.debug(f"Processing attack {atk_prop.get('name')}")
        auto = DCV2AutoParser(self).get_automation(atk_prop)
        if auto is None:
            log.debug(f"Oops! Automation is None!")

        name = atk_prop["name"]
        activation = ACTIVATION_DICT[atk_prop["actionType"]]
        attack = Attack(name, auto, activation_type=activation)

        return attack

    def persist_actions_for_name(self, name):
        actions = []
        if (g_actions := get_actions_for_name(name)) and len(g_actions) <= 20:
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
        return actions

    def _consumables_from_resources(self, resources):
        attrs = resources["attributesConsumed"]
        consumables = []
        for attr in attrs:
            full_attr = self._attr_by_name[attr["variableName"]]
            if full_attr["_id"] not in self._seen_consumables:
                self._seen_consumables.add(full_attr["_id"])
                uses = full_attr["total"]
                display_type = "bubble" if uses < 30 else None
                consumables.append(
                    {
                        "name": full_attr["name"],
                        "value": full_attr.get("value", uses),
                        "minv": "0",
                        "maxv": str(uses),
                        "reset": RESET_DICT[full_attr.get("reset")],
                        "display_type": display_type,
                    }
                )
        return consumables
