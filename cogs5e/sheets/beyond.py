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
import html2text

from cogs5e.models.errors import ExternalImportError

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
DAMAGE_TYPES = {1: "bludgeoning", 2: "piercing", 3: "slashing", 4: "necrotic", 5: "acid", 6: "cold", 7: "fire",
                8: "lightning", 9: "thunder", 10: "poison", 11: "psychic", 12: "radiant", 13: "force"}
CASTER_TYPES = {"Barbarian": 0, "Bard": 1, "Cleric": 1, "Druid": 1, "Fighter": 0.334, "Monk": 0, "Paladin": 0.5,
                "Ranger": 0.5, "Rogue": 0.334, "Sorcerer": 1, "Warlock": 0, "Wizard": 1}
SLOTS_PER_LEVEL = {
    1: lambda l: min(l + 1, 4),
    2: lambda l: 0 if l < 3 else min(l - 1, 3),
    3: lambda l: 0 if l < 5 else min(l - 3, 3),
    4: lambda l: 0 if l < 7 else min(l - 6, 3),
    5: lambda l: 0 if l < 9 else min(l - 8, 3),
    6: lambda l: 0 if l < 11 else 1 if l < 19 else 2,
    7: lambda l: 0 if l < 13 else 1 if l < 20 else 2,
    8: lambda l: int(l >= 15),
    9: lambda l: int(l >= 17)
}
SIMPLE_WEAPONS = ["Club", "Dagger", "Greatclub", "Handaxe", "Javelin", "Light Hammer", "Mace", "Quarterstaff", "Sickle",
                  "Spear", "Crossbow, Light", "Dart", "Shortbow", "Sling"]
MARTIAL_WEAPONS = ['Battleaxe', 'Blowgun', 'Flail', 'Glaive', 'Greataxe', 'Greatsword', 'Halberd', 'Hand Crossbow',
                   'Heavy Crossbow', 'Lance', 'Longbow', 'Longsword', 'Maul', 'Morningstar', 'Net', 'Pike', 'Rapier',
                   'Scimitar', 'Shortsword', 'Trident', 'War Pick', 'Warhammer', 'Whip', 'Pistol', 'Musket',
                   'Automatic Pistol', 'Revolver', 'Hunting Rifle', 'Automatic Rifle', 'Shotgun', 'Laser Pistol',
                   'Antimatter Rifle', 'Laser Rifle']


class BeyondSheetParser:

    def __init__(self, charId):
        self.url = charId
        self.character = None

        self.stats = None
        self.levels = None
        self.prof = None
        self.calculated_stats = {}

    async def get_character(self):
        charId = self.url
        character = None
        async with aiohttp.ClientSession(headers=CUSTOM_HEADERS) as session:
            async with session.get(f"{API_BASE}{charId}/json") as resp:
                log.debug(f"DDB returned {resp.status}")
                if resp.status == 200:
                    character = await resp.json()
                elif resp.status == 404:
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
            attacks = self.get_attacks()
            skills = self.get_skills()
            temp_resist = self.get_resistances()
            resistances = temp_resist['resist']
            immunities = temp_resist['immune']
            vulnerabilities = temp_resist['vuln']
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

    def get_stat(self, stat, base=0, bonus_tags=None):
        """Calculates the final value of a stat, based on modifiers and feats."""
        if bonus_tags is None:
            bonus_tags = ['bonus']
        if stat in self.calculated_stats and bonus_tags == ['bonus']:
            return self.calculated_stats[stat]
        bonus = 0
        for modtype in self.character['modifiers'].values():
            for mod in modtype:
                if not mod['subType'] == stat: continue
                if mod['type'] in bonus_tags:
                    bonus += mod['value'] or self.stat_from_id(mod['statId'])
                elif mod['type'] == 'set':
                    base = mod['value'] or self.stat_from_id(mod['statId'])

        if bonus_tags == ['bonus']:
            self.calculated_stats[stat] = base + bonus
        return base + bonus

    def stat_from_id(self, _id):
        if _id in range(1, 7):
            return self.get_stats()[('strengthMod', 'dexterityMod', 'constitutionMod',
                                     'intelligenceMod', 'wisdomMod', 'charismaMod')[_id - 1]]
        return 0

    def get_ac(self):
        base = 10
        armortype = None
        shield = 0
        for item in self.character['inventory']:
            if item['equipped'] and item['definition']['filterType'] == 'Armor':
                _type = item['definition']['type']
                if _type == "Shield":
                    shield = 2
                else:
                    base = item['definition']['armorClass']
                    armortype = _type
        base = self.get_stat('armor-class', base=base)
        dexBonus = self.get_stats()['dexterityMod']
        unarmoredBonus = self.get_stat('unarmored-armor-class')
        armoredBonus = self.get_stat('armored-armor-class')
        if armortype is None:
            return base + dexBonus + unarmoredBonus + shield
        elif armortype == 'Light Armor':
            return base + dexBonus + shield + armoredBonus
        elif armortype == 'Medium Armor':
            return base + min(dexBonus, 2) + shield + armoredBonus
        else:
            return base + shield + armoredBonus

    def get_description(self):
        if self.character is None: raise Exception('You must call get_character() first.')
        character = self.character
        g = character['gender']
        n = character['name']
        pronoun = "She" if g == "female" else "He" if g == "male" else "They"
        verb = "is" if not pronoun == 'They' else "are"
        verb2 = "has" if not pronoun == 'They' else "have"
        desc = "{0} is a level {1} {2} {3}. {4} {5} {6} years old, {7} tall, and appears to weigh about {8}. " \
               "{4} {12} {9} eyes, {10} hair, and {11} skin."
        desc = desc.format(n,
                           self.get_levels()['level'],
                           character['race']['fullName'],
                           '/'.join(c['definition']['name'] for c in character['classes']),
                           pronoun,
                           verb,
                           character['age'] or "unknown",
                           character['height'] or "unknown",
                           character['weight'] or "unknown",
                           (character['eyes'] or "unknown").lower(),
                           (character['hair'] or "unknown").lower(),
                           (character['skin'] or "unknown").lower(),
                           verb2)
        return desc

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

    def get_attack(self, atkIn, atkType):
        """Calculates and returns a list of dicts."""
        if self.character is None: raise Exception('You must call get_character() first.')
        stats = self.get_stats()
        prof = stats['proficiencyBonus']
        out = []
        attack = {
            'attackBonus': None,
            'damage': None,
            'name': None,
            'details': None
        }
        if atkType == 'action':
            attack = {
                'attackBonus': None,
                'damage': f"{atkIn['dice']['diceString']}[{parse_dmg_type(atkIn)}]",
                'name': atkIn['name'],
                'details': atkIn['snippet']
            }
        elif atkType == 'customAction':
            isProf = atkIn['isProficient']
            dmgBonus = (atkIn['fixedValue'] or 0) + (atkIn['damageBonus'] or 0)
            atkBonus = None
            if atkIn['statId']:
                atkBonus = self.stat_from_id(atkIn['statId']) + (prof if isProf else 0) + (atkIn['toHitBonus'] or 0)
                dmgBonus = (atkIn['fixedValue'] or 0) + self.stat_from_id(atkIn['statId']) + (atkIn['damageBonus'] or 0)

            if atkIn['attackSubtype'] == 3:  # natural weapons
                if atkBonus is not None:
                    atkBonus += self.get_stat('natural-attacks')
                dmgBonus += self.get_stat('natural-attacks', bonus_tags=['damage'])

            attack = {
                'attackBonus': str(atkBonus),
                'damage': f"{atkIn['diceCount']}d{atkIn['diceType']}+{dmgBonus}"
                          f"[{parse_dmg_type(atkIn)}]",
                'name': atkIn['name'],
                'details': atkIn['snippet']
            }
        elif atkType == 'item':
            itemdef = atkIn['definition']
            weirdBonuses = self.get_specific_item_bonuses(atkIn['id'])
            isProf = self.get_prof(itemdef['type']) or weirdBonuses['isPact']
            magicBonus = sum(
                m['value'] for m in itemdef['grantedModifiers'] if m['type'] == 'bonus' and m['subType'] == 'magic')

            dmgBonus = self.get_relevant_atkmod(itemdef) + magicBonus + weirdBonuses['damage']
            toHitBonus = (prof if isProf else 0) + magicBonus + weirdBonuses['attackBonus']

            is_melee = not 'Range' in [p['name'] for p in itemdef['properties']]
            is_one_handed = not 'Two-Handed' in [p['name'] for p in itemdef['properties']]
            is_weapon = itemdef['filterType'] == 'Weapon'

            if is_melee and is_one_handed:
                dmgBonus += self.get_stat('one-handed-melee-attacks', bonus_tags=['damage'])
            if not is_melee and is_weapon:
                toHitBonus += self.get_stat('ranged-weapon-attacks')

            attack = {
                'attackBonus': str(
                    weirdBonuses['attackBonusOverride'] or self.get_relevant_atkmod(itemdef) + toHitBonus),
                'damage': f"{itemdef['fixedDamage'] or itemdef['damage']['diceString']}+{dmgBonus}"
                          f"[{itemdef['damageType'].lower()}"
                          f"{'^' if itemdef['magic'] or weirdBonuses['isPact'] else ''}]",
                'name': itemdef['name'],
                'details': html2text.html2text(itemdef['description'], bodywidth=0).strip()
            }

            if 'Versatile' in [p['name'] for p in itemdef['properties']]:
                versDmg = next(p['notes'] for p in itemdef['properties'] if p['name'] == 'Versatile')
                out.append(
                    {
                        'attackBonus': attack['attackBonus'],
                        'damage': f"{versDmg}+{dmgBonus}"
                                  f"[{itemdef['damageType'].lower()}"
                                  f"{'^' if itemdef['magic'] or weirdBonuses['isPact'] else ''}]",
                        'name': f"{itemdef['name']} 2H",
                        'details': attack['details']
                    }
                )
        elif atkType == 'unarmed':
            dmg = 1 + self.stat_from_id(1)
            atkBonus = self.get_stats()['proficiencyBonus']

            atkBonus += self.get_stat('natural-attacks')
            dmg += self.get_stat('natural-attacks', bonus_tags=['damage'])

            attack = {
                'attackBonus': str(self.stat_from_id(1) + atkBonus),
                'damage': f"{dmg}[bludgeoning]",
                'name': "Unarmed Strike",
                'details': None
            }

        if attack['name'] is None:
            return None
        if attack['damage'] is "":
            attack['damage'] = None

        attack['attackBonus'] = attack['attackBonus'].replace('+', '', 1) if attack['attackBonus'] is not None else None
        out.insert(0, attack)

        return out

    def get_attacks(self):
        """Returns a list of dicts of all of the character's attacks."""
        if self.character is None: raise Exception('You must call get_character() first.')
        attacks = []
        used_names = []

        def extend(parsed_attacks):
            for atk in parsed_attacks:
                if atk['name'] in used_names:
                    num = 2
                    while f"{atk['name']}{num}" in used_names:
                        num += 1
                    atk['name'] = f"{atk['name']}{num}"
            attacks.extend(parsed_attacks)
            used_names.extend(a['name'] for a in parsed_attacks)

        for src in self.character['actions'].values():
            for action in src:
                if action['displayAsAttack']:
                    extend(self.get_attack(action, "action"))
        for action in self.character['customActions']:
            extend(self.get_attack(action, "customAction"))
        for item in self.character['inventory']:
            if item['equipped'] and (item['definition']['filterType'] == "Weapon" or item.get('displayAsAttack')):
                extend(self.get_attack(item, "item"))

        if 'Unarmed Strike' not in [a['name'] for a in attacks]:
            extend(self.get_attack(None, 'unarmed'))
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
                    bonuses[mod['subType']] = bonuses.get(mod['subType'], 0) + (mod['value'] or 0)

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

    def get_resistances(self):
        resist = {
            'resist': [],
            'immune': [],
            'vuln': []
        }
        for modtype in self.character['modifiers'].values():
            for mod in modtype:
                if mod['type'] == 'resistance':
                    resist['resist'].append(mod['subType'])
                elif mod['type'] == 'immunity':
                    resist['immune'].append(mod['subType'])
                elif mod['type'] == 'vulnerability':
                    resist['vuln'].append(mod['subType'])
        return resist

    def get_spellbook(self):
        if self.character is None: raise Exception('You must call get_character() first.')
        spellbook = {'spellslots': {},
                     'spells': [],
                     'dc': 0,
                     'attackBonus': 0}
        spellcasterLevel = 0
        spellMod = 0
        pactSlots = 0
        pactLevel = 1
        for _class in self.character['classes']:
            if _class['definition']['spellCastingAbilityId']:
                spellcasterLevel += floor(_class['level'] * CASTER_TYPES.get(_class['definition']['name'], 1))
                spellMod = max(spellMod, self.stat_from_id(_class['definition']['spellCastingAbilityId']))
            if _class['definition']['name'] == 'Warlock':
                pactSlots = pact_slots_by_level(_class['level'])
                pactLevel = pact_level_by_level(_class['level'])

        for lvl in range(1, 10):
            spellbook['spellslots'][lvl] = SLOTS_PER_LEVEL[lvl](spellcasterLevel)

        spellbook['spellslots'][pactLevel] += pactSlots

        prof = self.get_stats()['proficiencyBonus']
        spellbook['dc'] = 8 + spellMod + prof
        spellbook['attackBonus'] = spellMod + prof

        for src in self.character['classSpells']:
            spellbook['spells'].extend(s['definition']['name'].replace('\u2019', "'") for s in src['spells'])
        for src in self.character['spells'].values():
            spellbook['spells'].extend(s['definition']['name'].replace('\u2019', "'") for s in src)
        spellbook['spells'] = list(set(spellbook['spells']))

        return spellbook

    def get_prof(self, proftype):
        if not self.prof:
            p = []
            for modtype in self.character['modifiers'].values():
                for mod in modtype:
                    if mod['type'] == 'proficiency':
                        if mod['subType'] == 'simple-weapons':
                            p.extend(SIMPLE_WEAPONS)
                        elif mod['subType'] == 'martial-weapons':
                            p.extend(MARTIAL_WEAPONS)
                        p.append(mod['friendlySubtypeName'])
            self.prof = p
        return proftype in self.prof

    def get_relevant_atkmod(self, itemdef):
        if itemdef['attackType'] == 2:  # ranged, dex
            return self.stat_from_id(2)
        elif itemdef['attackType'] == 1:  # melee
            if 'Finesse' in [p['name'] for p in itemdef['properties']] or \
                    (itemdef['isMonkWeapon'] and self.get_levels().get('MonkLevel')):  # finesse, monk weapon
                return max(self.stat_from_id(1), self.stat_from_id(2))
        return self.stat_from_id(1)  # strength

    def get_specific_item_bonuses(self, itemId):
        out = {
            'attackBonus': 0,
            'attackBonusOverride': 0,
            'damage': 0,
            'isPact': False
        }
        for val in self.character['characterValues']:
            if not val['valueId'] == itemId: continue
            if val['typeId'] == 10:  # damage bonus
                out['damage'] += val['value']
            elif val['typeId'] == 12:  # to hit bonus
                out['attackBonus'] += val['value']
            elif val['typeId'] == 13:  # to hit override
                out['attackBonusOverride'] = max(val['value'], out['attackBonusOverride'])
            elif val['typeId'] == 28:  # pact weapon
                out['isPact'] = True
        return out


def parse_dmg_type(attack):
    return DAMAGE_TYPES.get(attack['damageTypeId'], "damage")


def pact_slots_by_level(level):
    return {
        1: 1,
        2: 2, 3: 2, 4: 2, 5: 2, 6: 2, 7: 2, 8: 2, 9: 2, 10: 2,
        11: 3, 12: 3, 13: 3, 14: 3, 15: 3, 16: 3,
        17: 4, 18: 4, 19: 4, 20: 4
    }.get(level, 0)


def pact_level_by_level(level):
    return min(floor((level + 1) / 2), 5)


if __name__ == '__main__':
    import asyncio

    while True:
        url = input("DDB Character ID: ").strip()
        parser = BeyondSheetParser(url)
        asyncio.get_event_loop().run_until_complete(parser.get_character())
        print(parser.get_sheet())
