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
from cogs5e.funcs.lookupFuncs import c
from cogs5e.sheets.errors import MissingAttribute
from cogs5e.sheets.sheetParser import SheetParser
from utils.functions import strict_search

log = logging.getLogger(__name__)

class BeyondSheetParser(SheetParser):
    
    def __init__(self, url):
        self.url = url
        self.character = None

    async def get_character(self):
        url = self.url
        async with aiohttp.get(url) as f:
            character = await f.json()
        self.character = character
        return character
    
    def get_sheet(self):
        """Returns a dict with character sheet data."""
        if self.character is None: raise Exception('You must call get_character() first.')
        character = self.character

        try:
            stats = self.get_stats() # TODO
            levels = self.get_levels()
            hp = character.get('hitPoints', {}).get('max', 0)
            dexArmor = self.calculate_stat('dexterityArmor', base=stats['dexterityMod']) # TODO
            armor = self.calculate_stat('armor', replacements={'dexterityArmor': dexArmor}) # TODO
            attacks = self.get_attacks() # TODO
            skills = self.get_skills() # TODO
            temp_resist = self.get_resistances() # TODO
            resistances = temp_resist['resist']
            immunities = temp_resist['immune']
            vulnerabilities = temp_resist['vuln']
            skill_effects = self.get_skill_effects() # TODO
            spellbook = self.get_spellbook() # TODO
        except:
            raise

        saves = {} # TODO
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
                skillsStr += '**{}**: {:+}\n'.format(re.sub(r'((?<=[a-z])[A-Z]|(?<!\A)[A-Z](?=[a-z]))', r' \1', skill), mod)
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
                                                                                  a['damage'] if a['damage'] is not None else 'no'))
                else:
                    tempAttacks.append("**{0}:** {1} damage.".format(a['name'],
                                                                     a['damage'] if a['damage'] is not None else 'no'))
        if tempAttacks == []:
            tempAttacks = ['No attacks.']
        embed.add_field(name="Attacks", value='\n'.join(tempAttacks))
        
        return embed
        
    def get_stats(self):
        """Returns a dict of stats."""
        if self.character is None: raise Exception('You must call get_character() first.')
        character = self.character
        stats = {"name":"", "image":"", "description":"",
                 "strength":10, "dexterity":10, "constitution":10, "wisdom":10, "intelligence":10, "charisma":10,
                 "strengthMod":0, "dexterityMod":0, "constitutionMod":0, "wisdomMod":0, "intelligenceMod":0, "charismaMod":0,
                 "proficiencyBonus":0}
        stats['name'] = character.get('name') or "Unnamed"
        stats['description'] = self.get_description()
        stats['image'] = character.get('avatarUrl') or ''
        stats['proficiencyBonus'] = int(character.get('proficiencyBonus'))
        
        for stat in ('strength', 'dexterity', 'constitution', 'wisdom', 'intelligence', 'charisma'):
            try:
                stats[stat] = int(character.get('stats', {}).get(stat[:3])) + int(character.get('bonusStats', {}).get(stat[:3]) or 0)
                stats[stat + 'Mod'] = int(floor((stats[stat]-10)/2))
            except TypeError:
                raise MissingAttribute(stat)
        
        return stats

    def get_description(self):
        if self.character is None: raise Exception('You must call get_character() first.')
        character = self.character
        n = character.get('name') or "Unnamed"
        pronoun = "They"
        desc = "{0} is a level {1} {2} {3}. {4} are {5} years old, {6} ft. tall, and appears to weigh about {7} lbs. {4} have {8} eyes, {9} hair, and {10} skin."
        desc = desc.format(n,
                           character.get('level', 0),
                           character.acell("T7").value, # TODO: get classes
                           character.get('race') or 'unknown',
                           pronoun,
                           character.get('age') or "unknown",
                           character.get('height') or "unknown",
                           character.get('weight') or "unknown",
                           character.get('eyes') or "unknown",
                           character.get('hair') or "unknown",
                           character.get('skin') or "unknown")
        return desc

    def get_levels(self):
        """Returns a dict with the character's level and class levels."""
        if self.character is None: raise Exception('You must call get_character() first.')
        character = self.character
        levels = {"level":0}
        for _class in character.get('classes', []):
            levels['level'] += _class.get('level')
            levelName = _class.get('class', {}).get('name') + 'Level'
            if levels.get(levelName) is None:
                levels[levelName] = _class.get('level')
            else:
                levels[levelName] += _class.get('level')
        return levels

    def get_attack(self, atkIn):
        """Calculates and returns a dict."""
        if self.character is None: raise Exception('You must call get_character() first.')
        character = self.character
        attack = {'attackBonus': '0', 'damage':'0', 'name': ''}
        
        attack['name'] = character.get('Attack' + str(atkIn))
        attack['attackBonus'] = character.get('AtkBonus' + str(atkIn))
        attack['damage'] = character.get('Damage' + str(atkIn))
        
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
        skillslist = ['acrobatics', 'animalHandling',
                      'arcana', 'athletics',
                      'charismaSave', 'constitutionSave',
                      'deception', 'dexteritySave',
                      'history', 'initiative',
                      'insight', 'intelligenceSave',
                      'intimidation', 'investigation',
                      'medicine', 'nature',
                      'perception', 'performance',
                      'persuasion', 'religion',
                      'sleightOfHand', 'stealth',
                      'strengthSave', 'survival',
                      'wisdomSave']
        skills = {}
        profs = {}
        for skill in skillslist:
            skills[skill] = stats.get(character.get('characters', [])[0].get(skill, {}).get('ability') + 'Mod', 0)
        for prof in character.get('proficiencies', []):
            if prof.get('enabled', False) and not prof.get('removed', False):
                profs[prof.get('name')] = prof.get('value') \
                    if prof.get('value') > profs.get(prof.get('name', 'None'), 0) \
                    else profs[prof.get('name')]

        for skill in skills:
            skills[skill] = floor(skills[skill] + stats.get('proficiencyBonus') * profs.get(skill, 0))
            skills[skill] = int(self.calculate_stat(skill, base=skills[skill]))

        for stat in ('strength', 'dexterity', 'constitution', 'wisdom', 'intelligence', 'charisma'):
            skills[stat] = stats.get(stat + 'Mod')

        return skills
    
    def get_level(self):
        if self.character is None: raise Exception('You must call get_character() first.')
        character = self.character
        level = 0
        classlevel = character.get("ClassLevel", "")
        for l in re.finditer(r'\d+', classlevel):
            level += int(l.group(0))
        return level

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
