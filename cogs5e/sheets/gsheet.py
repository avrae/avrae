"""
Created on May 8, 2017

@author: andrew
"""
# v3: added stat cvars
# v4: consumables
# v5: spellbook
# v6: v2.0 support (level vars, resistances, extra spells/attacks)
# v7: race/background (experimental)
# v8: skill/save effects
# v15: version fix
import asyncio
import logging
import os
import re

import pygsheets
from googleapiclient.errors import HttpError
from pygsheets.exceptions import SpreadsheetNotFound

from cogs5e.funcs.dice import get_roll_comment
from cogs5e.funcs.lookupFuncs import c
from cogs5e.models.character import Character
from cogs5e.models.errors import ExternalImportError
from cogs5e.models.sheet import Attack, BaseStats, Levels, Spellbook, SpellbookSpell
from cogs5e.models.sheet.base import Resistances, Saves, Skill, Skills
from cogs5e.sheets.errors import MissingAttribute
from utils.constants import DAMAGE_TYPES
from utils.functions import search
from .abc import SheetLoaderABC

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
    def __init__(self, worksheet, cells):
        self.worksheet = worksheet
        self.cells = worksheet.range(cells)
        # print('\n'.join(str(r) for r in self.cells))

    def cell(self, pos):
        _pos = POS_RE.match(pos)
        if _pos is None:
            raise Exception("No A1-style position found.")
        col = letter2num(_pos.group(1))
        row = int(_pos.group(2)) - 1
        if row > len(self.cells) or col > len(self.cells[row]):
            raise Exception("Cell out of bounds.")
        cell = self.cells[row][col]
        log.debug(f"Cell {pos}: {cell}")
        return cell

    def range(self, rng):
        return self.worksheet.range(rng)


class GoogleSheet(SheetLoaderABC):
    g_client = None
    _client_initializing = False

    def __init__(self, url):
        super(GoogleSheet, self).__init__(url)
        self.additional = None
        self.version = 1

        self.total_level = 0

    # google api stuff
    @staticmethod
    async def init_gsheet_client():
        if GoogleSheet._client_initializing:
            raise ExternalImportError("I am still connecting to google. Try again in a few seconds.")
        GoogleSheet._client_initializing = True

        def _():
            if "GOOGLE_SERVICE_ACCOUNT" in os.environ:
                return pygsheets.authorize(service_account_env_var='GOOGLE_SERVICE_ACCOUNT', no_cache=True)
            return pygsheets.authorize(service_account_file='avrae-google.json', no_cache=True)

        GoogleSheet.g_client = await asyncio.get_event_loop().run_in_executor(None, _)
        GoogleSheet._client_initializing = False
        log.info("Logged in to google")

    def _gchar(self):
        # self.client.login()
        doc = GoogleSheet.g_client.open_by_key(self.url)
        self.character_data = TempCharacter(doc.sheet1, "A1:AR180")
        vcell = doc.sheet1.cell("AQ4").value
        if "1.3" not in vcell:
            self.additional = TempCharacter(doc.worksheet('index', 1), "A1:AP81")
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
        except (KeyError, SpreadsheetNotFound):
            raise ExternalImportError("Invalid character sheet. Make sure you've shared it with me at "
                                      "`avrae-320@avrae-bot.iam.gserviceaccount.com`!")
        except HttpError:
            raise ExternalImportError("Google returned an error. Please ensure your sheet is shared with "
                                      "`avrae-320@avrae-bot.iam.gserviceaccount.com` and try again in a few minutes.")
        except Exception:
            raise
        return await asyncio.get_event_loop().run_in_executor(None, self._load_character, owner_id, args)

    def _load_character(self, owner_id: str, args):
        upstream = f"google-{self.url}"
        active = False
        sheet_type = "google"
        import_version = 15
        name = self.character_data.cell("C6").value.strip() or "Unnamed"
        description = self.get_description()
        image = self.character_data.cell("C176").value.strip()

        stats = self.get_stats().to_dict()
        levels = self.get_levels().to_dict()
        attacks = self.get_attacks()

        skls, svs = self.get_skills_and_saves()
        skills = skls.to_dict()
        saves = svs.to_dict()

        resistances = self.get_resistances().to_dict()
        ac = self.get_ac()
        max_hp = self.get_hp()
        hp = max_hp
        temp_hp = 0

        cvars = {}
        options = {}
        overrides = {}
        death_saves = {}
        consumables = []

        spellbook = self.get_spellbook().to_dict()
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
            await self.init_gsheet_client()
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._gchar)

    # calculator functions
    def get_description(self):
        if self.character_data is None: raise Exception('You must call get_character() first.')
        character = self.character_data
        g = character.cell("C150").value.lower()
        n = character.cell("C6").value
        pronoun = "She" if g == "female" else "He" if g == "male" else "They"
        verb1 = "is" if pronoun != "They" else "are"
        verb2 = "has" if pronoun != "They" else "have"
        desc = "{0} is a level {1} {2} {3}. {4} {11} {5} years old, {6} tall, and appears to weigh about {7}." \
               "{4} {12} {8} eyes, {9} hair, and {10} skin."
        desc = desc.format(n,
                           character.cell("AL6").value,
                           character.cell("T7").value,
                           character.cell("T5").value,
                           pronoun,
                           character.cell("C148").value or "unknown",
                           character.cell("F148").value or "unknown",
                           character.cell("I148").value or "unknown",
                           character.cell("F150").value.lower() or "unknown",
                           character.cell("I150").value.lower() or "unknown",
                           character.cell("L150").value.lower() or "unknown",
                           verb1, verb2)
        return desc

    def get_stats(self):
        """Returns a dict of stats."""
        if self.character_data is None: raise Exception('You must call get_character() first.')
        character = self.character_data
        try:
            prof_bonus = int(character.cell("H14").value)
        except (TypeError, ValueError):
            raise MissingAttribute("Proficiency Bonus")

        index = 15
        stat_dict = {}
        for stat in ('strength', 'dexterity', 'constitution', 'intelligence', 'wisdom', 'charisma'):
            try:
                stat_dict[stat] = int(character.cell("C" + str(index)).value)
                index += 5
            except (TypeError, ValueError):
                raise MissingAttribute(stat)

        stats = BaseStats(prof_bonus, **stat_dict)
        return stats

    def get_levels(self):
        if self.character_data is None: raise Exception('You must call get_character() first.')
        try:
            total_level = int(self.character_data.cell("AL6").value)
            self.total_level = total_level
        except ValueError:
            raise MissingAttribute("Character level")

        level_dict = {}
        if self.additional:
            for rownum in range(69, 79):  # sheet2, C69:C78
                namecell = f"C{rownum}"
                levelcell = f"N{rownum}"
                classname = self.additional.cell(namecell).value
                if classname:
                    classlevel = int(self.additional.cell(levelcell).value)
                    level_dict[classname] = classlevel
                else:  # classes should be top-aligned
                    break

        levels = Levels(level_dict, total_level)
        return levels

    def get_attacks(self):
        """Returns a list of dicts of all of the character's attacks."""
        if self.character_data is None: raise Exception('You must call get_character() first.')
        attacks = []
        for rownum in range(32, 37):  # sht1, R32:R36
            a = self.parse_attack(f"R{rownum}", f"Y{rownum}", f"AC{rownum}")
            if a is not None:
                attacks.append(a.to_dict())
        if self.additional:
            for rownum in range(3, 14):  # sht2, B3:B13; W3:W13
                additional = self.parse_attack(f"B{rownum}", f"I{rownum}", f"M{rownum}", self.additional)
                other = self.parse_attack(f"W{rownum}", f"AD{rownum}", f"AH{rownum}", self.additional)
                if additional is not None:
                    attacks.append(additional.to_dict())
                if other is not None:
                    attacks.append(other.to_dict())
        return attacks

    def get_skills_and_saves(self):
        if self.character_data is None: raise Exception('You must call get_character() first.')
        character = self.character_data

        skills = {}
        saves = {}
        is_joat = self.version == 2 and bool(character.cell("AR45").value)
        for cell, skill, advcell in SKILL_CELL_MAP:
            if isinstance(cell, int):
                advcell = f"F{cell}"
                profcell = f"H{cell}"
                cell = f"I{cell}"
            else:
                profcell = None
            try:
                value = int(character.cell(cell).value)
            except (TypeError, ValueError):
                raise MissingAttribute(skill)

            adv = None
            if self.version == 2 and advcell:
                advtype = character.cell(advcell).value
                if advtype in {'a', 'adv', 'advantage'}:
                    adv = True
                elif advtype in {'d', 'dis', 'disadvantage'}:
                    adv = False

            prof = 0
            if "Save" not in skill and is_joat:
                prof = 0.5
            if profcell:
                proftype = character.cell(profcell).value_unformatted
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
            resist = self.additional.cell(f"T{resist_row}").value
            if resist:
                out['resist'].append(resist.lower())

        for immune_row in range(69, 80):  # AE69:AE79
            immune = self.additional.cell(f"AE{immune_row}").value
            if immune:
                out['immune'].append(immune.lower())

        return Resistances.from_dict(out)

    def get_ac(self):
        try:
            return int(self.character_data.cell("R12").value)
        except (TypeError, ValueError):
            raise MissingAttribute("AC")

    def get_hp(self):
        try:
            return int(self.character_data.cell("U16").value)
        except (TypeError, ValueError):
            raise MissingAttribute("Max HP")

    def get_race(self):
        return self.character_data.cell('T7').value.strip()

    def get_background(self):
        if self.version == 2:
            return self.character_data.cell('AJ11').value.strip()
        return self.character_data.cell('Z5').value.strip()

    def get_spellbook(self):
        if self.character_data is None: raise Exception('You must call get_character() first.')
        # max slots
        slots = {
            '1': int(self.character_data.cell('AK101').value or 0),
            '2': int(self.character_data.cell('E107').value or 0),
            '3': int(self.character_data.cell('AK113').value or 0),
            '4': int(self.character_data.cell('E119').value or 0),
            '5': int(self.character_data.cell('AK124').value or 0),
            '6': int(self.character_data.cell('E129').value or 0),
            '7': int(self.character_data.cell('AK134').value or 0),
            '8': int(self.character_data.cell('E138').value or 0),
            '9': int(self.character_data.cell('AK142').value or 0)
        }

        # spells C96:AH143
        potential_spells = self.character_data.range("D96:AH143")  # returns a matrix, the docs lie
        if self.additional:
            potential_spells.extend(self.additional.range("D17:AH64"))

        spells = []
        for row in potential_spells:
            for cell in row:
                if cell.value and not cell.value in IGNORED_SPELL_VALUES:
                    value = cell.value.strip()
                    result = search(c.spells, value, lambda sp: sp.name, strict=True)
                    if result and result[0] and result[1]:
                        spells.append(SpellbookSpell(result[0].name, True))
                    elif len(value) > 2:
                        spells.append(SpellbookSpell(value.strip()))

        try:
            dc = int(self.character_data.cell('AB91').value or 0)
        except ValueError:
            dc = None

        try:
            sab = int(self.character_data.cell('AI91').value or 0)
        except ValueError:
            sab = None

        spellbook = Spellbook(slots, slots, spells, dc, sab, self.total_level)
        return spellbook

    # helper methods
    def parse_attack(self, name_index, bonus_index, damage_index, sheet=None):
        """Calculates and returns a dict."""
        if self.character_data is None: raise Exception('You must call get_character() first.')

        wksht = sheet or self.character_data

        name = wksht.cell(name_index).value
        damage = wksht.cell(damage_index).value
        bonus = wksht.cell(bonus_index).value
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

        bonus_calc = None
        if bonus:
            try:
                bonus = int(bonus)
            except (TypeError, ValueError):
                bonus_calc = bonus
                bonus = None
        else:
            bonus = None

        attack = Attack(name, bonus, damage, details, bonus_calc)
        return attack
