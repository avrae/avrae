"""
Created on May 8, 2017

@author: andrew
"""
import asyncio
import logging
import random
import re

import discord

from cogs5e.funcs.dice import get_roll_comment
from cogs5e.funcs.lookupFuncs import c
from cogs5e.sheets.errors import MissingAttribute
from utils.functions import search

log = logging.getLogger(__name__)

POS_RE = re.compile(r"([A-Z]+)(\d+)")
IGNORED_SPELL_VALUES = ('MAX', 'SLOTS', 'CANTRIPS', '1ST LEVEL', '2ND LEVEL', '3RD LEVEL', '4TH LEVEL', '5TH LEVEL',
                        '6TH LEVEL', '7TH LEVEL', '8TH LEVEL', '9TH LEVEL', '\u25c9',
                        "You can hide each level of spells individually by hiding the rows (on the left).")
SKILL_MAP = (  # list of (MOD_CELL, SKILL_NAME, ADV_CELL)
    ('I25', 'acrobatics', 'F25'), ('I26', 'animalHandling', 'F26'), ('I27', 'arcana', 'F27'),
    ('I28', 'athletics', 'F28'), ('I22', 'charismaSave', 'F22'), ('I19', 'constitutionSave', 'F19'),
    ('I29', 'deception', 'F29'), ('I18', 'dexteritySave', 'F18'), ('I30', 'history', 'F30'),
    ('V12', 'initiative', 'V11'), ('I31', 'insight', 'F31'), ('I20', 'intelligenceSave', 'F20'),
    ('I32', 'intimidation', 'F32'), ('I33', 'investigation', 'F33'), ('I34', 'medicine', 'F34'),
    ('I35', 'nature', 'F35'), ('I36', 'perception', 'F36'), ('I37', 'performance', 'F37'),
    ('I38', 'persuasion', 'F38'), ('I39', 'religion', 'F39'), ('I40', 'sleightOfHand', 'F40'),
    ('I41', 'stealth', 'F41'), ('I17', 'strengthSave', 'F17'), ('I42', 'survival', 'F42'),
    ('I21', 'wisdomSave', 'F21'), ('C13', 'strength', None), ('C18', 'dexterity', None),
    ('C23', 'constitution', None), ('C33', 'wisdom', None), ('C28', 'intelligence', None),
    ('C38', 'charisma', None)
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


class GoogleSheet:
    def __init__(self, url, client):
        self.url = url
        self.character = None
        assert client is not None
        self.client = client
        self.additional = None
        self.version = 1

    def _gchar(self):
        # self.client.login()
        doc = self.client.open_by_key(self.url)
        self.character = TempCharacter(doc.sheet1, "A1:AQ180")
        if doc.sheet1.cell("AQ4").value == "2.0":
            self.additional = TempCharacter(doc.worksheet('index', 1), "A1:AP81")
            self.version = 2

    async def get_character(self):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._gchar)

    async def get_sheet(self):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_sheet)

    def _get_sheet(self):
        """Returns a dict with character sheet data."""
        if self.character is None: raise Exception('You must call get_character() first.')
        character = self.character
        try:
            stats = self.get_stats()
            hp = int(character.cell("U16").value)
        except ValueError:
            raise MissingAttribute("Max HP")

        armor = character.cell("R12").value
        attacks = self.get_attacks()
        skills, skill_effects = self.get_skills()
        levels = self.get_levels()

        temp_resist = self.get_resistances()
        resistances = temp_resist['resist']
        immunities = temp_resist['immune']
        spellbook = self.get_spellbook()

        saves = {}
        for key in skills.copy():
            if 'Save' in key:
                saves[key] = skills.pop(key)

        stat_vars = {}
        stat_vars.update(stats)
        stat_vars.update(levels)
        stat_vars['hp'] = hp
        stat_vars['armor'] = int(armor)
        stat_vars.update(saves)

        # v3: added stat cvars
        # v4: consumables
        # v5: spellbook
        # v6: v2.0 support (level vars, resistances, extra spells/attacks)
        # v7: race/background (experimental)
        # v8: skill/save effects
        sheet = {
            'type': 'google',
            'version': 7,
            'stats': stats,
            'levels': levels,
            'hp': hp,
            'armor': int(armor),
            'attacks': attacks,
            'skills': skills,
            'resist': resistances,
            'immune': immunities,
            'vuln': [],
            'saves': saves,
            'stat_cvars': stat_vars,
            'skill_effects': skill_effects,
            'consumables': {},
            'spellbook': spellbook,
            'race': self.get_race(),
            'background': self.get_background()
        }

        return {'embed': None, 'sheet': sheet}

    def get_stats(self):
        """Returns a dict of stats."""
        if self.character is None: raise Exception('You must call get_character() first.')
        character = self.character
        stats = {"image": "", "strength": 10, "dexterity": 10, "constitution": 10,
                 "wisdom": 10, "intelligence": 10, "charisma": 10, "strengthMod": 0, "dexterityMod": 0,
                 "constitutionMod": 0, "wisdomMod": 0, "intelligenceMod": 0, "charismaMod": 0, "proficiencyBonus": 0,
                 'name': character.cell("C6").value or "Unnamed",
                 'description': self.get_description()}
        try:
            stats['proficiencyBonus'] = int(character.cell("H14").value)
        except (TypeError, ValueError):
            raise MissingAttribute("Proficiency Bonus")
        stats['image'] = character.cell("C176").value

        index = 15
        for stat in ('strength', 'dexterity', 'constitution', 'intelligence', 'wisdom', 'charisma'):
            try:
                stats[stat] = int(character.cell("C" + str(index)).value)
                stats[stat + 'Mod'] = int(character.cell("C" + str(index - 2)).value)
                index += 5
            except (TypeError, ValueError):
                raise MissingAttribute(stat)

        return stats

    def get_attack(self, name_index, bonus_index, damage_index, sheet=None):
        """Calculates and returns a dict."""
        if self.character is None: raise Exception('You must call get_character() first.')

        wksht = sheet or self.character

        attack = {
            'attackBonus': wksht.cell(bonus_index).value,
            'damage': wksht.cell(damage_index).value,
            'name': wksht.cell(name_index).value
        }

        if attack['name'] is "":
            return None
        if attack['damage'] is "":
            attack['damage'] = None
        else:
            damageTypes = ['acid', 'bludgeoning', 'cold', 'fire', 'force',
                           'lightning', 'necrotic', 'piercing', 'poison',
                           'psychic', 'radiant', 'slashing', 'thunder']

            details = None
            if '|' in attack['damage']:
                attack['damage'], details = attack['damage'].split('|', 1)

            dice, comment = get_roll_comment(attack['damage'])
            if details:
                attack['details'] = details.strip()

            if any(d in comment.lower() for d in damageTypes):
                attack['damage'] = "{}[{}]".format(dice, comment)
            else:
                attack['damage'] = dice
                if comment.strip() and not details:
                    attack['details'] = comment.strip()

        attack['attackBonus'] = attack['attackBonus'].strip('+') if attack['attackBonus'] is not '' else None

        return attack

    def get_attacks(self):
        """Returns a list of dicts of all of the character's attacks."""
        if self.character is None: raise Exception('You must call get_character() first.')
        attacks = []
        for rownum in range(32, 37):  # sht1, R32:R36
            a = self.get_attack(f"R{rownum}", f"Y{rownum}", f"AC{rownum}")
            if a is not None: attacks.append(a)
        if self.additional:
            for rownum in range(3, 14):  # sht2, B3:B13; W3:W13
                additional = self.get_attack(f"B{rownum}", f"I{rownum}", f"M{rownum}", self.additional)
                other = self.get_attack(f"W{rownum}", f"AD{rownum}", f"AH{rownum}", self.additional)
                if additional is not None: attacks.append(additional)
                if other is not None: attacks.append(other)
        return attacks

    def get_skills(self):
        """Returns a dict of all the character's skills."""
        if self.character is None: raise Exception('You must call get_character() first.')
        character = self.character

        skills = {}
        skill_effects = {}
        for cell, skill, advcell in SKILL_MAP:
            try:
                skills[skill] = int(character.cell(cell).value)
            except (TypeError, ValueError):
                raise MissingAttribute(skill)

            if self.version == 2 and advcell:
                advtype = character.cell(advcell).value
                if advtype in ('a', 'adv'):
                    skill_effects[skill] = 'adv'
                elif advtype in ('d', 'dis'):
                    skill_effects[skill] = 'dis'

        skills = {k: v for k, v in sorted(skills.items())}
        return skills, skill_effects

    def get_levels(self):
        if self.character is None: raise Exception('You must call get_character() first.')
        levels = {}
        try:
            levels['level'] = int(self.character.cell("AL6").value)
        except ValueError:
            raise MissingAttribute("Character level")
        if self.additional:
            for rownum in range(69, 79):  # sheet2, C69:C78
                namecell = f"C{rownum}"
                levelcell = f"N{rownum}"
                classname = self.additional.cell(namecell).value
                if classname:
                    classlevel = int(self.additional.cell(levelcell).value)
                    levels[f"{classname}Level"] = classlevel
                else:  # classes should be top-aligned
                    break
        return levels

    def get_description(self):
        if self.character is None: raise Exception('You must call get_character() first.')
        character = self.character
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

    def get_resistances(self):
        out = {'resist': [], 'immune': []}
        if not self.additional:  # requires 2.0
            return out

        for resist_row in range(69, 80):  # T69:T79
            resist = self.additional.cell(f"T{resist_row}").value
            if resist:
                out['resist'].append(resist.lower())

        for immune_row in range(69, 80):  # AE69:AE79
            immune = self.additional.cell(f"AE{immune_row}").value
            if immune:
                out['immune'].append(immune.lower())

        return out

    def get_spellbook(self):
        if self.character is None: raise Exception('You must call get_character() first.')
        spellbook = {'spellslots': {},
                     'spells': [],  # C96:AH143 - gah.
                     'dc': 0,
                     'attackBonus': 0}

        spellslots = {'1': int(self.character.cell('AK101').value or 0),
                      '2': int(self.character.cell('E107').value or 0),
                      '3': int(self.character.cell('AK113').value or 0),
                      '4': int(self.character.cell('E119').value or 0),
                      '5': int(self.character.cell('AK124').value or 0),
                      '6': int(self.character.cell('E129').value or 0),
                      '7': int(self.character.cell('AK134').value or 0),
                      '8': int(self.character.cell('E138').value or 0),
                      '9': int(self.character.cell('AK142').value or 0)}
        spellbook['spellslots'] = spellslots

        potential_spells = self.character.range("D96:AH143")  # returns a matrix, the docs lie
        if self.additional:
            potential_spells.extend(self.additional.range("D17:AH64"))
        spells = []

        for row in potential_spells:
            for cell in row:
                if cell.value and not cell.value in IGNORED_SPELL_VALUES:
                    value = cell.value.strip()
                    result = search(c.spells, value, lambda sp: sp.name, strict=True)
                    if result and result[0] and result[1]:
                        spells.append({
                            'name': result[0].name,
                            'strict': True
                        })
                    elif len(value) > 2:
                        spells.append({
                            'name': value,
                            'strict': False
                        })

        spellbook['spells'] = spells

        try:
            spellbook['dc'] = int(self.character.cell('AB91').value or 0)
        except ValueError:
            pass

        try:
            spellbook['attackBonus'] = int(self.character.cell('AI91').value or 0)
        except ValueError:
            pass

        log.debug(f"Completed parsing spellbook: {spellbook}")
        return spellbook

    def get_race(self):
        return self.character.cell('T7').value.strip()

    def get_background(self):
        if self.version == 2:
            return self.character.cell('AJ11').value.strip()
        return self.character.cell('Z5').value.strip()
