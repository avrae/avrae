"""
Created on Nov 08, 2022

@author: lazydope
"""

import collections
import logging
import re

from cogs5e.models.sheet.coinpurse import Coinpurse

from cogs5e.models.character import Character
from cogs5e.models.dicecloud.clientv2 import DicecloudV2Client
from cogs5e.models.dicecloud.errors import DicecloudException, AutoParserException
from cogs5e.models.dicecloud.autoparser import DCV2AutoParser
from cogs5e.models.errors import ExternalImportError
from cogs5e.models.sheet.action import Action, Actions
from cogs5e.models.sheet.attack import Attack, AttackList
from cogs5e.models.sheet.base import BaseStats, Levels, Saves, Skill, Skills
from cogs5e.models.sheet.resistance import Resistances
from cogs5e.models.sheet.spellcasting import Spellbook, SpellbookSpell
from gamedata.compendium import compendium
from utils.constants import DAMAGE_TYPES, SAVE_NAMES, SKILL_NAMES, STAT_NAMES
from utils.functions import search
from utils.enums import ActivationType
from .abc import SHEET_VERSION, SheetLoaderABC
from .utils import get_actions_for_name

log = logging.getLogger(__name__)

API_BASE = "https://dicecloud.com/character/"
DICECLOUDV2_URL_RE = re.compile(r"(?:https?://)?(?:(?:beta|app|www)\.)?dicecloud\.com/character/([\d\w]+)/?")

ACTIVATION_MAP = {
    "action": ActivationType.ACTION,
    "bonus": ActivationType.BONUS_ACTION,
    "attack": None,
    "reaction": ActivationType.REACTION,
    "free": ActivationType.NO_ACTION,
}

RESET_MAP = {
    "shortRest": "short",
    "longRest": "long",
    None: None,
}

ADV_INT_MAP = {-1: False, 0: None, 1: True}

# required stats for any character sheet, we want to ensure these are present
BASE_STATS = (
    "strength",
    "dexterity",
    "constitution",
    "wisdom",
    "intelligence",
    "charisma",
)

STATS = (
    "proficiencyBonus",
    "armor",
    "hitPoints",
)


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

        # grab some stuff from the notes
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

        spellbook, spell_consumables, spell_attacks, spell_actions = self.get_spellbook(slots)
        consumables += spell_consumables
        attacks.extend(spell_attacks)
        actions += spell_actions
        live = None  # TODO: implement live character

        # get race, subrace, and background from slot fillers and notes
        race = None
        subrace = None
        background = None
        for prop in self._by_type["folder"] + self._by_type["feature"] + self._by_type["note"]:
            tags = prop["tags"] + prop.get("libraryTags", [])
            if race is None and "race" in tags:
                race = prop.get("name")
            elif subrace is None and "subrace" in tags:
                subrace = prop.get("name")
            elif background is None and "background" in tags:
                background = prop.get("name")
            if race is not None and subrace is not None and background is not None:
                break

        # defaults if any were still None
        race = race or "Unknown"
        subrace = subrace or ""
        background = background or ""

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

        # keep track of which properties' parents weren't registered by the time we reach them
        orphans = collections.defaultdict(lambda: [])  # :'(
        for prop in self.character_data.get("creatureProperties", []):
            # if a property is marked for removal, skip it
            if prop.get("removed"):
                continue

            # gather information for the keys into the pair of dicts
            prop_type = prop["type"]
            prop_id = prop["_id"]
            self._by_id[prop_id] = prop
            self._by_type[prop_type].append(prop)

            # add an empty list for storing children
            prop["children"] = []

            # assign as child to parent as long as it is not a root property (parent is the character itself)
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

        # assign all orphaned children
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

        # defaults to 0 for any key that isn't pact
        slots = collections.defaultdict(lambda: 0)
        slots["pact"] = {}

        # setup all the collections for the various things attributes track
        stat_dict = {}
        base_checks = {}
        consumables = []

        # we iterate over all attributes here so we don't have to loop over it multiple times
        for attr in self._by_type["attribute"]:
            if attr.get("inactive") or attr.get("overridden"):
                continue
            try:
                # parse basic stats and their checks
                self._parse_stats(attr, stat_dict, base_checks)

                # handle spell slots
                self._parse_slots(attr, slots)

                # assume all resources should be CCs
                self._parse_resources(attr, consumables)

            except ValueError as e:
                raise ExternalImportError(
                    e.args[0].capitalize()
                    + f" for Attribute {attr.get('name') or attr.get('variableName') or attr['_id']}"
                )

        # ensure all the necessary stats were found
        if not all(stat in stat_dict for stat in STATS + BASE_STATS):
            raise ExternalImportError(f"Missing required stats: {', '.join(set(STATS + BASE_STATS) - set(stat_dict))}")

        stats = BaseStats(
            stat_dict["proficiencyBonus"],
            stat_dict["strength"],
            stat_dict["dexterity"],
            stat_dict["constitution"],
            stat_dict["intelligence"],
            stat_dict["wisdom"],
            stat_dict["charisma"],
        )

        # save for later
        self.parsed_attrs = (stat_dict["hitPoints"], stat_dict["armor"], slots, stats, base_checks, consumables)
        return stat_dict["hitPoints"], stat_dict["armor"], slots, stats, base_checks, consumables

    def _parse_stats(self, attr, stat_dict, base_checks):
        try:
            # assign by name to by name dict
            self._attr_by_name[attr["variableName"]] = attr
            attr_name = attr["variableName"]

            # add appropriate base checks if it is an ability score
            if attr_name in BASE_STATS:
                try:
                    base_checks[attr_name] = Skill(int(attr["modifier"]), 0, None)
                except KeyError:
                    raise ExternalImportError(f"Skill {attr_name} is missing a modifier")

            # track the total for all stats
            if attr_name in STATS + BASE_STATS:
                stat_dict[attr_name] = int(attr["total"])

        except KeyError as e:
            if e.args[0] == "variableName":
                pass
            else:
                raise ExternalImportError(f"Attribute {attr_name} missing key {e.args[0]}")

    @staticmethod
    def _parse_slots(attr, slots):
        if attr["attributeType"] == "spellSlot":
            try:
                if attr.get("variableName") == "pactSlot":
                    slots["pact"] = {
                        "num": int(attr["total"]),
                        "level": int(attr["spellSlotLevel"]["value"]),
                    }
                slots[str(attr["spellSlotLevel"]["value"])] += int(attr["total"])
            except KeyError as e:
                if e.args[0] == "spellSlotLevel":
                    raise ExternalImportError(f"{get_ident(attr)} is missing a spell level")
                raise

    def _parse_resources(self, attr, consumables):
        if attr["attributeType"] == "resource":
            # add all resources
            name = get_ident(attr, incl_id=False)
            log.debug(f"Found resource named: {name}")
            if name is None:
                raise ExternalImportError(f"Resource {attr['_id']} is missing a name")
            self._seen_consumables.add(attr["_id"])
            try:
                uses = int(attr["total"])
            except KeyError:
                raise ExternalImportError(f"Resource {name} is missing a maximum value")

            # 7 was too small so 10 instead
            display_type = "bubble" if uses < 10 else None
            consumables.append({
                "name": name,
                "value": int(attr.get("value", uses)),
                "minv": "0",
                "maxv": str(uses),
                "reset": RESET_MAP.get(attr.get("reset")),
                "display_type": display_type,
            })

    def get_levels(self) -> Levels:
        """Returns a dict with the character's level and class levels."""
        if self.character_data is None:
            raise Exception("You must call get_character() first.")
        if self.levels:
            return self.levels

        # setup a default dict for collecting class levels
        levels = collections.defaultdict(lambda: 0)
        for level in self._by_type["class"]:
            try:
                var_name = level["variableName"]
                # BloodHunter rather than bloodHunter
                level_name = var_name[0].upper() + var_name[1:]
                levels[level_name] += level["level"]
            except KeyError as e:
                raise ExternalImportError(f"Class {level.get('name', 'Unnamed')} is missing key {e.args[0]}")

        try:
            total_level = self.character_data["creatureVariables"][0]["level"]["value"]
        except (IndexError, KeyError):
            total_level = None

        level_obj = Levels(levels, total_level)
        self.levels = level_obj
        return level_obj

    def get_coinpurse(self):
        """Due to the format of the coin handling in DiceCloud, this is going to be slightly messy."""
        if self.character_data is None:
            raise Exception("You must call get_character() first.")
        if self.coinpurse:
            return self.coinpurse

        # define all the coin types right away
        coins = {"pp": 0, "gp": 0, "ep": 0, "sp": 0, "cp": 0}

        # checks all items, adding to count if it matches a coin type
        for i in self._by_type["item"]:
            try:
                if re.fullmatch(
                    r"^((plat(inum)?|gold|electrum|silver|copper)( coins?| pieces?)?|(pp|gp|ep|sp|cp))",
                    i["name"],
                    re.IGNORECASE,
                ):
                    coins[i["name"][0].lower() + "p"] += int(i["quantity"])
            except KeyError:
                continue

        coinpurse = Coinpurse(pp=coins["pp"], gp=coins["gp"], ep=coins["ep"], sp=coins["sp"], cp=coins["cp"])
        self.coinpurse = coinpurse

        return coinpurse

    def get_attacks(self):
        """Returns a list of dicts of all of the character's attacks."""
        if self.character_data is None:
            raise Exception("You must call get_character() first.")

        # initialize collections
        attacks = AttackList()
        actions = []
        consumables = []
        for attack in self._by_type["action"]:
            tags = attack["tags"] + attack.get("libraryTags", [])
            # we don't want to parse inactive actions
            if not attack.get("inactive") and "avrae:no_import" not in tags:
                try:
                    aname = attack["name"]
                except KeyError:
                    continue

                log.debug(f"Parsing {aname}")
                # convert uses into consumable format
                if attack.get("uses"):
                    uses = attack["uses"]["value"]
                    display_type = "bubble" if uses < 10 else None
                    consumables.append({
                        "name": aname,
                        "value": attack.get("usesLeft", uses),
                        "minv": "0",
                        "maxv": str(uses),
                        "reset": RESET_MAP.get(attack.get("reset")),
                        "display_type": display_type,
                    })

                consumables += self._consumables_from_resources(attack["resources"])

                # don't bother parsing if a compendium action is found
                if "avrae:parse_only" not in tags and (atk_actions := self.persist_actions_for_name(aname)):
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

        # we don't define skills here because we already started with base skills when parsing attributes
        saves = {}

        # calculate skills and saves from skill properties
        for skill in self._by_type["skill"]:
            if not skill.get("inactive") and skill["skillType"] in ("skill", "save", "check"):
                vname = skill.get("variableName")
                if not vname:
                    continue
                skill_obj = Skill(
                    # proficiency can be 0.49 or 0.5 for half round down or up, but we just want 0.5
                    skill["value"],
                    prof=round(skill["proficiency"], 1),
                    adv=ADV_INT_MAP[skill.get("advantage", 0)],
                )
                match skill["skillType"]:
                    case "save":
                        if vname in SAVE_NAMES:
                            saves[vname] = skill_obj
                    case "skill" | "check":
                        if vname in SKILL_NAMES:
                            skills[vname] = skill_obj

        if missing_skills := set(SKILL_NAMES) - set(skills):
            raise ExternalImportError(
                f"Your sheet is missing the following skill{'s' if len(missing_skills)>1 else ''}:"
                f" {', '.join(missing_skills)}"
            )
        if missing_saves := set(SAVE_NAMES) - set(saves):
            raise ExternalImportError(
                f"Your sheet is missing the following save{'s' if len(missing_saves)>1 else ''}:"
                f" {', '.join(missing_saves)}"
            )

        return Skills(skills), Saves(saves)

    def get_resistances(self) -> Resistances:
        if self.character_data is None:
            raise Exception("You must call get_character() first.")

        # only unqiue resistances pls
        out = {"resist": set(), "immune": set(), "vuln": set()}

        for dmg_mult in self._by_type["damageMultiplier"]:
            if not dmg_mult.get("inactive"):
                # each resistance property can give multiple resistances
                for dmg_type in dmg_mult["damageTypes"]:
                    if dmg_type in DAMAGE_TYPES:
                        for exclude in dmg_mult.get("excludeTags", []):
                            dmg_type = f"non{exclude} {dmg_type}"
                        for include in dmg_mult.get("includeTags", []):
                            dmg_type = f"{include} {dmg_type}"
                        # if we're immune, nothing else matters
                        if dmg_type in out["immune"]:
                            continue
                        mult = dmg_mult["value"]
                        if mult <= 0:
                            # if it turns out we're immune, discard the others
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
            if not f.get("inactive") and "avrae:no_import" not in f["tags"] + f.get("libraryTags", []):
                actions += self.persist_actions_for_name(f.get("name"))

        return actions

    def get_custom_counters(self):
        return self._parse_attributes()[5]

    def get_spellbook(self, slots):
        if self.character_data is None:
            raise Exception("You must call get_character() first.")

        pact = slots.pop("pact") if "pact" in slots else {}

        spell_lists = {}  # list_id: (name, ab, dc, scam)
        for sl in self._by_type["spellList"]:
            ab = sl.get("attackRollBonus", {})
            ab_calc = ab.get("calculation", "").lower()
            ab_val = ab.get("value")
            dc = sl.get("dc", {}).get("value")
            try:
                scam = self.get_stats().get_mod(next(m for m in STAT_NAMES if m in ab_calc))
            except StopIteration:
                scam = None
            spell_lists[sl["_id"]] = (sl.get("name"), ab_val, dc, scam)

        log.debug(f"Got spell lists: {spell_lists}")

        # we got lots of stuff going on with spells, so lots of collections
        spells = []
        consumables = []
        sabs = []
        dcs = []
        mods = []
        attacks = []
        actions = []

        for spell in self._by_type["spell"]:
            if "avrae:no_import" in spell["tags"] + spell.get("libraryTags", []):
                continue

            # an unnamed spell is not parsable
            if "name" not in spell:
                continue

            # unprepared spells are inactive, so we need to specifically check how it is deactivated
            if spell.get("deactivatedByAncestor") or spell.get("deactivatedByToggle"):
                continue

            spell_actions = self.persist_actions_for_name(spell["name"])
            actions += spell_actions
            log.debug(f"Got spell with ancestors: {[spell['parent']['id']] + [k['id'] for k in spell['ancestors']]}")

            # find the matching spell list, trying the direct parent first, then ancestors
            sl_name, spell_ab, spell_dc, spell_mod = spell_lists.get(spell["parent"]["id"]) or next(
                (
                    spell_lists[k["id"]]
                    for k in spell["ancestors"]
                    if k["collection"] == "creatureProperties" and k["id"] in spell_lists
                ),
                (None, None, None, None),
            )
            spell["spellListName"] = sl_name

            # we need to keep track of consumables per spell so we know if a free use action is needed
            spell_consumables = []

            if "uses" in spell:
                uses = spell["uses"]["value"]
                display_type = "bubble" if uses < 10 else None
                action_name = f"{sl_name}: {spell['name']}" if sl_name else spell["name"]
                spell_consumables.append({
                    "name": action_name,
                    "value": spell.get("usesLeft", 0),
                    "minv": "0",
                    "maxv": str(uses),
                    "reset": RESET_MAP.get(spell.get("reset")),
                    "display_type": display_type,
                })

            spell_consumables += self._consumables_from_resources(spell["resources"])
            consumables += spell_consumables

            # shouldn't parse or add to spells if a compendium action was found
            if not spell_actions:
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

                # we only want to track the spell's stats if it's actually prepared
                spell_prepared = spell.get("prepared") or spell.get("alwaysPrepared") or "noprep" in self.args
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
                        SpellbookSpell.from_spell(
                            result, sab=spell_ab, dc=spell_dc, mod=spell_mod, prepared=spell_prepared
                        )
                    )
                else:
                    spells.append(
                        SpellbookSpell(
                            spell["name"].strip(), sab=spell_ab, dc=spell_dc, mod=spell_mod, prepared=spell_prepared
                        )
                    )

        # most common stats are used for the spellbook
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
        # get readable identifier utility
        log.debug(f"Completed parsing spellbook: {spellbook.to_dict()}")

        return spellbook, consumables, attacks, actions

    # helper functions

    # parse attack into automation
    def parse_attack(self, atk_prop) -> Attack:
        """Calculates and returns an Attack given a property."""
        if self.character_data is None:
            raise Exception("You must call get_character() first.")

        log.debug(f"Processing attack {get_ident(atk_prop)}")
        try:
            auto = DCV2AutoParser(self).get_automation(atk_prop)
        except AutoParserException as e:
            node = e.node
            if isinstance(e.__cause__, KeyError):
                raise ExternalImportError(
                    f"{node['type']} {get_ident(node)} in {get_ident(atk_prop)} could not get key {e.__cause__.args[0]}"
                )
            if e.__cause__ is None:
                raise ExternalImportError(
                    f"{node['type']} {get_ident(node)} in {get_ident(atk_prop)} encountered an error: {e.args[0]}"
                )
            raise ExternalImportError(
                f"{node['type']} {get_ident(node)} in {get_ident(atk_prop)} could not import properly due to"
                f" {e.__cause__}"
            ) from e
        if auto is None:
            log.debug("Oops! Automation is None!")

        name = atk_prop["name"]
        verb, proper = (
            ("casts", True)
            if atk_prop["type"] == "spell"
            else ("uses", False) if atk_prop["actionType"] != "attack" else (None, False)
        )
        log.debug(f"Parsing {atk_prop['type']}")
        activation = ACTIVATION_MAP.get(atk_prop["actionType"], ActivationType.SPECIAL)
        attack = Attack(name, auto, verb=verb, proper=proper, activation_type=activation)

        return attack

    def persist_actions_for_name(self, name):
        """
        Since compendium actions can be found in spells, actions, and features, we need to keep track of what we've seen
        """
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
        """Grabs attribute resources from actions/spells and converts them into consumables"""
        attrs = resources["attributesConsumed"]
        consumables = []
        for attr in attrs:
            if "variableName" not in attr:
                continue
            full_attr = self._attr_by_name.get(attr["variableName"])
            if full_attr and full_attr["_id"] not in self._seen_consumables:
                self._seen_consumables.add(full_attr["_id"])
                uses = full_attr["total"]
                display_type = "bubble" if uses < 10 else None
                consumables.append({
                    "name": full_attr["name"],
                    "value": full_attr.get("value", uses),
                    "minv": "0",
                    "maxv": str(uses),
                    "reset": RESET_MAP.get(full_attr.get("reset")),
                    "display_type": display_type,
                })
        return consumables


# get readable identifier utility
def get_ident(attr, *, incl_id=True):
    return attr.get("name") or attr.get("variableName") or (attr["_id"] if incl_id else None)
