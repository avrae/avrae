"""
Created on May 26, 2020

@author: andrew
"""

import itertools
import logging
import re

import aiohttp
from markdownify import markdownify

import gamedata
from cogs5e.models import automation
from cogs5e.models.character import Character
from cogs5e.models.errors import ExternalImportError
from cogs5e.models.sheet.action import Action, Actions
from cogs5e.models.sheet.coinpurse import Coinpurse
from cogs5e.models.sheet.attack import Attack, AttackList
from cogs5e.models.sheet.base import BaseStats, Levels, Saves, Skill, Skills
from cogs5e.models.sheet.player import CustomCounter
from cogs5e.models.sheet.resistance import Resistances
from cogs5e.models.sheet.spellcasting import Spellbook, SpellbookSpell
from cogs5e.sheets.abc import SHEET_VERSION, SheetLoaderABC
from gamedata.compendium import compendium
from utils import config, constants, enums
from utils.enums import ActivationType
from utils.functions import smart_trim

log = logging.getLogger(__name__)

ENDPOINT = config.DDB_CHAR_COMPUTATION_ENDPT
if config.ENVIRONMENT in ("development", "staging"):
    urls = r"stg\.dndbeyond\.com|www\.dndbeyond\.com|ddb\.ac"
else:
    urls = r"www\.dndbeyond\.com|ddb\.ac"

DDB_URL_RE = re.compile(rf"(?:https?://)?(?:{urls})(?:/profile/.+)?/characters/(\d+)(?:/)?")
DDB_PDF_URL_RE = re.compile(rf"(?:https?://)?(?:{urls})/sheet-pdfs/.+_(\d+).pdf")
SKILL_MAP = {
    "3": "acrobatics",
    "11": "animalHandling",
    "6": "arcana",
    "2": "athletics",
    "16": "deception",
    "7": "history",
    "12": "insight",
    "17": "intimidation",
    "8": "investigation",
    "13": "medicine",
    "9": "nature",
    "14": "perception",
    "18": "performance",
    "19": "persuasion",
    "10": "religion",
    "4": "sleightOfHand",
    "5": "stealth",
    "15": "survival",
}
RESET_MAP = {1: "short", 2: "long", 3: "long", 4: "none"}


class BeyondSheetParser(SheetLoaderABC):
    def __init__(self, charId):
        super(BeyondSheetParser, self).__init__(charId)
        self.ctx = None
        self.args = None
        self._is_live = None

    async def load_character(self, ctx, args):
        """
        Downloads and parses the character data, returning a fully-formed Character object.
        :raises ExternalImportError if something went wrong during the import that we can expect
        :raises Exception if something weirder happened
        """
        self.ctx = ctx
        self.args = args

        owner_id = str(ctx.author.id)
        await self._get_character()

        upstream = f"beyond-{self.url}"
        active = False
        sheet_type = "beyond"
        import_version = SHEET_VERSION
        name = self.character_data["name"].strip()
        description = self.character_data["description"]
        image = self.character_data["image"] or ""

        stats = self._get_stats()
        levels = self._get_levels()
        skills = self._get_skills()
        saves = self._get_saves()
        # we do this to handle the attack/action overlap (e.g. actions with displayAsAttack)
        attacks, actions = self._get_attacks_and_actions()

        resistances = self._get_resistances()
        ac = self._get_ac()
        max_hp, hp, temp_hp = self._get_hp()

        cvars = {}
        overrides = {}
        death_saves = {}

        consumables = []
        if not args.last("nocc"):
            consumables = self._get_custom_counters()

        spellbook = self._get_spellbook()
        live = "beyond" if self._is_live else None
        race = self._get_race()
        background = self._get_background()
        coinpurse = self._get_purse()

        # ddb campaign
        campaign = self.character_data.get("campaign")
        campaign_id = None
        if campaign is not None:
            campaign_id = str(campaign["id"])

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
            ddb_campaign_id=campaign_id,
            actions=actions,
            coinpurse=coinpurse,
        )
        return character

    async def _get_character(self):
        char_id = self.url
        character = None
        headers = {}

        ddb_user = await self.ctx.bot.ddb.get_ddb_user(self.ctx, self.ctx.author.id)
        if ddb_user is not None:
            headers = {"Authorization": f"Bearer {ddb_user.token}"}

        async with aiohttp.ClientSession() as session:
            async with session.get(f"{ENDPOINT}{char_id}", headers=headers) as resp:
                log.debug(f"DDB returned {resp.status}")
                if resp.status == 200:
                    character = await resp.json()
                elif resp.status == 403:
                    if ddb_user is None:
                        raise ExternalImportError(
                            "This character is private. Link your D&D Beyond and Discord accounts to import it!"
                        )
                    else:
                        raise ExternalImportError("You do not have permission to view this character.")
                elif resp.status == 404:
                    raise ExternalImportError(
                        "This character does not exist, or you do not have access to it. Are you using the right link?"
                    )
                elif resp.status == 429:
                    raise ExternalImportError(
                        "Too many people are trying to import characters! Please try again in a few minutes."
                    )
                else:
                    raise ExternalImportError(f"Beyond returned an error: {resp.status} - {resp.reason}")

        character["_id"] = char_id
        self.character_data = character
        self._is_live = (ddb_user is not None) and (ddb_user.user_id == str(character["ownerId"]))
        log.debug(character)
        return character

    def _get_stats(self) -> BaseStats:
        """Returns a dict of stats."""
        c = self.character_data
        stats = BaseStats(
            c["proficiencyBonus"],
            c["stats"]["str"]["score"],
            c["stats"]["dex"]["score"],
            c["stats"]["con"]["score"],
            c["stats"]["int"]["score"],
            c["stats"]["wis"]["score"],
            c["stats"]["cha"]["score"],
        )
        return stats

    def _get_levels(self) -> Levels:
        """Returns a dict with the character's level and class levels."""
        out = {}
        for klass in self.character_data["classes"]:
            cleaned_name = re.sub(r"[.$]", "_", klass["name"])
            out[cleaned_name] = klass["level"]

        return Levels(out)

    def _get_skills(self) -> Skills:
        out = {}

        # main skills
        for skill_id, skill in self.character_data["skills"].items():
            prof_type = {1: 0, 2: 0.5, 3: 1, 4: 2}.get(skill["prof"], 0)
            adv_type = derive_adv(skill["adv"], skill["dis"])
            out[SKILL_MAP[skill_id]] = Skill(skill["modifier"], prof_type, skill["bonus"], adv_type)

        # initiative
        out["initiative"] = Skill(
            self.character_data["initiative"]["modifier"], adv=self.character_data["initiative"]["adv"] or None
        )

        # ability skills (base strength, dex, etc checks)
        for stat_key, skill in zip(constants.STAT_ABBREVIATIONS, constants.STAT_NAMES):
            stat_obj = self.character_data["stats"][stat_key]
            prof_type = {1: 0, 2: 0.5, 3: 1, 4: 2}.get(stat_obj["modifierProficiency"], 0)
            out[skill] = Skill(stat_obj["modifier"], prof_type)

        return Skills(out)

    def _get_saves(self) -> Saves:
        out = {}
        for stat_key, save_key in zip(constants.STAT_ABBREVIATIONS, constants.SAVE_NAMES):
            stat_data = self.character_data["stats"][stat_key]
            adv_type = derive_adv(stat_data["saveAdv"], stat_data["saveDis"])
            out[save_key] = Skill(stat_data["save"], prof=1 if stat_data["saveProficiency"] else 0, adv=adv_type)

        return Saves(out)

    def _get_resistances(self):
        return Resistances.from_dict(self.character_data["resistances"])

    def _get_ac(self):
        return self.character_data["ac"]

    def _get_hp(self):
        hp_obj = self.character_data["hp"]
        return hp_obj["max"], hp_obj["current"], hp_obj["temp"]

    def _get_spellbook(self):
        spellbook = self.character_data["spellbook"]

        max_slots = {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0, "6": 0, "7": 0, "8": 0, "9": 0}
        slots = {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0, "6": 0, "7": 0, "8": 0, "9": 0}
        for slot in spellbook["slots"]:
            slots[str(slot["level"])] = slot["remaining"]
            max_slots[str(slot["level"])] = slot["available"]

        dcs = []
        sabs = []
        mods = []
        spells = []

        for spell in spellbook["spells"]:
            spell_ab = spell["sab"]
            spell_dc = spell["dc"]
            spell_mod = spell["mod"]
            spell_prepared = spell["prepared"] or "noprep" in self.args
            if spell_ab is not None:
                sabs.append(spell_ab)
            if spell_dc is not None:
                dcs.append(spell_dc)
            if spell_mod is not None:
                mods.append(spell_mod)

            result = compendium.lookup_entity(gamedata.Spell.entity_type, spell["id"])

            if result:
                if result.name not in [spell.name for spell in spells]:
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

        dc = max(dcs, key=dcs.count, default=None)
        sab = max(sabs, key=sabs.count, default=None)
        smod = max(mods, key=mods.count, default=None)

        # assumption: a character will only ever have one pact slot level, with a given number of slots of that level
        pact_slot_level = None
        num_pact_slots = None
        max_pact_slots = None
        if spellbook["pactSlots"]:
            pact_info = spellbook["pactSlots"][0]
            pact_slot_level = pact_info["level"]
            max_pact_slots = pact_info["available"]
            num_pact_slots = max_pact_slots - pact_info["used"]

        return Spellbook(
            slots,
            max_slots,
            spells,
            dc,
            sab,
            self._get_levels().total_level,
            smod,
            pact_slot_level=pact_slot_level,
            num_pact_slots=num_pact_slots,
            max_pact_slots=max_pact_slots,
        )

    def _get_custom_counters(self):
        out = []

        for cons in self.character_data["consumables"]:
            live_id = f"{cons['id']}-{cons['typeId']}"
            display_type = "bubble" if cons["max"] < 7 else None
            reset = RESET_MAP.get(cons["reset"], "long")
            name = cons["name"].replace("\u2019", "'").strip()
            desc = None
            source_feature_type = cons["sourceFeatureType"]
            source_feature_id = cons["sourceFeatureId"]

            if cons["desc"] is not None:
                desc = smart_trim(html_to_md(cons["desc"].replace("\u2019", "'")))

            source_feature = compendium.lookup_entity(source_feature_type, source_feature_id)
            log.debug(f"Processed counter named {name!r} for feature {source_feature}")

            if source_feature is None:
                log.warning(
                    f"Could not find source feature ({source_feature_type}, {source_feature_id}) for counter "
                    f"named {name!r}"
                )

            if cons["max"] and name:  # don't make counters with a range of 0 - 0, or blank named counters
                out.append(
                    CustomCounter(
                        None,
                        name,
                        cons["value"],
                        minv="0",
                        maxv=str(cons["max"]),
                        reset=reset,
                        display_type=display_type,
                        live_id=live_id,
                        desc=desc,
                        ddb_source_feature_type=source_feature_type,
                        ddb_source_feature_id=source_feature_id,
                    )
                )

        return [cc.to_dict() for cc in out]

    def _get_race(self):
        return self.character_data["race"]

    def _get_background(self):
        return self.character_data["background"]

    def _get_purse(self) -> Coinpurse:
        """Returns the Currency values."""
        coins = Coinpurse(
            pp=self.character_data["currencies"]["pp"],
            gp=self.character_data["currencies"]["gp"],
            ep=self.character_data["currencies"]["ep"],
            sp=self.character_data["currencies"]["sp"],
            cp=self.character_data["currencies"]["cp"],
        )
        return coins

    def _get_attacks_and_actions(self):
        """
        :rtype: tuple[AttackList, Actions]
        """
        attacks = self._process_attacks()  # this returns all attacks regardless of their status
        actions, action_grantor_ids = self._process_actions()  # this skips customized actions with displayAsAttack

        filtered_attacks = [attack for ((id, type_id), attack) in attacks if (id, type_id) not in action_grantor_ids]

        return AttackList(filtered_attacks), actions

    def _process_attacks(self):
        """
        :return: list of pairs ((id, typeId), attack)
        :rtype: list[tuple[tuple[str, str], Attack]]
        """
        attacks = []
        used_names = set()

        def append(processed_attack, attack_data):
            if processed_attack.name in used_names:
                num = 2
                while f"{processed_attack.name}{num}" in used_names:
                    num += 1
                processed_attack.name = f"{processed_attack.name} {num}"
            attacks.append(((str(attack_data["id"]), str(attack_data["typeId"])), processed_attack))
            used_names.add(processed_attack.name)

        for attack in self.character_data["attacks"]:
            append(self._transform_attack(attack), attack)

        return attacks

    def _process_actions(self):
        """
        :return: a pair (actions, action ids that granted valid actions (id, typeid))
        :rtype: tuple[Actions, set[tuple[str, str]]]
        """
        character_actions = self.character_data["actions"]
        character_features = self.character_data["features"]
        actions = []
        seen_feature_ids = set()  # set of tuples (typeid, id)
        action_ids_with_valid_actions = set()  # set of tuples (id, typeid)

        def add_action_from_gamedata(d_action, g_action):
            name = g_action.name
            if d_action.get("isCustomized") and d_action["name"] != g_action.name:
                # custom name handler: steal any parenthetical from the canonical name and tack it on to the custom name
                name = d_action["name"]
                g_name_parenthetical = re.search(r"\(.+\)$", g_action.name)
                if g_name_parenthetical:
                    name = f"{name} {g_name_parenthetical.group(0)}"

            actions.append(
                Action(
                    name=name,
                    uid=g_action.uid,
                    id=g_action.id,
                    type_id=g_action.type_id,
                    activation_type=g_action.activation_type,
                    snippet=html_to_md(d_action["snippet"]),
                )
            )

        # actions: save all, regardless of gamedata presence
        for d_action in character_actions:
            # Unarmed Strike - already in attacks
            if d_action["typeId"] == "1120657896" and d_action["id"] == "1":
                continue
            # display as attack override - fall back to attack system
            if d_action["isCustomized"] and d_action["displayAsAttack"]:
                continue
            # racial feature affected by martial arts - fall back to attack system
            if (
                d_action["isMartialArts"]
                and d_action["displayAsAttack"]
                and int(d_action["componentTypeId"]) == gamedata.race.RaceFeature.type_id
            ):
                continue

            # gamedata for limiteduse
            try:
                g_actions = compendium.lookup_actions_for_entity(int(d_action["typeId"]), int(d_action["id"]))
            except (TypeError, ValueError):  # weird null typeid/uuid id action, maybe artificer infused item?
                continue

            # gamedata for component (parent feature)
            # data might have been entered for the parent feature instead
            try:
                parent_type_id, parent_id = int(d_action["componentTypeId"]), int(d_action["componentId"])
                parent_g_actions = compendium.lookup_actions_for_entity(parent_type_id, parent_id)
                seen_feature_ids.add((parent_type_id, parent_id))
            except (TypeError, ValueError):
                parent_g_actions = []

            # if the lu itself has action data, save a reference to each gamedata action by UID
            for g_action in itertools.chain(g_actions, parent_g_actions):
                add_action_from_gamedata(d_action, g_action)

            # just save the action w/ its snippet if there is no gamedata
            if not (g_actions or parent_g_actions):
                activation_type = (
                    enums.ActivationType(d_action["activationType"]) if d_action["activationType"] is not None else None
                )
                actions.append(
                    Action(
                        name=d_action["name"],
                        uid=None,
                        id=int(d_action["id"]),
                        type_id=int(d_action["typeId"]),
                        activation_type=activation_type,
                        snippet=html_to_md(d_action["snippet"]),
                    )
                )
            else:
                # otherwise, either it or its parent successfully added something, so we can save its id
                # for attack filtering
                action_ids_with_valid_actions.add((str(d_action["id"]), str(d_action["typeId"])))

        # features: save only if gamedata references them
        for d_feature in character_features:
            d_type_id, d_id = int(d_feature["typeId"]), int(d_feature["id"])
            if (d_type_id, d_id) in seen_feature_ids:
                continue
            g_actions = compendium.lookup_actions_for_entity(d_type_id, d_id)
            for g_action in g_actions:
                add_action_from_gamedata(d_feature, g_action)

        return Actions(actions), action_ids_with_valid_actions

    # ==== helpers ====
    @staticmethod
    def _transform_attack(attack) -> Attack:
        desc = html_to_md(attack["desc"])

        activation = attack.get("activationType")
        # Attack's are listed as Actions on Beyond, and this was the default prior
        if activation == 1:
            activation = None
        if activation is not None:
            activation = ActivationType(activation)

        if attack["saveDc"] is not None and attack["saveStat"] is not None:
            stat = constants.STAT_ABBREVIATIONS[attack["saveStat"] - 1]
            for_half = desc and "half" in desc

            the_attack = automation.Save(
                stat,
                fail=[automation.Damage("{damage}")],
                success=[] if not for_half else [automation.Damage("{damage}/2")],
                dc=str(attack["saveDc"]),
            )

            # attack, then save
            if attack["toHit"] is not None:
                the_attack = automation.Attack(hit=[the_attack], attackBonus=str(attack["toHit"]), miss=[])

            # target and damage meta
            target = automation.Target("each", [the_attack])
            damage_roll = automation.Roll(attack["damage"] or "0", "damage")
            effects = [damage_roll, target]
            # description text
            if desc:
                effects.append(automation.Text(desc))
            return Attack(attack["name"], automation.Automation(effects), activation_type=activation)
        else:
            return Attack.new(
                attack["name"], attack["toHit"], attack["damage"] or "0", desc, activation_type=activation
            )


def derive_adv(advs, dises):
    seen = set()
    for adv in advs:
        if not adv["restriction"]:
            seen.add(True)
    for dis in dises:
        if not dis["restriction"]:
            seen.add(False)

    if len(seen) == 1:
        return seen.pop()
    return None


def html_to_md(text):
    if not text:
        return text
    return markdownify(text).strip()
