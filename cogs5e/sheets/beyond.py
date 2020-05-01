"""
Created on Feb 14, 2017

@author: andrew
"""

import collections
import logging
import re
from math import ceil, floor

import aiohttp
import html2text

from cogs5e.funcs.lookupFuncs import compendium
from cogs5e.models.character import Character
from cogs5e.models.errors import ExternalImportError
from cogs5e.models.sheet.attack import Attack, AttackList
from cogs5e.models.sheet.base import BaseStats, Levels, Saves, Skill, Skills
from cogs5e.models.sheet.resistance import Resistances
from cogs5e.models.sheet.spellcasting import Spellbook, SpellbookSpell
from cogs5e.sheets.abc import SHEET_VERSION, SheetLoaderABC
from utils.constants import SAVE_NAMES, SKILL_MAP, SKILL_NAMES
from utils.functions import search

try:
    from credentials import ddb_json_headers as HEADERS
except ImportError:
    HEADERS = {}

log = logging.getLogger(__name__)

API_BASE = "https://www.dndbeyond.com/character/"
DAMAGE_TYPES = {1: "bludgeoning", 2: "piercing", 3: "slashing", 4: "necrotic", 5: "acid", 6: "cold", 7: "fire",
                8: "lightning", 9: "thunder", 10: "poison", 11: "psychic", 12: "radiant", 13: "force"}
CASTER_TYPES = {"Barbarian": 0, "Bard": 1, "Cleric": 1, "Druid": 1, "Fighter": 0.333, "Monk": 0, "Paladin": 0.5,
                "Ranger": 0.5, "Rogue": 0.333, "Sorcerer": 1, "Warlock": 0, "Wizard": 1, "Artificer": 0.5}
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
RESIST_OVERRIDE_MAP = {
    1: ('Bludgeoning', 1), 2: ('Piercing', 1), 3: ('Slashing', 1), 4: ('Lightning', 1), 5: ('Thunder', 1),
    6: ('Poison', 1), 7: ('Cold', 1), 8: ('Radiant', 1), 9: ('Fire', 1), 10: ('Necrotic', 1), 11: ('Acid', 1),
    12: ('Psychic', 1), 17: ('Bludgeoning', 2), 18: ('Piercing', 2), 19: ('Slashing', 2), 20: ('Lightning', 2),
    21: ('Thunder', 2), 22: ('Poison', 2), 23: ('Cold', 2), 24: ('Radiant', 2), 25: ('Fire', 2), 26: ('Necrotic', 2),
    27: ('Acid', 2), 28: ('Psychic', 2), 33: ('Bludgeoning', 3), 34: ('Piercing', 3), 35: ('Slashing', 3),
    36: ('Lightning', 3), 37: ('Thunder', 3), 38: ('Poison', 3), 39: ('Cold', 3), 40: ('Radiant', 3), 41: ('Fire', 3),
    42: ('Necrotic', 3), 43: ('Acid', 3), 44: ('Psychic', 3), 47: ('Force', 1), 48: ('Force', 2), 49: ('Force', 3)
}
RESIST_TYPE_MAP = {
    1: "resist", 2: "immune", 3: "vuln"
}


class BeyondSheetParser(SheetLoaderABC):
    def __init__(self, charId):
        super(BeyondSheetParser, self).__init__(charId)

        self.stats = None
        self.levels = None
        self.prof = None
        self.calculated_stats = collections.defaultdict(lambda: 0)
        self.set_calculated_stats = set()
        self.calculations_complete = False
        self._all_features = set()

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
        import_version = SHEET_VERSION
        name = self.character_data['name'].strip()
        description = self.character_data['traits']['appearance']
        image = self.character_data.get('avatarUrl') or ''

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
        charId = self.url
        character = None
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{API_BASE}{charId}/json", headers=HEADERS) as resp:
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
        self._calculate_stats()
        self._load_features()
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

        if self.calculations_complete:
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
        """Returns an attacklist"""
        if self.character_data is None: raise Exception('You must call get_character() first.')
        attacks = AttackList()
        used_names = set()

        def extend(parsed_attacks):
            for atk in parsed_attacks:
                if atk.name in used_names:
                    num = 2
                    while f"{atk.name}{num}" in used_names:
                        num += 1
                    atk.name = f"{atk.name}{num}"
            attacks.extend(parsed_attacks)
            used_names.update(a.name for a in parsed_attacks)

        for src in self.character_data['actions'].values():
            for action in src:
                if action['displayAsAttack']:
                    extend(self.parse_attack(action, "action"))
        for action in self.character_data['customActions']:
            extend(self.parse_attack(action, "customAction"))
        for item in self.character_data['inventory']:
            if item['equipped'] and (item['definition']['filterType'] == "Weapon" or item.get('displayAsAttack')):
                extend(self.parse_attack(item, "item"))

        if 'Unarmed Strike' not in [a.name for a in attacks]:
            extend(self.parse_attack(None, 'unarmed'))
        return attacks

    def get_skills_and_saves(self):
        """Returns a dict of all the character's skills."""
        if self.character_data is None: raise Exception('You must call get_character() first.')
        stats = self.get_stats()
        profBonus = stats.prof_bonus

        profs = dict()
        bonuses = dict()
        advantages = collections.defaultdict(lambda: [])

        for mod in self.modifiers():
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
            elif mod['type'] == 'advantage' and not mod['restriction']:  # unconditional adv
                advantages[mod['subType']].append(True)
            elif mod['type'] == 'disadvantage' and not mod['restriction']:  # unconditional dis
                advantages[mod['subType']].append(False)

        profs['animalHandling'] = profs.get('animal-handling', 0)
        profs['sleightOfHand'] = profs.get('sleight-of-hand', 0)
        advantages['animalHandling'] = advantages['animal-handling']
        advantages['sleightOfHand'] = advantages['sleight-of-hand']

        def _simplify_adv(adv_list):
            adv_set = set(adv_list)
            if len(adv_set) == 1:
                return adv_set.pop()
            return None

        skills = {}
        for skill in SKILL_NAMES:  # add proficiency and bonuses to skills
            relevantprof = profs.get(skill, 0)
            relevantbonus = bonuses.get(skill, 0)
            relevantadv = _simplify_adv(advantages[skill])
            if 'ability-checks' in profs and skill != 'initiative':
                relevantprof = max(relevantprof, profs['ability-checks'])
            if 'ability-checks' in bonuses and skill != 'initiative':
                relevantbonus += bonuses['ability-checks']
            skills[skill] = Skill(
                floor(stats.get_mod(SKILL_MAP[skill]) + (profBonus * relevantprof) + relevantbonus),
                relevantprof, relevantbonus, adv=relevantadv
            )

        # saves
        saves = {}
        for save in SAVE_NAMES:  # add proficiency and bonuses to skills
            relevantprof = profs.get(save, 0)
            relevantbonus = bonuses.get(save, 0)
            relevantadv = _simplify_adv(advantages[save])
            if 'saving-throws' in profs:
                relevantprof = max(relevantprof, profs['saving-throws'])
            if 'saving-throws' in bonuses:
                relevantbonus += bonuses['saving-throws']
            saves[save] = Skill(
                floor(stats.get_mod(SKILL_MAP[save]) + (profBonus * relevantprof) + relevantbonus),
                relevantprof, relevantbonus, adv=relevantadv
            )

        # values
        ignored_ids = set()
        for charval in self.character_data['characterValues']:
            if charval['value'] is None:
                continue

            if charval['typeId'] == 39:  # misc saving throw bonus
                save_id = SAVE_NAMES[charval['valueId'] - 1]
                save_bonus = charval['value']
                saves[save_id].value += save_bonus
                saves[save_id].bonus += save_bonus
            elif charval['valueId'] in HOUSERULE_SKILL_MAP and charval['valueId'] not in ignored_ids:
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
            'resist': set(),
            'immune': set(),
            'vuln': set()
        }
        for mod in self.modifiers():
            if mod['type'] == 'resistance':
                resist['resist'].add(mod['subType'].lower())
            elif mod['type'] == 'immunity':
                resist['immune'].add(mod['subType'].lower())
            elif mod['type'] == 'vulnerability':
                resist['vuln'].add(mod['subType'].lower())

        for override in self.character_data['customDefenseAdjustments']:
            if not override['type'] == 2:
                continue
            if override['id'] not in RESIST_OVERRIDE_MAP:
                continue

            dtype, rtype = RESIST_OVERRIDE_MAP[override['id']]
            resist[RESIST_TYPE_MAP[rtype]].add(dtype.lower())

        resist = {k: list(v) for k, v in resist.items()}
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
        minDexBonus = -100
        unarmoredBonus = self.get_stat('unarmored-armor-class')
        armoredBonus = self.get_stat('armored-armor-class')
        miscBonus = 0

        armored = armortype is not None

        for val in self.character_data['characterValues']:
            if val['value'] is None: continue
            if val['typeId'] == 1:  # AC override
                return val['value']
            elif val['typeId'] == 2:  # AC magic bonus
                miscBonus += val['value']
            elif val['typeId'] == 3:  # AC misc bonus
                miscBonus += val['value']
            elif val['typeId'] == 4:  # AC+DEX override
                baseArmor = val['value']

        # Dual Wielder feat
        miscBonus += self.get_stat('dual-wield-armor-class')

        if armortype == 'Medium Armor':
            maxDexBonus = 2
        elif armortype == 'Heavy Armor' or self.get_race() == 'Tortle':  # HACK - tortle natural armor
            maxDexBonus = 0
            minDexBonus = 0

        # unarmored vs armored
        if not armored:
            armoredBonus = 0
            maxDexBonus = self.get_stat('ac-max-dex-unarmored-modifier', default=maxDexBonus)
            if not min_base_armor:
                dexBonus = self.get_stat('unarmored-dex-ac-bonus', base=dexBonus)
        else:
            unarmoredBonus = 0
            maxDexBonus = self.get_stat('ac-max-dex-armored-modifier', default=maxDexBonus)

        dexBonus = max(minDexBonus, min(dexBonus, maxDexBonus))

        return baseArmor + dexBonus + shield + armoredBonus + unarmoredBonus + miscBonus

    def get_hp(self):
        return self.character_data['overrideHitPoints'] or \
               (self.character_data['baseHitPoints'] +
                (self.get_stat('hit-points-per-level',
                               base=self.get_stats().get_mod('con')) * self.get_levels().total_level))

    def get_spellbook(self):
        if self.character_data is None: raise Exception('You must call get_character() first.')
        spellcasterLevel = 0
        castingClasses = 0
        spell_mod = 0
        pactSlots = 0
        pactLevel = 1
        hasSpells = False
        for _class in self.character_data['classes']:
            castingAbility = _class['definition']['spellCastingAbilityId'] or \
                             (_class['subclassDefinition'] or {}).get('spellCastingAbilityId')
            if castingAbility:
                casterMult = CASTER_TYPES.get(_class['definition']['name'], 1)
                spellcasterLevel += _class['level'] * casterMult
                castingClasses += 1 if casterMult else 0  # warlock multiclass fix
                spell_mod = max(spell_mod, self.stat_from_id(castingAbility))

                class_features = {cf['name'] for cf in _class['definition']['classFeatures'] if
                                  cf['requiredLevel'] <= _class['level']}
                if _class['subclassDefinition']:
                    class_features.update({cf['name'] for cf in _class['subclassDefinition']['classFeatures'] if
                                           cf['requiredLevel'] <= _class['level']})

                hasSpells = 'Spellcasting' in class_features or hasSpells

            if _class['definition']['name'] == 'Warlock':
                pactSlots = pact_slots_by_level(_class['level'])
                pactLevel = pact_level_by_level(_class['level'])

        if castingClasses > 1:
            spellcasterLevel = floor(spellcasterLevel)
        else:
            if hasSpells:
                spellcasterLevel = ceil(spellcasterLevel)
            else:
                spellcasterLevel = 0
        log.debug(f"Caster level: {spellcasterLevel}")

        slots = {}
        for lvl in range(1, 10):
            slots[str(lvl)] = SLOTS_PER_LEVEL[lvl](spellcasterLevel)
        slots[str(pactLevel)] += pactSlots

        prof = self.get_stats().prof_bonus
        save_dc_bonus = max(self.get_stat("spell-save-dc"), self.get_stat("warlock-spell-save-dc"))
        attack_bonus_bonus = max(self.get_stat("spell-attacks"), self.get_stat("warlock-spell-attacks"))
        dc = 8 + spell_mod + prof + save_dc_bonus
        sab = spell_mod + prof + attack_bonus_bonus

        spellnames = []
        for src in self.character_data['classSpells']:
            spellnames.extend(s['definition']['name'].replace('\u2019', "'") for s in src['spells'])
        for src in self.character_data['spells'].values():
            spellnames.extend(s['definition']['name'].replace('\u2019', "'") for s in src)

        spells = []
        for value in spellnames:
            result = search(compendium.spells, value, lambda sp: sp.name, strict=True)
            if result and result[0] and result[1]:
                spells.append(SpellbookSpell(result[0].name, True))
            elif len(value) > 2:
                spells.append(SpellbookSpell(value))

        spellbook = Spellbook(slots, slots, spells, dc, sab, self.get_levels().total_level, spell_mod or None)
        return spellbook

    def get_race(self):
        return self.character_data['race']['fullName']

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

        def monk_scale():
            monk_level = self.get_levels().get('Monk')
            if not monk_level:
                monk_dice_size = 0
            elif monk_level < 5:
                monk_dice_size = 4
            elif monk_level < 11:
                monk_dice_size = 6
            elif monk_level < 17:
                monk_dice_size = 8
            else:
                monk_dice_size = 10
            return monk_dice_size

        if atkType == 'action':
            if atkIn['dice'] is None:
                return []  # thanks DDB
            isProf = atkIn['isProficient']
            atk_bonus = None
            dmgBonus = None

            dice_size = max(monk_scale(), atkIn['dice']['diceValue'])
            base_dice = f"{atkIn['dice']['diceCount']}d{dice_size}"

            if atkIn["abilityModifierStatId"]:
                atk_bonus = self.stat_from_id(atkIn['abilityModifierStatId'])
                dmgBonus = self.stat_from_id(atkIn['abilityModifierStatId'])

            if atkIn["isMartialArts"] and self.get_levels().get("Monk"):
                atk_bonus = max(atk_bonus, self.stat_from_id(2))  # allow using dex
                dmgBonus = max(dmgBonus, self.stat_from_id(2))

            if isProf and atk_bonus is not None:
                atk_bonus += prof

            if dmgBonus:
                damage = f"{base_dice}+{dmgBonus}[{parse_dmg_type(atkIn)}]"
            else:
                damage = f"{base_dice}[{parse_dmg_type(atkIn)}]"
            attack = Attack.new(
                atkIn['name'], atk_bonus, damage,
                atkIn['snippet']
            )
            out.append(attack)
        elif atkType == 'customAction':
            isProf = atkIn['isProficient']
            dmgBonus = (atkIn['fixedValue'] or 0) + (atkIn['damageBonus'] or 0)
            atk_bonus = None
            if atkIn['statId']:
                atk_bonus = self.stat_from_id(atkIn['statId']) + (prof if isProf else 0) + (atkIn['toHitBonus'] or 0)
                dmgBonus = (atkIn['fixedValue'] or 0) + self.stat_from_id(atkIn['statId']) + (atkIn['damageBonus'] or 0)

            if atkIn['attackSubtype'] == 3:  # natural weapons
                if atk_bonus is not None:
                    atk_bonus += self.get_stat('natural-attacks')
                dmgBonus += self.get_stat('natural-attacks-damage')

            damage = f"{atkIn['diceCount']}d{atkIn['diceType']}+{dmgBonus}[{parse_dmg_type(atkIn)}]"
            attack = Attack.new(
                atkIn['name'], atk_bonus, damage, atkIn['snippet']
            )
            out.append(attack)
        elif atkType == 'item':
            itemdef = atkIn['definition']
            character_item_bonuses = self.get_specific_item_bonuses(atkIn['id'])
            item_specific_bonuses = self._item_modifiers(itemdef)

            item_properties = itemdef['properties'] + [collections.defaultdict(lambda: None, name=n) for n in
                                                       item_specific_bonuses['extraProperties']]

            isProf = self.get_prof(itemdef['type']) or character_item_bonuses['isPact']
        
            mod_bonus = self.get_relevant_atkmod(itemdef, item_properties)
            if character_item_bonuses['isHex']:
                mod_bonus = max(mod_bonus, self.stat_from_id(6))
            if itemdef['magic'] and self.get_levels().get('Artificer') and "Battle Ready" in self._all_features:
                mod_bonus = max(mod_bonus, self.stat_from_id(4))
        
            magic_bonus = item_specific_bonuses['magicBonus']
            item_dmg_bonus = self.get_stat(f"{itemdef['type'].lower()}-damage")

            dmgBonus = mod_bonus + magic_bonus + character_item_bonuses['damage'] + item_dmg_bonus
            toHitBonus = (prof if isProf else 0) + magic_bonus + character_item_bonuses['attackBonus']

            is_melee = not 'Range' in [p['name'] for p in item_properties]
            is_one_handed = not 'Two-Handed' in [p['name'] for p in item_properties]
            is_weapon = itemdef['filterType'] == 'Weapon'
            has_gwf = "Great Weapon Fighting" in self._all_features

            if is_melee and is_one_handed:
                dmgBonus += self.get_stat('one-handed-melee-attacks-damage')

            if not is_melee and is_weapon:
                toHitBonus += self.get_stat('ranged-weapon-attacks')

            if character_item_bonuses['isPact'] and self._improved_pact_weapon_applies(itemdef):
                dmgBonus += 1
                toHitBonus += 1

            base_dice = None
            if itemdef['fixedDamage']:
                base_dice = itemdef['fixedDamage']
            elif itemdef['damage']:
                if not itemdef['isMonkWeapon']:
                    base_dice = f"{itemdef['damage']['diceCount']}d{itemdef['damage']['diceValue']}"
                else:
                    dice_size = max(monk_scale(), itemdef['damage']['diceValue'])
                    base_dice = f"{itemdef['damage']['diceCount']}d{dice_size}"

            damage_type = (item_specific_bonuses['replaceDamageType'] or itemdef['damageType'] or 'unknown').lower()
            if itemdef['magic'] or character_item_bonuses['isPact']:
                damage_type = f"magical {damage_type}"
            if character_item_bonuses['isAdamantine']:
                damage_type = f"adamantine {damage_type}"
            if character_item_bonuses['isSilver']:
                damage_type = f"silvered {damage_type}"

            if base_dice and is_melee and has_gwf and not is_one_handed:
                base_dice += "ro<3"      

            if base_dice:
                damage = f"{base_dice} + {dmgBonus} [{damage_type}]"
            else:
                damage = None

            atk_bonus = character_item_bonuses['attackBonusOverride'] or mod_bonus + toHitBonus
            details = character_item_bonuses['note'] or html2text.html2text(itemdef['description'], bodywidth=0).strip()
            name = character_item_bonuses['name'] or itemdef['name']
            attack = Attack.new(
                name, atk_bonus, damage, details
            )
            out.append(attack)

            if 'Versatile' in [p['name'] for p in item_properties]:
                versDmg = next(p['notes'] for p in item_properties if p['name'] == 'Versatile')
                if has_gwf:
                    versDmg += "ro<3"
                damage = f"{versDmg} + {dmgBonus} [{damage_type}]"
                attack = Attack.new(
                    f"2-Handed {name}", atk_bonus, damage, details
                )
                out.append(attack)
        elif atkType == 'unarmed':
            dice_size = monk_scale()
            ability_mod = self.stat_from_id(1) if not self.get_levels().get('Monk') else max(self.stat_from_id(1),
                                                                                             self.stat_from_id(2))
            character_item_bonuses = self.get_specific_item_bonuses(1)  # magic number: Unarmed Strike ID
            if dice_size:
                dmg = f"1d{dice_size}+{ability_mod}"
            else:
                dmg = 1 + ability_mod

            atk_bonus = character_item_bonuses['attackBonusOverride'] or \
                        (prof + self.get_stat('natural-attacks') + character_item_bonuses['attackBonus'])
            dmg_bonus = self.get_stat('natural-attacks-damage') + character_item_bonuses['damage']
            if dmg_bonus:
                dmg = f"{dmg}+{dmg_bonus}"

            details = character_item_bonuses['note'] or None
            name = character_item_bonuses['name'] or "Unarmed Strike"

            attack = Attack.new(
                name, ability_mod + atk_bonus, f"{dmg}[bludgeoning]", details
            )
            out.append(attack)
        return out

    def _calculate_stats(self):
        ignored = set()

        def handle_mod(mod):
            mod_type = mod['subType']  # e.g. 'strength-score'
            if mod_type in ignored:
                return
            value = (mod['value'] or 0)
            if mod['statId']:
                value = self.stat_from_id(mod['statId'])

            if mod['type'] == 'bonus':
                if mod_type in self.set_calculated_stats:
                    return
                self.calculated_stats[mod_type] += value
            elif mod['type'] == 'damage':
                self.calculated_stats[f"{mod_type}-damage"] += value
            elif mod['type'] == 'set':
                if mod_type in self.set_calculated_stats and self.calculated_stats[mod_type] >= value:
                    return
                self.calculated_stats[mod_type] = value
                self.set_calculated_stats.add(mod_type)
            elif mod['type'] == 'ignore':
                self.calculated_stats[mod_type] = 0
                ignored.add(mod_type)

        for modifier in self.modifiers():
            handle_mod(modifier)

        self.calculations_complete = True

    def _load_features(self):
        """Loads all class/race/feat features a character has into a set."""

        def name_from_entity(entity):
            return entity['definition']['name']

        # race
        for racial_trait in self.character_data['race']['racialTraits']:
            self._all_features.add(name_from_entity(racial_trait))

        # class
        for klass in self.character_data['classes']:
            for class_feature in klass['classFeatures']:
                self._all_features.add(name_from_entity(class_feature))

            # subclass
            if klass['subclassDefinition']:
                for subclass_feature in klass['subclassDefinition']['classFeatures']:
                    self._all_features.add(subclass_feature['name'])

        # feats
        for feat in self.character_data['feats']:
            self._all_features.add(name_from_entity(feat))

        # options
        for option_list in self.character_data['options'].values():
            for option in option_list:
                self._all_features.add(name_from_entity(option))

    def get_prof(self, proftype):
        if not self.prof:
            p = []
            for mod in self.modifiers():
                if mod['type'] == 'proficiency':
                    if mod['subType'] == 'simple-weapons':
                        p.extend(SIMPLE_WEAPONS)
                    elif mod['subType'] == 'martial-weapons':
                        p.extend(MARTIAL_WEAPONS)
                    p.append(mod['friendlySubtypeName'])
            self.prof = p
        return proftype in self.prof

    def get_relevant_atkmod(self, itemdef, item_properties):
        if itemdef['attackType'] == 2:  # ranged, dex
            return self.stat_from_id(2)
        elif itemdef['attackType'] == 1:  # melee
            if 'Finesse' in [p['name'] for p in item_properties] or \
                    (itemdef['isMonkWeapon'] and self.get_levels().get('Monk')):  # finesse, monk weapon
                return max(self.stat_from_id(1), self.stat_from_id(2))
        return self.stat_from_id(1)  # strength

    def get_specific_item_bonuses(self, itemId):
        out = {
            'attackBonus': 0,
            'attackBonusOverride': 0,
            'damage': 0,
            'isPact': False,
            'isHex': False,
            'name': None,
            'note': None,
            'isSilver': False,
            'isAdamantine': False
        }
        for val in self.character_data['characterValues']:
            if not val['valueId'] == itemId: continue
            if val['typeId'] == 8:  # name
                out['name'] = val['value']
            elif val['typeId'] == 9:  # note
                out['note'] = val['value']
            elif val['typeId'] == 10:  # damage bonus
                out['damage'] += val['value']
            elif val['typeId'] == 12:  # to hit bonus
                out['attackBonus'] += val['value']
            elif val['typeId'] == 13:  # to hit override
                out['attackBonusOverride'] = max(val['value'], out['attackBonusOverride'])
            elif val['typeId'] == 20:  # silver
                out['isSilver'] = True
            elif val['typeId'] == 21:  # adamantine
                out['isAdamantine'] = True
            elif val['typeId'] == 28:  # pact weapon
                out['isPact'] = True
            elif val['typeId'] == 29:  # hex weapon
                out['isHex'] = True
        return out

    def modifiers(self):
        """Returns an iterator over granted character modifiers. Also sets a few things useful in later calculations."""
        for provider, modtype in self.character_data['modifiers'].items():  # {race: [], class: [], ...}
            if provider == 'item':  # we handle this by iterating over inventory to handle unequipped items
                continue
            for modifier in modtype:  # [{}, ...]
                yield modifier

        for item in self.character_data['inventory']:
            if not item['equipped']:
                continue
            for modifier in item['definition']['grantedModifiers']:
                if modifier['requiresAttunement'] and not item['isAttuned']:
                    continue
                yield modifier

    # ===== Specific helpers =====
    @staticmethod
    def _item_modifiers(itemdef):
        out = {
            'magicBonus': 0,
            'replaceDamageType': None,
            'extraProperties': []
        }
        for modifier in itemdef['grantedModifiers']:
            if modifier['type'] == 'bonus' and modifier['subType'] == 'magic':
                out['magicBonus'] += modifier['value']
            elif modifier['type'] == 'replace-damage-type':
                out['replaceDamageType'] = modifier['subType']
            elif modifier['type'] == 'weapon-property':
                out['extraProperties'].append(modifier['subType'])

        return out

    def _improved_pact_weapon_applies(self, itemdef):
        # precondition: item is a pact weapon
        # we must have IPW
        if 'Improved Pact Weapon' not in self._all_features:
            return False

        # item must not have a magical bonus
        if self._item_modifiers(itemdef)['magicBonus']:
            return False

        return True


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
        print(f"set: {parser.set_calculated_stats}")
        input("press enter to view character data")
        print(json.dumps(char.to_dict(), indent=2))
