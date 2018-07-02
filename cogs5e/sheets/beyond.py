"""
Created on Feb 14, 2017

@author: andrew
"""

import logging
import random
import re
from math import floor

import aiohttp
import discord

from cogs5e.funcs.dice import get_roll_comment
from cogs5e.models.errors import ExternalImportError
from utils.functions import strict_search

log = logging.getLogger(__name__)

API_BASE = "https://www.dndbeyond.com/character/"
CUSTOM_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/60.0.3112.113 Safari/537.36"
}
SKILL_MAP = {'acrobatics': 'dexterity', 'animalHandling': 'wisdom', 'arcana': 'intelligence', 'athletics': 'strength',
             'deception': 'charisma', 'history': 'intelligence', 'initiative': 'dexterity', 'insight': 'wisdom',
             'intimidation': 'charisma', 'investigation': 'intelligence', 'medicine': 'wisdom',
             'nature': 'intelligence', 'perception': 'wisdom', 'performance': 'charisma',
             'persuasion': 'charisma', 'religion': 'intelligence', 'sleightOfHand': 'dexterity', 'stealth': 'dexterity',
             'survival': 'wisdom', 'strengthSave': 'strength', 'dexteritySave': 'dexterity',
             'constitutionSave': 'constitution', 'intelligenceSave': 'intelligence', 'wisdomSave': 'wisdom',
             'charismaSave': 'charisma'}


class BeyondSheetParser:

    def __init__(self, charId):
        self.url = charId
        self.character = None

        self.stats = None
        self.levels = None

    async def get_character(self):
        charId = self.url
        character = None
        async with aiohttp.ClientSession(headers=CUSTOM_HEADERS) as session:
            async with session.get(f"{API_BASE}{charId}/json") as resp:
                log.debug(f"DDB returned {resp.status}")
                if resp.status == 200:
                    character = await resp.json()
                elif resp.status == 403:
                    raise ExternalImportError("Error: I do not have permission to view this character sheet. "
                                              "Make sure you've generated a sharable link for your character.")
                else:
                    raise ExternalImportError(f"Beyond returned an error: {resp.status} - {resp.reason}")
        character['_id'] = charId
        self.character = character
        return character

    def get_sheet(self):
        """Returns a dict with character sheet data."""
        if self.character is None: raise Exception('You must call get_character() first.')
        character = self.character

        try:
            stats = self.get_stats()
            levels = self.get_levels()
            hp = character['baseHitPoints'] + (
                    (self.get_stat('hit-points-per-level', base=stats['constitutionMod'])) * levels['level'])
            armor = self.get_ac()
            attacks = self.get_attacks()  # TODO
            skills = self.get_skills()
            temp_resist = self.get_resistances()  # TODO
            resistances = temp_resist['resist']
            immunities = temp_resist['immune']
            vulnerabilities = temp_resist['vuln']
            skill_effects = self.get_skill_effects()  # TODO
            spellbook = self.get_spellbook()  # TODO
        except:
            raise

        saves = {}  # TODO
        for key in skills:
            if 'Save' in key:
                saves[key] = skills[key]

        stat_vars = {}
        stat_vars.update(stats)
        stat_vars.update(levels)
        stat_vars['hp'] = int(hp)
        stat_vars['armor'] = int(armor)
        stat_vars.update(saves)

        sheet = {'type': 'beyond',
                 'version': 1,
                 'stats': stats,
                 'levels': levels,
                 'hp': int(hp),
                 'armor': int(armor),
                 'attacks': attacks,
                 'skills': skills,
                 'resist': resistances,
                 'immune': immunities,
                 'vuln': vulnerabilities,
                 'saves': saves,
                 'stat_cvars': stat_vars,
                 'skill_effects': skill_effects,
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
        if self.stats: return self.stats
        character = self.character
        stats = {"name": "", "image": "", "description": "", "strength": 10, "dexterity": 10, "constitution": 10,
                 "wisdom": 10, "intelligence": 10, "charisma": 10, "strengthMod": 0, "dexterityMod": 0,
                 "constitutionMod": 0, "wisdomMod": 0, "intelligenceMod": 0, "charismaMod": 0, "proficiencyBonus": 0,
                 'name': character.get('name') or "Unnamed", 'description': self.get_description(),
                 'image': character.get('avatarUrl') or ''}

        profByLevel = floor(self.get_levels()['level'] / 4 + 1.75)
        stats['proficiencyBonus'] = self.get_stat('proficiency-bonus', base=int(profByLevel))

        for i, stat in enumerate(('strength', 'dexterity', 'constitution', 'intelligence', 'wisdom', 'charisma')):
            base = next(s for s in character['stats'] if s['id'] == i + 1)['value']
            bonus = next(s for s in character['bonusStats'] if s['id'] == i + 1)['value'] or 0
            override = next(s for s in character['overrideStats'] if s['id'] == i + 1)['value']
            stats[stat] = override or self.get_stat(f"{stat}-score", base=base + bonus)
            stats[f"{stat}Mod"] = floor((int(stats[stat]) - 10) / 2)

        self.stats = stats
        return stats

    def get_stat(self, stat, base=0):
        """Calculates the final value of a stat, based on modifiers and feats."""
        bonus = 0
        for modtype in self.character['modifiers'].values():
            for mod in modtype:
                if not mod['subType'] == stat: continue
                if mod['type'] == 'bonus':
                    bonus += mod['value'] or self.stat_from_id(mod['statId'])
                elif mod['type'] == 'set':
                    base = mod['value'] or self.stat_from_id(mod['statId'])

        return base + bonus

    def stat_from_id(self, _id):
        return self.get_stats()[('strengthMod', 'dexterityMod', 'constitutionMod',
                                 'intelligenceMod', 'wisdomMod', 'charismaMod')[_id + 1]]

    def get_ac(self):
        base = 10
        armortype = None
        for item in self.character['inventory']:
            if item['equipped'] and item['definition']['filterType'] == 'Armor':
                base = item['definition']['armorClass']
                armortype = item['definition']['type']
        base = self.get_stat('armor-class', base=base)
        dexBonus = self.get_stats()['dexterityMod']
        unarmoredBonus = self.get_stat('unarmored-armor-class')
        if armortype is None:
            return base + dexBonus + unarmoredBonus
        elif armortype == 'Light Armor':
            return base + dexBonus
        elif armortype == 'Medium Armor':
            return base + min(dexBonus, 2)
        else:
            return base

    def get_description(self):
        if self.character is None: raise Exception('You must call get_character() first.')
        return "TODO"  # TODO

    def get_levels(self):
        """Returns a dict with the character's level and class levels."""
        if self.character is None: raise Exception('You must call get_character() first.')
        if self.levels: return self.levels
        character = self.character
        levels = {"level": 0}
        for _class in character.get('classes', []):
            levels['level'] += _class.get('level')
            levelName = _class.get('definition', {}).get('name') + 'Level'
            if levels.get(levelName) is None:
                levels[levelName] = _class.get('level')
            else:
                levels[levelName] += _class.get('level')
        self.levels = levels  # cache for further use
        return levels

    def get_attack(self, atkIn):
        """Calculates and returns a dict."""
        if self.character is None: raise Exception('You must call get_character() first.')
        character = self.character
        attack = {
            'attackBonus': character.get('AtkBonus' + str(atkIn)),
            'damage': character.get('Damage' + str(atkIn)),
            'name': character.get('Attack' + str(atkIn))
        }

        if attack['name'] is None:
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

        attack['attackBonus'] = attack['attackBonus'].replace('+', '', 1) if attack['attackBonus'] is not None else None

        return attack

    def get_attacks(self):
        """Returns a list of dicts of all of the character's attacks."""
        if self.character is None: raise Exception('You must call get_character() first.')
        attacks = []
        for attack in range(3):
            a = self.get_attack(attack + 1)
            if a is not None: attacks.append(a)
        return attacks

    def get_skills(self):
        """Returns a dict of all the character's skills."""
        if self.character is None: raise Exception('You must call get_character() first.')
        character = self.character
        stats = self.get_stats()

        skills = {}
        profs = {}
        bonuses = {}
        for skill, stat in SKILL_MAP.items():
            skills[skill] = stats.get(f"{stat}Mod", 0)

        for modtype in character['modifiers'].values():
            for mod in modtype:
                mod['subType'] = mod['subType'].replace("-saving-throws", "Save")
                if mod['type'] == 'half-proficiency':
                    profs[mod['subType']] = max(profs.get(mod['subType'], 0), 0.5)
                elif mod['type'] == 'proficiency':
                    profs[mod['subType']] = max(profs.get(mod['subType'], 0), 1)
                elif mod['type'] == 'expertise':
                    profs[mod['subType']] = 2
                elif mod['type'] == 'bonus':
                    bonuses[mod['subType']] = bonuses.get(mod['subType'], 0) + mod['value']

        profs['animalHandling'] = profs.get('animal-handling', 0)
        profs['sleightOfHand'] = profs.get('sleight-of-hand', 0)

        for skill in skills:
            relevantprof = profs.get(skill, 0)
            relevantbonus = bonuses.get(skill, 0)
            if 'ability-checks' in profs and not 'Save' in skill:
                relevantprof = max(relevantprof, profs['ability-checks'])
            if 'saving-throws' in profs and 'Save' in skill:
                relevantprof = max(relevantprof, profs['saving-throws'])
            if 'ability-checks' in bonuses and not 'Save' in skill:
                relevantbonus += bonuses['ability-checks']
            if 'saving-throws' in bonuses and 'Save' in skill:
                relevantbonus += bonuses['saving-throws']
            skills[skill] = floor(
                skills[skill] + (stats.get('proficiencyBonus') * relevantprof) + relevantbonus)

        for stat in ('strength', 'dexterity', 'constitution', 'wisdom', 'intelligence', 'charisma'):
            skills[stat] = stats.get(stat + 'Mod')

        return skills

    def get_spellbook(self):
        if self.character is None: raise Exception('You must call get_character() first.')
        spellbook = {'spellslots': {},
                     'spells': [],
                     'dc': 0,
                     'attackBonus': 0}

        for lvl in range(1, 10):
            try:
                numSlots = int(self.character.get(f"SlotsTot{lvl}") or 0)
            except ValueError:
                numSlots = 0
            spellbook['spellslots'][str(lvl)] = numSlots

        spellnames = set([self.character.get(f"Spells{n}") for n in range(1, 101) if self.character.get(f"Spells{n}")])

        for spell in spellnames:
            s = strict_search(c.spells, 'name', spell)
            if s:
                spellbook['spells'].append(s.get('name'))

        try:
            spellbook['dc'] = int(self.character.get('SpellSaveDC', 0) or 0)
        except ValueError:
            pass

        try:
            spellbook['attackBonus'] = int(self.character.get('SAB', 0) or 0)
        except ValueError:
            pass

        log.debug(f"Completed parsing spellbook: {spellbook}")
        return spellbook


if __name__ == '__main__':
    import asyncio

    while True:
        url = input("DDB Character ID: ").strip()
        parser = BeyondSheetParser(url)
        asyncio.get_event_loop().run_until_complete(parser.get_character())
        print(parser.get_sheet())
