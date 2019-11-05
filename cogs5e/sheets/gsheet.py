"""
Created on May 8, 2017

@author: andrew
"""

import asyncio
import datetime
import json
import logging
import os
import re
from contextlib import contextmanager

import gspread
from gspread import SpreadsheetNotFound
from gspread.exceptions import APIError
from gspread.utils import a1_to_rowcol, fill_gaps
from oauth2client.service_account import ServiceAccountCredentials

from cogs5e.funcs.dice import get_roll_comment
from cogs5e.funcs.lookupFuncs import compendium
from cogs5e.models.character import Character
from cogs5e.models.errors import ExternalImportError
from cogs5e.models.sheet.attack import Attack, AttackList
from cogs5e.models.sheet.base import BaseStats, Levels, Resistances, Saves, Skill, Skills
from cogs5e.models.sheet.spellcasting import Spellbook, SpellbookSpell
from cogs5e.sheets.abc import SHEET_VERSION, SheetLoaderABC
from cogs5e.sheets.errors import MissingAttribute
from utils import config
from utils.constants import DAMAGE_TYPES
from utils.functions import search

log = logging.getLogger(__name__)

POS_RE = re.compile(r"([A-Z]+)(\d+)")
IGNORED_SPELL_VALUES = {
    'MAX', 'SLOTS', 'CANTRIPS', '1ST LEVEL', '2ND LEVEL', '3RD LEVEL', '4TH LEVEL', '5TH LEVEL',
    '6TH LEVEL', '7TH LEVEL', '8TH LEVEL', '9TH LEVEL', '\u25c9', '\u25cd',
    "You can hide each level of spells individually by hiding the rows (on the left)."
}
SKILL_CELL_MAP = (  # list of (MOD_CELL/ROW, SKILL_NAME, ADV_CELL)
    ('C13', 'strength', None), ('C18', 'dexterity', None), ('C23', 'constitution', None),
    ('C33', 'wisdom', None), ('C28', 'intelligence', None), ('C38', 'charisma', None),
    (25, 'acrobatics', None), (26, 'animalHandling', None), (27, 'arcana', None),
    (28, 'athletics', None), (22, 'charismaSave', None), (19, 'constitutionSave', None),
    (29, 'deception', None), (18, 'dexteritySave', None), (30, 'history', None),
    ('V12', 'initiative', 'V11'), (31, 'insight', None), (20, 'intelligenceSave', None),
    (32, 'intimidation', None), (33, 'investigation', None), (34, 'medicine', None),
    (35, 'nature', None), (36, 'perception', None), (37, 'performance', None),
    (38, 'persuasion', None), (39, 'religion', None), (40, 'sleightOfHand', None),
    (41, 'stealth', None), (17, 'strengthSave', None), (42, 'survival', None),
    (21, 'wisdomSave', None)
)
SCOPES = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']


def letter2num(letters, zbase=True):
    """A = 1, C = 3 and so on. Convert spreadsheet style column
    enumeration to a number.
    """

    letters = letters.upper()
    res = 0
    weight = len(letters) - 1
    for i, ch in enumerate(letters):
        res += (ord(ch) - 64) * 26 ** (weight - i)
    if not zbase:
        return res
    return res - 1


class TempCharacter:
    def __init__(self, worksheet):
        self.worksheet = worksheet
        self.values = worksheet.get_all_values()
        self.unformatted_values = self._get_all_unformatted_values()

    def _get_all_unformatted_values(self):
        data = self.worksheet.spreadsheet.values_get(
            self.worksheet.title,
            params={'valueRenderOption': "UNFORMATTED_VALUE"})
        try:
            return fill_gaps(data['values'])
        except KeyError:
            return []

    @staticmethod
    def _get_value(source, pos):
        _pos = POS_RE.match(pos)
        if _pos is None:
            raise ValueError("No A1-style position found.")
        col = letter2num(_pos.group(1))
        row = int(_pos.group(2)) - 1
        if row > len(source) or col > len(source[row]):
            raise IndexError("Cell out of bounds.")
        value = source[row][col]
        log.debug(f"Cell {pos}: {value}")
        return value

    def value(self, pos):
        return self._get_value(self.values, pos)

    def unformatted_value(self, pos):
        return self._get_value(self.unformatted_values, pos)

    def value_range(self, rng):
        """Returns a list of values in a range."""
        start, end = rng.split(':')
        (row_offset, column_offset) = a1_to_rowcol(start)
        (last_row, last_column) = a1_to_rowcol(end)

        out = []
        for col in self.values[row_offset - 1:last_row]:
            out.extend(col[column_offset - 1:last_column])
        return out


class GoogleSheet(SheetLoaderABC):
    g_client = None
    _client_initializing = False
    _token_expiry = None

    def __init__(self, url):
        super(GoogleSheet, self).__init__(url)
        self.additional = None
        self.version = 1

        self.total_level = 0

        # cache
        self._stats = None

    # google api stuff
    @staticmethod
    @contextmanager
    def _client_lock():
        if GoogleSheet._client_initializing:
            raise ExternalImportError("I am still connecting to google. Try again in a few seconds.")
        GoogleSheet._client_initializing = True
        yield
        GoogleSheet._client_initializing = False

    @staticmethod
    async def _init_gsheet_client():
        with GoogleSheet._client_lock():
            def _():
                if config.GOOGLE_SERVICE_ACCOUNT is not None:
                    credentials = ServiceAccountCredentials.from_json_keyfile_dict(
                        json.loads(config.GOOGLE_SERVICE_ACCOUNT),
                        scopes=SCOPES)
                else:
                    credentials = ServiceAccountCredentials.from_json_keyfile_name(
                        "avrae-google.json",
                        scopes=SCOPES)
                return gspread.authorize(credentials)

            try:
                GoogleSheet.g_client = await asyncio.get_event_loop().run_in_executor(None, _)
            except:
                GoogleSheet._client_initializing = False
                raise
        GoogleSheet._token_expiry = datetime.datetime.now() + datetime.timedelta(
            seconds=ServiceAccountCredentials.MAX_TOKEN_LIFETIME_SECS)
        log.info("Logged in to google")

    @staticmethod
    async def _refresh_google_token():
        with GoogleSheet._client_lock():
            def _():
                import httplib2

                http = httplib2.Http()
                GoogleSheet.g_client.auth.refresh(http)
                GoogleSheet.g_client.session.headers.update({
                    'Authorization': 'Bearer %s' % GoogleSheet.g_client.auth.access_token
                })

            try:
                await asyncio.get_event_loop().run_in_executor(None, _)
            except:
                GoogleSheet._client_initializing = False
                raise
        log.info("Refreshed google token")

    @staticmethod
    def _is_expired():
        return datetime.datetime.now() > GoogleSheet._token_expiry

    # load character data
    def _gchar(self):
        doc = GoogleSheet.g_client.open_by_key(self.url)
        self.character_data = TempCharacter(doc.sheet1)
        vcell = self.character_data.value("AQ4")
        if ("1.3" not in vcell) and vcell:
            self.additional = TempCharacter(doc.get_worksheet(1))
            self.version = 2 if "2" in vcell else 1

    # main loading methods
    async def load_character(self, owner_id: str, args):
        """
        Downloads and parses the character data, returning a fully-formed Character object.
        :raises ExternalImportError if something went wrong during the import that we can expect
        :raises Exception if something weirder happened
        """
        try:
            await self.get_character()
        except (KeyError, SpreadsheetNotFound, APIError):
            raise ExternalImportError("Invalid character sheet. Make sure you've shared it with me at "
                                      "`avrae-320@avrae-bot.iam.gserviceaccount.com`!")
        except Exception:
            raise
        return await asyncio.get_event_loop().run_in_executor(None, self._load_character, owner_id, args)

    def _load_character(self, owner_id: str, args):
        upstream = f"google-{self.url}"
        active = False
        sheet_type = "google"
        import_version = SHEET_VERSION
        name = self.character_data.value("C6").strip() or "Unnamed"
        description = self.get_description()
        image = self.character_data.value("C176").strip()

        stats = self.get_stats()
        levels = self.get_levels()
        attacks = self.get_attacks()

        skills, saves = self.get_skills_and_saves()

        resistances = self.get_resistances()
        ac = self.get_ac()
        max_hp = self.get_hp()
        hp = max_hp
        temp_hp = 0

        cvars = {}
        options = {}
        overrides = {}
        death_saves = {}
        consumables = []

        spellbook = self.get_spellbook()
        live = None
        race = self.get_race()
        background = self.get_background()

        character = Character(
            owner_id, upstream, active, sheet_type, import_version, name, description, image, stats, levels, attacks,
            skills, resistances, saves, ac, max_hp, hp, temp_hp, cvars, options, overrides, consumables, death_saves,
            spellbook, live, race, background
        )
        return character

    async def get_character(self):
        if GoogleSheet.g_client is None:
            await self._init_gsheet_client()
        elif GoogleSheet._is_expired():
            await self._refresh_google_token()
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._gchar)

    # calculator functions
    def get_description(self):
        if self.character_data is None: raise Exception('You must call get_character() first.')
        character = self.character_data
        g = character.value("C150").lower()
        n = character.value("C6")
        pronoun = "She" if g == "female" else "He" if g == "male" else "They"
        verb1 = "is" if pronoun != "They" else "are"
        verb2 = "has" if pronoun != "They" else "have"
        desc = "{0} is a level {1} {2} {3}. {4} {11} {5} years old, {6} tall, and appears to weigh about {7}." \
               "{4} {12} {8} eyes, {9} hair, and {10} skin."
        desc = desc.format(n,
                           character.value("AL6"),
                           character.value("T7"),
                           character.value("T5"),
                           pronoun,
                           character.value("C148") or "unknown",
                           character.value("F148") or "unknown",
                           character.value("I148") or "unknown",
                           character.value("F150").lower() or "unknown",
                           character.value("I150").lower() or "unknown",
                           character.value("L150").lower() or "unknown",
                           verb1, verb2)
        return desc

    def get_stats(self):
        """Returns a dict of stats."""
        if self.character_data is None: raise Exception('You must call get_character() first.')
        character = self.character_data
        if self._stats is not None:
            return self._stats

        try:
            prof_bonus = int(character.value("H14"))
        except (TypeError, ValueError):
            raise MissingAttribute("Proficiency Bonus")

        index = 15
        stat_dict = {}
        for stat in ('strength', 'dexterity', 'constitution', 'intelligence', 'wisdom', 'charisma'):
            try:
                stat_dict[stat] = int(character.value("C" + str(index)))
                index += 5
            except (TypeError, ValueError):
                raise MissingAttribute(stat)

        stats = BaseStats(prof_bonus, **stat_dict)
        self._stats = stats
        return stats

    def get_levels(self):
        if self.character_data is None: raise Exception('You must call get_character() first.')
        try:
            total_level = int(self.character_data.value("AL6"))
            self.total_level = total_level
        except ValueError:
            raise MissingAttribute("Character level")

        level_dict = {}
        if self.additional:
            for rownum in range(69, 79):  # sheet2, C69:C78
                namecell = f"C{rownum}"
                levelcell = f"N{rownum}"
                classname = self.additional.value(namecell)
                if classname:
                    classlevel = int(self.additional.value(levelcell))
                    level_dict[classname] = classlevel
                else:  # classes should be top-aligned
                    break

        levels = Levels(level_dict, total_level)
        return levels

    def get_attacks(self):
        """Returns an attack list."""
        if self.character_data is None: raise Exception('You must call get_character() first.')
        attacks = AttackList()
        for rownum in range(32, 37):  # sht1, R32:R36
            a = self.parse_attack(f"R{rownum}", f"Y{rownum}", f"AC{rownum}")
            if a is not None:
                attacks.append(a)
        if self.additional:
            for rownum in range(3, 14):  # sht2, B3:B13; W3:W13
                additional = self.parse_attack(f"B{rownum}", f"I{rownum}", f"M{rownum}", self.additional)
                other = self.parse_attack(f"W{rownum}", f"AD{rownum}", f"AH{rownum}", self.additional)
                if additional is not None:
                    attacks.append(additional)
                if other is not None:
                    attacks.append(other)
        return attacks

    def get_skills_and_saves(self):
        if self.character_data is None: raise Exception('You must call get_character() first.')
        character = self.character_data

        skills = {}
        saves = {}
        is_joat = self.version == 2 and bool(character.value("AR45"))
        for cell, skill, advcell in SKILL_CELL_MAP:
            if isinstance(cell, int):
                advcell = f"F{cell}"
                profcell = f"H{cell}"
                cell = f"I{cell}"
            else:
                profcell = None
            try:
                value = int(character.value(cell))
            except (TypeError, ValueError):
                raise MissingAttribute(skill)

            adv = None
            if self.version == 2 and advcell:
                advtype = character.unformatted_value(advcell)
                if advtype in {'a', 'adv', 'advantage'}:
                    adv = True
                elif advtype in {'d', 'dis', 'disadvantage'}:
                    adv = False

            prof = 0
            if "Save" not in skill and is_joat:
                prof = 0.5
            if profcell:
                proftype = character.unformatted_value(profcell)
                if proftype == 'e':
                    prof = 2
                elif proftype and proftype != '0':
                    prof = 1

            skl_obj = Skill(value, prof, adv=adv)
            if "Save" in skill:
                saves[skill] = skl_obj
            else:
                skills[skill] = skl_obj

        skills = Skills(skills)
        saves = Saves(saves)
        return skills, saves

    def get_resistances(self):
        out = {'resist': [], 'immune': [], 'vuln': []}
        if not self.additional:  # requires 2.0
            return Resistances.from_dict(out)

        for resist_row in range(69, 80):  # T69:T79
            resist = self.additional.value(f"T{resist_row}")
            if resist:
                out['resist'].append(resist.lower())

        for immune_row in range(69, 80):  # AE69:AE79
            immune = self.additional.value(f"AE{immune_row}")
            if immune:
                out['immune'].append(immune.lower())

        return Resistances.from_dict(out)

    def get_ac(self):
        try:
            return int(self.character_data.value("R12"))
        except (TypeError, ValueError):
            raise MissingAttribute("AC")

    def get_hp(self):
        try:
            return int(self.character_data.value("U16"))
        except (TypeError, ValueError):
            raise MissingAttribute("Max HP")

    def get_race(self):
        return self.character_data.value('T7').strip()

    def get_background(self):
        if self.version == 2:
            return self.character_data.value('AJ11').strip()
        return self.character_data.value('Z5').strip()

    def get_spellbook(self):
        if self.character_data is None: raise Exception('You must call get_character() first.')
        # max slots
        slots = {
            '1': int(self.character_data.value("AK101") or 0),
            '2': int(self.character_data.value("E107") or 0),
            '3': int(self.character_data.value("AK113") or 0),
            '4': int(self.character_data.value("E119") or 0),
            '5': int(self.character_data.value("AK124") or 0),
            '6': int(self.character_data.value("E129") or 0),
            '7': int(self.character_data.value("AK134") or 0),
            '8': int(self.character_data.value("E138") or 0),
            '9': int(self.character_data.value("AK142") or 0)
        }

        # spells C96:AH143
        potential_spells = self.character_data.value_range("D96:AH143")
        if self.additional:
            potential_spells.extend(self.additional.value_range("D17:AH64"))

        spells = []
        for value in potential_spells:
            value = value.strip()
            if len(value) > 2 and value not in IGNORED_SPELL_VALUES:
                log.debug(f"Searching for spell {value}")
                result, strict = search(compendium.spells, value, lambda sp: sp.name, strict=True)
                if result and strict:
                    spells.append(SpellbookSpell(result.name, True))
                else:
                    spells.append(SpellbookSpell(value.strip()))

        # dc
        try:
            dc = int(self.character_data.value("AB91") or 0)
        except ValueError:
            dc = None

        # sab
        try:
            sab = int(self.character_data.value("AI91") or 0)
        except ValueError:
            sab = None

        # spellcasting mod
        spell_mod_value = self.character_data.value("U91")
        spell_mod = None
        if spell_mod_value:  # it might be in the form of a ability name, or an int, wjdk
            try:
                spell_mod = self.get_stats().get_mod(spell_mod_value)
            except ValueError:
                try:
                    spell_mod = int(spell_mod_value)
                except (TypeError, ValueError):
                    spell_mod = None

        spellbook = Spellbook(slots, slots, spells, dc, sab, self.total_level, spell_mod)
        return spellbook

    # helper methods
    def parse_attack(self, name_index, bonus_index, damage_index, sheet=None):
        """Calculates and returns a dict."""
        if self.character_data is None: raise Exception('You must call get_character() first.')

        wksht = sheet or self.character_data

        name = wksht.value(name_index)
        damage = wksht.value(damage_index)
        bonus = wksht.value(bonus_index)
        details = None

        if not name:
            return None

        if not damage:
            damage = None
        else:
            details = None
            if '|' in damage:
                damage, details = damage.split('|', 1)

            dice, comment = get_roll_comment(damage)
            if details:
                details = details.strip()

            if any(d in comment.lower() for d in DAMAGE_TYPES):
                damage = "{}[{}]".format(dice, comment)
            else:
                damage = dice
                if comment.strip() and not details:
                    damage = comment.strip()

        if bonus:
            try:
                bonus = int(bonus)
            except (TypeError, ValueError):
                bonus = None
        else:
            bonus = None

        attack = Attack.new(name, bonus, damage, details)
        return attack
