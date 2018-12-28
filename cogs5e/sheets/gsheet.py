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
                        '6TH LEVEL', '7TH LEVEL', '8TH LEVEL', '9TH LEVEL',
                        "You can hide each level of spells individually by hiding the rows (on the left).")


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

    def _gchar(self):
        # self.client.login()
        doc = self.client.open_by_key(self.url)
        self.character = TempCharacter(doc.sheet1, "A1:AQ180")
        if doc.sheet1.cell("AQ4").value == "2.0":
            self.additional = TempCharacter(doc.worksheet('index', 1), "A1:AP81")

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

        try:
            armor = character.cell("R12").value
            attacks = self.get_attacks()
            skills = self.get_skills()
            levels = self.get_levels()

            temp_resist = self.get_resistances()
            resistances = temp_resist['resist']
            immunities = temp_resist['immune']
            spellbook = self.get_spellbook()
        except:
            raise

        saves = {}
        for key in skills:
            if 'Save' in key:
                saves[key] = skills[key]

        stat_vars = {}
        stat_vars.update(stats)
        stat_vars.update(levels)
        stat_vars['hp'] = hp
        stat_vars['armor'] = int(armor)
        stat_vars.update(saves)

        sheet = {'type': 'google',
                 'version': 6,  # v3: added stat cvars
                 # v4: consumables
                 # v5: spellbook
                 # v6: v2.0 support (level vars, resistances, extra spells/attacks)
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
                 'consumables': {},
                 'spellbook': spellbook}

        embed = self.get_embed(sheet)

        return {'embed': embed, 'sheet': sheet}

    def get_embed(self, sheet):
        stats = sheet['stats']
        hp = sheet['hp']
        skills = sheet['skills']
        attacks = sheet['attacks']
        levels = sheet['levels']
        saves = sheet['saves']
        armor = sheet['armor']
        embed = discord.Embed()
        embed.colour = random.randint(0, 0xffffff)
        embed.title = stats['name']
        embed.set_thumbnail(url=stats['image'])
        embed.add_field(name="HP/Level", value="**HP:** {}\nLevel {}".format(hp, levels['level']))
        embed.add_field(name="AC", value=str(armor))
        embed.add_field(name="Stats", value="**STR:** {strength} ({strengthMod:+})\n" \
                                            "**DEX:** {dexterity} ({dexterityMod:+})\n" \
                                            "**CON:** {constitution} ({constitutionMod:+})\n" \
                                            "**INT:** {intelligence} ({intelligenceMod:+})\n" \
                                            "**WIS:** {wisdom} ({wisdomMod:+})\n" \
                                            "**CHA:** {charisma} ({charismaMod:+})".format(**stats))
        embed.add_field(name="Saves", value="**STR:** {strengthSave:+}\n" \
                                            "**DEX:** {dexteritySave:+}\n" \
                                            "**CON:** {constitutionSave:+}\n" \
                                            "**INT:** {intelligenceSave:+}\n" \
                                            "**WIS:** {wisdomSave:+}\n" \
                                            "**CHA:** {charismaSave:+}".format(**saves))

        skillsStr = ''
        tempSkills = {}
        for skill, mod in sorted(skills.items()):
            if 'Save' not in skill:
                skillsStr += '**{}**: {:+}\n'.format(re.sub(r'((?<=[a-z])[A-Z]|(?<!\A)[A-Z](?=[a-z]))', r' \1', skill),
                                                     mod)
                tempSkills[skill] = mod
        sheet['skills'] = tempSkills

        embed.add_field(name="Skills", value=skillsStr.title())

        tempAttacks = []
        for a in attacks:
            if a is not None:
                if a['attackBonus'] is not None:
                    bonus = a['attackBonus']
                    tempAttacks.append("**{0}:** +{1} To Hit, {2} damage.".format(a['name'],
                                                                                  bonus,
                                                                                  a['damage'] if a[
                                                                                                     'damage'] is not None else 'no'))
                else:
                    tempAttacks.append("**{0}:** {1} damage.".format(a['name'],
                                                                     a['damage'] if a['damage'] is not None else 'no'))
        if not tempAttacks:
            tempAttacks = ['No attacks.']
        embed.add_field(name="Attacks", value='\n'.join(tempAttacks))

        return embed

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
            dice, comment = get_roll_comment(attack['damage'])
            if any(d in comment.lower() for d in damageTypes):
                attack['damage'] = "{}[{}]".format(dice, comment)
            else:
                attack['damage'] = dice
                if comment.strip():
                    attack['details'] = comment.strip()

        attack['attackBonus'] = attack['attackBonus'].replace('+', '', 1) if attack['attackBonus'] is not '' else None

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
        skillslist = ['I25', 'I26', 'I27', 'I28',
                      'I22', 'I19', 'I29', 'I18',
                      'I30', 'V12', 'I31', 'I20',
                      'I32', 'I33', 'I34', 'I35',
                      'I36', 'I37', 'I38', 'I39',
                      'I40', 'I41', 'I17', 'I42', 'I21',
                      'C13', 'C18', 'C23', 'C33', 'C28', 'C38']
        skillsMap = ['acrobatics', 'animalHandling', 'arcana', 'athletics',
                     'charismaSave', 'constitutionSave', 'deception', 'dexteritySave',
                     'history', 'initiative', 'insight', 'intelligenceSave',
                     'intimidation', 'investigation', 'medicine', 'nature',
                     'perception', 'performance', 'persuasion', 'religion',
                     'sleightOfHand', 'stealth', 'strengthSave', 'survival', 'wisdomSave',
                     'strength', 'dexterity', 'constitution', 'wisdom', 'intelligence', 'charisma']
        skills = {}
        for index, skill in enumerate(skillslist):
            try:
                skills[skillsMap[index]] = int(character.cell(skill).value)
            except (TypeError, ValueError):
                raise MissingAttribute(skillsMap[index])

        return skills

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
        pronoun = "She" if g == "female" else "He" if g == "male" else n
        desc = "{0} is a level {1} {2} {3}. {4} is {5} years old, {6} tall, and appears to weigh about {7}. {4} has {8} eyes, {9} hair, and {10} skin."
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
                           character.cell("L150").value.lower() or "unknown")
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
