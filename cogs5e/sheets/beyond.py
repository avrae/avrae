"""
Created on Feb 14, 2017

@author: andrew
"""
# v1: initial implementation
# v2: added race/background for research purposes
# v15: standardize sheet import versions
import collections
import logging
import re
from math import ceil, floor

import aiohttp
import html2text

from cogs5e.funcs.lookupFuncs import c
from cogs5e.models.character import Character
from cogs5e.models.errors import ExternalImportError
from cogs5e.models.sheet import Attack, BaseStats, Levels, Spellbook, SpellbookSpell
from cogs5e.models.sheet.base import Resistances, Saves, Skill, Skills
from cogs5e.sheets.abc import SheetLoaderABC
from utils.constants import SAVE_NAMES, SKILL_MAP, SKILL_NAMES
from utils.functions import search

log = logging.getLogger(__name__)

API_BASE = "https://www.dndbeyond.com/character/"
DAMAGE_TYPES = {1: "bludgeoning", 2: "piercing", 3: "slashing", 4: "necrotic", 5: "acid", 6: "cold", 7: "fire",
                8: "lightning", 9: "thunder", 10: "poison", 11: "psychic", 12: "radiant", 13: "force"}
CASTER_TYPES = {"Barbarian": 0, "Bard": 1, "Cleric": 1, "Druid": 1, "Fighter": 0.334, "Monk": 0, "Paladin": 0.5,
                "Ranger": 0.5, "Rogue": 0.334, "Sorcerer": 1, "Warlock": 0, "Wizard": 1}
SLOTS_PER_LEVEL = {
    1: lambda l: min(l + 1, 4) if l else 0,
    2: lambda l: 0 if l < 3 else min(l - 1, 3),
    3: lambda l: 0 if l < 5 else min(l - 3, 3),
    4: lambda l: 0 if l < 7 else min(l - 6, 3),
    5: lambda l: 0 if l < 9 else 1 if l < 10 else 2 if l < 18 else 3,
    6: lambda l: 0 if l < 11 else 1 if l < 19 else 2,
    7: lambda l: 0 if l < 13 else 1 if l < 20 else 2,
    8: lambda l: int(l >= 15),
    9: lambda l: int(l >= 17)
}
SIMPLE_WEAPONS = ["Club", "Dagger", "Greatclub", "Handaxe", "Javelin", "Light Hammer", "Mace", "Quarterstaff", "Sickle",
                  "Spear", "Crossbow, Light", "Dart", "Shortbow", "Sling"]
MARTIAL_WEAPONS = ['Battleaxe', 'Blowgun', 'Flail', 'Glaive', 'Greataxe', 'Greatsword', 'Halberd', 'Crossbow, Hand',
                   'Crossbow, Heavy', 'Lance', 'Longbow', 'Longsword', 'Maul', 'Morningstar', 'Net', 'Pike', 'Rapier',
                   'Scimitar', 'Shortsword', 'Trident', 'War Pick', 'Warhammer', 'Whip', 'Pistol', 'Musket',
                   'Automatic Pistol', 'Revolver', 'Hunting Rifle', 'Automatic Rifle', 'Shotgun', 'Laser Pistol',
                   'Antimatter Rifle', 'Laser Rifle']
HOUSERULE_SKILL_MAP = {
    3: 'acrobatics', 11: 'animalHandling', 6: 'arcana', 2: 'athletics', 16: 'deception', 7: 'history',
    12: 'insight', 17: 'intimidation', 8: 'investigation', 13: 'medicine', 9: 'nature', 14: 'perception',
    18: 'performance', 19: 'persuasion', 10: 'religion', 4: 'sleightOfHand', 5: 'stealth', 15: 'survival'
}


class BeyondSheetParser(SheetLoaderABC):
    def __init__(self, charId):
        super(BeyondSheetParser, self).__init__(charId)

        self.stats = None
        self.levels = None
        self.prof = None
        self.calculated_stats = collections.defaultdict(lambda: 0)
        self.set_calculated_stats = set()

    async def load_character(self, owner_id: str, args):
        """
        Downloads and parses the character data, returning a fully-formed Character object.
        :raises ExternalImportError if something went wrong during the import that we can expect
        :raises Exception if something weirder happened
        """
        await self.get_character()

        upstream = f"beyond-{self.url}"
        active = False
        sheet_type = "beyond"
        import_version = 15
        name = self.character_data['name'].strip()
        description = self.character_data['traits']['appearance']
        image = self.character_data.get('avatarUrl') or ''

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
        race = self.character_data['race']['fullName']
        background = self.get_background()

        character = Character(
            owner_id, upstream, active, sheet_type, import_version, name, description, image, stats, levels, attacks,
            skills, resistances, saves, ac, max_hp, hp, temp_hp, cvars, options, overrides, consumables, death_saves,
            spellbook, live, race, background
        )
        return character

    async def get_character(self):
        charId = self.url
        character = None
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{API_BASE}{charId}/json") as resp:
                log.debug(f"DDB returned {resp.status}")
                if resp.status == 200:
                    character = await resp.json()
                elif resp.status == 404:
                    raise ExternalImportError("Error: I do not have permission to view this character sheet. "
                                              "Make sure you've generated a sharable link for your character.")
                elif resp.status == 429:
                    raise ExternalImportError("Too many people are trying to import characters! Please try again in "
                                              "a few minutes.")
                else:
                    raise ExternalImportError(f"Beyond returned an error: {resp.status} - {resp.reason}")
        character['_id'] = charId
        self.character_data = character
        self.calculate_stats()
        return character

    def get_stats(self) -> BaseStats:
        """Returns a dict of stats."""
        if self.character_data is None: raise Exception('You must call get_character() first.')
        if self.stats: return self.stats
        character = self.character_data

        profByLevel = floor(self.get_levels().total_level / 4 + 1.75)
        prof_bonus = self.get_stat('proficiency-bonus', base=int(profByLevel))

        stat_dict = {}
        for i, stat in enumerate(('strength', 'dexterity', 'constitution', 'intelligence', 'wisdom', 'charisma')):
            base = next(s for s in character['stats'] if s['id'] == i + 1)['value']
            bonus = next(s for s in character['bonusStats'] if s['id'] == i + 1)['value'] or 0
            override = next(s for s in character['overrideStats'] if s['id'] == i + 1)['value']
            stat_dict[stat] = override or self.get_stat(f"{stat}-score", base=base + bonus)

        stats = BaseStats(prof_bonus, **stat_dict)

        self.stats = stats
        return stats

    def get_levels(self) -> Levels:
        """Returns a dict with the character's level and class levels."""
        if self.character_data is None: raise Exception('You must call get_character() first.')
        if self.levels: return self.levels
        character = self.character_data
        levels = collections.defaultdict(lambda: 0)
        for _class in character.get('classes', []):
            levelName = _class.get('definition', {}).get('name')
            levels[levelName] += _class.get('level')

        out = {}
        for level, v in levels.items():
            cleaned_name = re.sub(r'[.$]', '_', level)
            out[cleaned_name] = v

        level_obj = Levels(out)
        self.levels = level_obj
        return level_obj

    def get_attacks(self):
        """Returns a list of dicts of all of the character's attacks."""
        if self.character_data is None: raise Exception('You must call get_character() first.')
        attacks = []
        used_names = set()

        def extend(parsed_attacks):
            for atk in parsed_attacks:
                if atk['name'] in used_names:
                    num = 2
                    while f"{atk['name']}{num}" in used_names:
                        num += 1
                    atk['name'] = f"{atk['name']}{num}"
            attacks.extend(parsed_attacks)
            used_names.update(a['name'] for a in parsed_attacks)

        for src in self.character_data['actions'].values():
            for action in src:
                if action['displayAsAttack']:
                    extend(self.parse_attack(action, "action"))
        for action in self.character_data['customActions']:
            extend(self.parse_attack(action, "customAction"))
        for item in self.character_data['inventory']:
            if item['equipped'] and (item['definition']['filterType'] == "Weapon" or item.get('displayAsAttack')):
                extend(self.parse_attack(item, "item"))

        if 'Unarmed Strike' not in [a['name'] for a in attacks]:
            extend(self.parse_attack(None, 'unarmed'))
        return attacks

    def get_skills_and_saves(self):
        """Returns a dict of all the character's skills."""
        if self.character_data is None: raise Exception('You must call get_character() first.')
        character = self.character_data
        stats = self.get_stats()
        profBonus = stats.prof_bonus

        profs = dict()
        bonuses = dict()

        for modtype in character['modifiers'].values():  # calculate proficiencies in all skills
            for mod in modtype:
                mod['subType'] = mod['subType'].replace("-saving-throws", "Save")
                if mod['type'] == 'half-proficiency':
                    profs[mod['subType']] = max(profs.get(mod['subType'], 0), 0.5)
                elif mod['type'] == 'proficiency':
                    profs[mod['subType']] = max(profs.get(mod['subType'], 0), 1)
                elif mod['type'] == 'expertise':
                    profs[mod['subType']] = 2
                elif mod['type'] == 'bonus':
                    if not mod['isGranted']:
                        continue
                    if mod['statId'] is not None:
                        bonuses[mod['subType']] = bonuses.get(mod['subType'], 0) + self.stat_from_id(mod['statId'])
                    else:
                        bonuses[mod['subType']] = bonuses.get(mod['subType'], 0) + (mod['value'] or 0)

        profs['animalHandling'] = profs.get('animal-handling', 0)
        profs['sleightOfHand'] = profs.get('sleight-of-hand', 0)

        skills = {}
        for skill in SKILL_NAMES:  # add proficiency and bonuses to skills
            relevantprof = profs.get(skill, 0)
            relevantbonus = bonuses.get(skill, 0)
            if 'ability-checks' in profs:
                relevantprof = max(relevantprof, profs['ability-checks'])
            if 'ability-checks' in bonuses:
                relevantbonus += bonuses['ability-checks']
            skills[skill] = Skill(
                floor(stats.get_mod(SKILL_MAP[skill]) + (profBonus * relevantprof) + relevantbonus),
                relevantprof, relevantbonus
            )

        saves = {}
        for save in SAVE_NAMES:  # add proficiency and bonuses to skills
            relevantprof = profs.get(save, 0)
            relevantbonus = bonuses.get(save, 0)
            if 'saving-throws' in profs:
                relevantprof = max(relevantprof, profs['saving-throws'])
            if 'saving-throws' in bonuses:
                relevantbonus += bonuses['saving-throws']
            saves[save] = Skill(
                floor(stats.get_mod(SKILL_MAP[save]) + (profBonus * relevantprof) + relevantbonus),
                relevantprof, relevantbonus
            )

        ignored_ids = set()
        for charval in self.character_data['characterValues']:
            if charval['valueId'] in HOUSERULE_SKILL_MAP and charval['valueId'] not in ignored_ids:
                skill_name = HOUSERULE_SKILL_MAP[charval['valueId']]
                if charval['typeId'] == 23:  # override
                    skills[skill_name] = Skill(charval['value'])
                    ignored_ids.add(charval['valueId'])  # this must be the final value so we stop looking
                elif charval['typeId'] in {24, 25}:  # PROBABLY skill magic/misc bonus
                    skills[skill_name].value += charval['value']
                    skills[skill_name].bonus += charval['value']
                elif charval['typeId'] == 26:  # proficiency stuff
                    relevantprof = profs.get(skill_name, 0)
                    skills[skill_name].value -= relevantprof * profBonus
                    if charval['value'] == 0:  # no prof, don't need to do anything
                        skills[skill_name].prof = 0
                    elif charval['value'] == 1:  # half prof, round down
                        skills[skill_name].value += profBonus // 2
                        skills[skill_name].prof = 0.5
                    elif charval['value'] == 2:  # half, round up
                        skills[skill_name].value += ceil(profBonus / 2)
                        skills[skill_name].prof = 0.5
                    elif charval['value'] == 3:  # full
                        skills[skill_name].value += profBonus
                        skills[skill_name].prof = 1
                    elif charval['value'] == 4:  # double
                        skills[skill_name].value += profBonus * 2
                        skills[skill_name].prof = 2

        skills = Skills(skills)
        saves = Saves(saves)

        return skills, saves

    def get_resistances(self):
        resist = {
            'resist': [],
            'immune': [],
            'vuln': []
        }
        for modtype in self.character_data['modifiers'].values():
            for mod in modtype:
                if mod['type'] == 'resistance':
                    resist['resist'].append(mod['subType'])
                elif mod['type'] == 'immunity':
                    resist['immune'].append(mod['subType'])
                elif mod['type'] == 'vulnerability':
                    resist['vuln'].append(mod['subType'])
        return Resistances.from_dict(resist)

    def get_ac(self):
        min_base_armor = self.get_stat('minimum-base-armor')
        base = min_base_armor or 10
        armortype = None
        shield = 0
        for item in self.character_data['inventory']:
            if item['equipped'] and item['definition']['filterType'] == 'Armor':
                _type = item['definition']['type']
                if _type == "Shield":
                    shield = 2
                else:
                    base = item['definition']['armorClass']
                    armortype = _type

        baseArmor = self.get_stat('armor-class', base=base)
        dexBonus = self.get_stats().get_mod('dex')
        maxDexBonus = self.get_stat('ac-max-dex-modifier', default=100)
        unarmoredBonus = self.get_stat('unarmored-armor-class')
        armoredBonus = self.get_stat('armored-armor-class')
        miscBonus = 0

        armored = armortype is not None

        for val in self.character_data['characterValues']:
            if val['typeId'] == 1:  # AC override
                return val['value']
            elif val['typeId'] == 2:  # AC magic bonus
                miscBonus += val['value']
            elif val['typeId'] == 3:  # AC misc bonus
                miscBonus += val['value']
            elif val['typeId'] == 4:  # AC+DEX override
                baseArmor = val['value']

        miscBonus += self.get_stat('dual-wield-armor-class')
        # todo hack for integrated protection

        if armortype == 'Medium Armor':
            maxDexBonus = 2
        elif armortype == 'Heavy Armor':
            maxDexBonus = 0

        # unarmored vs armored
        if not armored:
            armoredBonus = 0
            maxDexBonus = self.get_stat('ac-max-dex-unarmored-modifier', default=maxDexBonus)
            if not min_base_armor:
                dexBonus = self.get_stat('unarmored-dex-ac-bonus', base=dexBonus)
        else:
            unarmoredBonus = 0
            maxDexBonus = self.get_stat('ac-max-dex-armored-modifier', default=maxDexBonus)

        return baseArmor + min(dexBonus, maxDexBonus) + shield + armoredBonus + unarmoredBonus + miscBonus

    def get_hp(self):
        return self.character_data['overrideHitPoints'] or \
               (self.character_data['baseHitPoints'] +
                (self.get_stat('hit-points-per-level',
                               base=self.get_stats().get_mod('con')) * self.get_levels().total_level))

    def get_spellbook(self):
        if self.character_data is None: raise Exception('You must call get_character() first.')
        spellcasterLevel = 0
        castingClasses = 0
        spellMod = 0
        pactSlots = 0
        pactLevel = 1
        for _class in self.character_data['classes']:
            castingAbility = _class['definition']['spellCastingAbilityId'] or \
                             (_class['subclassDefinition'] or {}).get('spellCastingAbilityId')
            if castingAbility:
                castingClasses += 1
                casterMult = CASTER_TYPES.get(_class['definition']['name'], 1)
                spellcasterLevel += _class['level'] * casterMult
                spellMod = max(spellMod, self.stat_from_id(castingAbility))
            if _class['definition']['name'] == 'Warlock':
                pactSlots = pact_slots_by_level(_class['level'])
                pactLevel = pact_level_by_level(_class['level'])

        if castingClasses > 1:
            spellcasterLevel = floor(spellcasterLevel)
        else:
            if spellcasterLevel >= 1:
                spellcasterLevel = ceil(spellcasterLevel)
            else:
                spellcasterLevel = 0
        log.debug(f"Caster level: {spellcasterLevel}")

        slots = {}
        for lvl in range(1, 10):
            slots[str(lvl)] = SLOTS_PER_LEVEL[lvl](spellcasterLevel)
        slots[str(pactLevel)] += pactSlots

        prof = self.get_stats().prof_bonus
        attack_bonus_bonus = self.get_stat("spell-attacks")
        dc = 8 + spellMod + prof
        sab = spellMod + prof + attack_bonus_bonus

        spellnames = []
        for src in self.character_data['classSpells']:
            spellnames.extend(s['definition']['name'].replace('\u2019', "'") for s in src['spells'])
        for src in self.character_data['spells'].values():
            spellnames.extend(s['definition']['name'].replace('\u2019', "'") for s in src)

        spells = []
        for value in spellnames:
            result = search(c.spells, value, lambda sp: sp.name, strict=True)
            if result and result[0] and result[1]:
                spells.append(SpellbookSpell(result[0].name, True))
            elif len(value) > 2:
                spells.append(SpellbookSpell(value))

        spellbook = Spellbook(slots, slots, spells, dc, sab, self.get_levels().total_level)
        return spellbook

    def get_background(self):
        if not self.character_data['background']['definition']:
            return None
        if not self.character_data['background']['hasCustomBackground']:
            return self.character_data['background']['definition']['name']
        return "Custom"

    # helper funcs
    def get_stat(self, stat, base=0, default=0):
        """Calculates the final value of a stat, based on modifiers and feats."""
        if stat in self.set_calculated_stats:
            return self.calculated_stats[stat]
        bonus = self.calculated_stats.get(stat, default)
        return base + bonus

    def stat_from_id(self, _id):
        if _id in range(1, 7):
            return self.get_stats().get_mod(('str', 'dex', 'con',
                                             'int', 'wis', 'cha')[_id - 1])
        return 0

    def parse_attack(self, atkIn, atkType):
        """Calculates and returns a list of dicts."""
        if self.character_data is None: raise Exception('You must call get_character() first.')
        prof = self.get_stats().prof_bonus
        out = []

        if atkType == 'action':
            if atkIn['dice'] is None:
                return []  # thanks DDB
            isProf = atkIn['isProficient']
            atkBonus = None
            dmgBonus = ""
            if atkIn["abilityModifierStatId"]:
                atkBonus = self.stat_from_id(atkIn['abilityModifierStatId']) + (prof if isProf else 0)
                dmgBonus = f"+{self.stat_from_id(atkIn['abilityModifierStatId'])}"
            attack = Attack(
                atkIn['name'], atkBonus, f"{atkIn['dice']['diceString']}{dmgBonus}[{parse_dmg_type(atkIn)}]",
                atkIn['snippet']
            )
            out.append(attack)
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
                dmgBonus += self.get_stat('natural-attacks-damage')

            damage = f"{atkIn['diceCount']}d{atkIn['diceType']}+{dmgBonus}[{parse_dmg_type(atkIn)}]"
            attack = Attack(
                atkIn['name'], atkBonus, damage, atkIn['snippet']
            )
            out.append(attack)
        elif atkType == 'item':
            itemdef = atkIn['definition']
            weirdBonuses = self.get_specific_item_bonuses(atkIn['id'])
            isProf = self.get_prof(itemdef['type']) or weirdBonuses['isPact']
            magicBonus = sum(
                m['value'] for m in itemdef['grantedModifiers'] if m['type'] == 'bonus' and m['subType'] == 'magic')
            modBonus = self.get_relevant_atkmod(itemdef) if not weirdBonuses['isHex'] else self.stat_from_id(6)

            dmgBonus = modBonus + magicBonus + weirdBonuses['damage']
            toHitBonus = (prof if isProf else 0) + magicBonus + weirdBonuses['attackBonus']

            is_melee = not 'Range' in [p['name'] for p in itemdef['properties']]
            is_one_handed = not 'Two-Handed' in [p['name'] for p in itemdef['properties']]
            is_weapon = itemdef['filterType'] == 'Weapon'

            if is_melee and is_one_handed:
                dmgBonus += self.get_stat('one-handed-melee-attacks-damage')
            if not is_melee and is_weapon:
                toHitBonus += self.get_stat('ranged-weapon-attacks')

            damage = None
            if itemdef['fixedDamage'] or itemdef['damage']:
                damage = f"{itemdef['fixedDamage'] or itemdef['damage']['diceString']}+{dmgBonus}" \
                    f"[{itemdef['damageType'].lower()}" \
                    f"{'^' if itemdef['magic'] or weirdBonuses['isPact'] else ''}]"

            atkBonus = weirdBonuses['attackBonusOverride'] or modBonus + toHitBonus
            details = html2text.html2text(itemdef['description'], bodywidth=0).strip()
            attack = Attack(
                itemdef['name'], atkBonus, damage, details
            )
            out.append(attack)

            if 'Versatile' in [p['name'] for p in itemdef['properties']]:
                versDmg = next(p['notes'] for p in itemdef['properties'] if p['name'] == 'Versatile')
                damage = f"{versDmg}+{dmgBonus}[{itemdef['damageType'].lower()}" \
                    f"{'^' if itemdef['magic'] or weirdBonuses['isPact'] else ''}]"
                attack = Attack(
                    f"2-Handed {itemdef['name']}", atkBonus, damage, details
                )
                out.append(attack)
        elif atkType == 'unarmed':
            monk_level = self.get_levels().get('Monk')
            ability_mod = self.stat_from_id(1) if not monk_level else max(self.stat_from_id(1), self.stat_from_id(2))
            if not monk_level:
                dmg = 1 + ability_mod
            elif monk_level < 5:
                dmg = f"1d4+{ability_mod}"
            elif monk_level < 11:
                dmg = f"1d6+{ability_mod}"
            elif monk_level < 17:
                dmg = f"1d8+{ability_mod}"
            else:
                dmg = f"1d10+{ability_mod}"
            atkBonus = self.get_stats().prof_bonus

            atkBonus += self.get_stat('natural-attacks')
            natural_bonus = self.get_stat('natural-attacks-damage')
            if natural_bonus:
                dmg = f"{dmg}+{natural_bonus}"

            attack = Attack(
                "Unarmed Strike", ability_mod + atkBonus, f"{dmg}[bludgeoning]"
            )
            out.append(attack)
        return [a.to_dict() for a in out]

    def calculate_stats(self):
        ignored = set()
        has_stat_bonuses = []  # [{type, stat, subtype}]
        for modtype in self.character_data['modifiers'].values():  # {race: [], class: [], ...}
            for mod in modtype:  # [{}, ...]
                mod_type = mod['subType']  # e.g. 'strength-score'
                if mod_type in ignored:
                    continue
                if mod['statId']:
                    has_stat_bonuses.append({'subtype': mod_type, 'type': mod['type'], 'stat': mod['statId']})

                if mod['type'] == 'bonus':
                    if mod_type in self.set_calculated_stats:
                        continue
                    self.calculated_stats[mod_type] += (mod['value'] or 0)
                elif mod['type'] == 'damage':
                    self.calculated_stats[f"{mod_type}-damage"] += (mod['value'] or 0)
                elif mod['type'] == 'set':
                    if mod_type in self.set_calculated_stats and self.calculated_stats[mod_type] > (mod['value'] or 0):
                        continue
                    self.calculated_stats[mod_type] = (mod['value'] or 0)
                    self.set_calculated_stats.add(mod_type)
                elif mod['type'] == 'ignore':
                    self.calculated_stats[mod_type] = 0
                    ignored.add(mod_type)
        for mod in has_stat_bonuses:
            mod_type = mod['subtype']
            if mod_type in ignored:
                continue
            stat_mod = self.stat_from_id(mod['stat'])
            if mod['type'] == 'bonus':
                self.calculated_stats[mod_type] += stat_mod
            elif mod['type'] == 'damage':
                self.calculated_stats[f"{mod_type}-damage"] += stat_mod
            elif mod['type'] == 'set':
                self.calculated_stats[mod_type] = stat_mod

    def get_prof(self, proftype):
        if not self.prof:
            p = []
            for modtype in self.character_data['modifiers'].values():
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
            'isPact': False,
            'isHex': False
        }
        for val in self.character_data['characterValues']:
            if not val['valueId'] == itemId: continue
            if val['typeId'] == 10:  # damage bonus
                out['damage'] += val['value']
            elif val['typeId'] == 12:  # to hit bonus
                out['attackBonus'] += val['value']
            elif val['typeId'] == 13:  # to hit override
                out['attackBonusOverride'] = max(val['value'], out['attackBonusOverride'])
            elif val['typeId'] == 28:  # pact weapon
                out['isPact'] = True
            elif val['typeId'] == 29:  # hex weapon
                out['isHex'] = True
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
    return min((level + 1) // 2, 5)


if __name__ == '__main__':
    import asyncio
    import json
    from utils.argparser import argparse

    while True:
        url = input("DDB Character ID: ").strip()
        parser = BeyondSheetParser(url)
        char = asyncio.get_event_loop().run_until_complete(parser.load_character("", argparse("")))
        print(json.dumps(parser.calculated_stats, indent=2))
        input("press enter to view character data")
        print(json.dumps(char.to_dict(), indent=2))
