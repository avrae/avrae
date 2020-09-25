"""
Created on Jan 19, 2017

@author: andrew
"""

import ast
import collections
import logging
import re
from math import ceil, floor

import draconic

from cogs5e.models.character import Character
from cogs5e.models.dicecloud.client import DicecloudClient
from cogs5e.models.dicecloud.errors import DicecloudException
from cogs5e.models.errors import ExternalImportError
from cogs5e.models.sheet.attack import Attack, AttackList
from cogs5e.models.sheet.base import BaseStats, Levels, Saves, Skill, Skills
from cogs5e.models.sheet.resistance import Resistances
from cogs5e.models.sheet.spellcasting import Spellbook, SpellbookSpell
from gamedata.compendium import compendium
from utils import config
from utils.constants import DAMAGE_TYPES, SAVE_NAMES, SKILL_MAP, SKILL_NAMES, STAT_NAMES
from utils.functions import search
from .abc import SHEET_VERSION, SheetLoaderABC

log = logging.getLogger(__name__)

CLASS_RESOURCES = ("expertiseDice", "ki", "rages", "sorceryPoints", "superiorityDice")
CLASS_RESOURCE_NAMES = {"expertiseDice": "Expertise Dice", "ki": "Ki", "rages": "Rages",
                        "sorceryPoints": "Sorcery Points", "superiorityDice": "Superiority Dice"}
CLASS_RESOURCE_RESETS = {"expertiseDice": 'short', "ki": 'short', "rages": 'long',
                         "sorceryPoints": 'long', "superiorityDice": 'short'}
API_BASE = "https://dicecloud.com/character/"
KEY = config.DICECLOUD_API_KEY


class DicecloudParser(SheetLoaderABC):
    def __init__(self, url):
        super(DicecloudParser, self).__init__(url)
        self.stats = None
        self.levels = None
        self.evaluator = DicecloudEvaluator()
        self._cache = {}

    async def load_character(self, ctx, args):
        """
        Downloads and parses the character data, returning a fully-formed Character object.
        :raises ExternalImportError if something went wrong during the import that we can expect
        :raises Exception if something weirder happened
        """
        owner_id = str(ctx.author.id)
        try:
            await self.get_character()
        except DicecloudException as e:
            raise ExternalImportError(f"Dicecloud returned an error: {e}")

        upstream = f"dicecloud-{self.url}"
        active = False
        sheet_type = "dicecloud"
        import_version = SHEET_VERSION
        name = self.character_data['characters'][0]['name'].strip()
        description = self.character_data['characters'][0]['description']
        image = self.character_data['characters'][0]['picture']

        stats = self.get_stats()
        levels = self.get_levels()
        attacks = self.get_attacks()

        skills, saves = self.get_skills_and_saves()

        resistances = self.get_resistances()
        ac = self.get_ac()
        max_hp = int(self.calculate_stat('hitPoints'))
        hp = max_hp
        temp_hp = 0

        cvars = {}
        options = {}
        overrides = {}
        death_saves = {}

        consumables = []
        if not args.last('nocc'):
            consumables = self.get_custom_counters()

        spellbook = self.get_spellbook()
        live = self.is_live()
        race = self.character_data['characters'][0]['race'].strip()
        background = self.character_data['characters'][0]['backstory'].strip()

        character = Character(
            owner_id, upstream, active, sheet_type, import_version, name, description, image, stats, levels, attacks,
            skills, resistances, saves, ac, max_hp, hp, temp_hp, cvars, options, overrides, consumables, death_saves,
            spellbook, live, race, background
        )
        return character

    async def get_character(self):
        """Saves the character JSON data to this object."""
        url = self.url
        character = await DicecloudClient.getInstance().get_character(url)
        character['_id'] = url
        self.character_data = character
        return character

    def get_stats(self) -> BaseStats:
        if self.character_data is None: raise Exception('You must call get_character() first.')
        if self.stats:
            return self.stats
        self.get_levels()

        stat_dict = {'proficiencyBonus': int(self.calculate_stat('proficiencyBonus'))}

        for stat in ('strength', 'dexterity', 'constitution', 'wisdom', 'intelligence', 'charisma'):
            stat_dict[stat] = int(self.calculate_stat(stat))
            stat_dict[stat + 'Mod'] = int(stat_dict[stat]) // 2 - 5
        self.evaluator.names.update(stat_dict)

        stats = BaseStats(stat_dict['proficiencyBonus'], stat_dict['strength'], stat_dict['dexterity'],
                          stat_dict['constitution'], stat_dict['intelligence'], stat_dict['wisdom'],
                          stat_dict['charisma'])

        self.stats = stats
        return stats

    def get_levels(self) -> Levels:
        """Returns a dict with the character's level and class levels."""
        if self.character_data is None: raise Exception('You must call get_character() first.')
        if self.levels:
            return self.levels
        character = self.character_data
        levels = collections.defaultdict(lambda: 0)
        for level in character.get('classes', []):
            if level.get('removed', False): continue
            level_name = level['name']
            levels[level_name] += level['level']

        out = {}
        for level, v in levels.items():
            cleaned_name = re.sub(r'[.$]', '_', level)
            out[cleaned_name] = v
            self.evaluator.names[f"{cleaned_name}Level"] = v

        level_obj = Levels(out)
        self.levels = level_obj
        self.evaluator.names['level'] = level_obj.total_level
        return level_obj

    def get_attacks(self):
        """Returns a list of dicts of all of the character's attacks."""
        if self.character_data is None: raise Exception('You must call get_character() first.')
        character = self.character_data
        attacks = AttackList()
        atk_names = set()
        for attack in character.get('attacks', []):
            if attack.get('enabled') and not attack.get('removed'):
                atk = self.parse_attack(attack)

                # unique naming
                atk_num = 2
                if atk.name in atk_names:
                    while f"{atk.name}{atk_num}" in atk_names:
                        atk_num += 1
                    atk.name = f"{atk.name}{atk_num}"
                atk_names.add(atk.name)

                attacks.append(atk)
        return attacks

    def get_skills_and_saves(self) -> (Skills, Saves):
        if self.character_data is None: raise Exception('You must call get_character() first.')
        character = self.character_data
        stats = self.get_stats()

        NAME_SET = set(SKILL_NAMES + SAVE_NAMES)
        ADV_INT_MAP = {-1: False, 0: None, 1: True}
        profs = {}
        effects = collections.defaultdict(lambda: 0)

        # calculate profs
        for prof in character.get('proficiencies', []):
            if prof.get('enabled', False) and not prof.get('removed', False):
                profs[prof.get('name')] = prof.get('value') \
                    if prof.get('value') > profs.get(prof.get('name', 'None'), 0) \
                    else profs[prof.get('name')]

        # and effects
        for effect in self.character_data.get('effects', []):
            if effect.get('stat') in NAME_SET \
                    and effect.get('enabled', True) \
                    and not effect.get('removed', False):
                statname = effect.get('stat')
                if effect.get('operation') == 'disadvantage':
                    effects[statname] = max(-1, effects[statname] - 1)
                if effect.get('operation') == 'advantage':
                    effects[statname] = min(1, effects[statname] + 1)

        # assign skills
        skills = {}
        for skill in SKILL_NAMES:
            prof_mult = profs.get(skill, 0)
            base_val = floor(stats.get_mod(SKILL_MAP[skill]) + stats.prof_bonus * prof_mult)
            adv = ADV_INT_MAP.get(effects.get(skill))
            if skill not in STAT_NAMES:
                value = int(self.calculate_stat(skill, base=base_val))
            else:
                value = base_val
            skills[skill] = Skill(
                value,
                prof=prof_mult,
                adv=adv
            )

        # and saves
        saves = {}
        for save in SAVE_NAMES:
            prof_mult = profs.get(save, 0)
            base_val = floor(stats.get_mod(SKILL_MAP[save]) + stats.prof_bonus * prof_mult)
            adv = ADV_INT_MAP.get(effects.get(save))
            saves[save] = Skill(
                int(self.calculate_stat(save, base=base_val)),
                prof=prof_mult,
                adv=adv
            )

        return Skills(skills), Saves(saves)

    def get_resistances(self) -> Resistances:
        if self.character_data is None: raise Exception('You must call get_character() first.')
        out = {'resist': [], 'immune': [], 'vuln': []}
        for dmgType in DAMAGE_TYPES:
            mult = self.calculate_stat(f"{dmgType}Multiplier", 1)
            if mult <= 0:
                out['immune'].append(dmgType)
            elif mult < 1:
                out['resist'].append(dmgType)
            elif mult > 1:
                out['vuln'].append(dmgType)
        return Resistances.from_dict(out)

    def get_ac(self) -> int:
        self.evaluator.names['dexterityArmor'] = self.calculate_stat('dexterityArmor',
                                                                     base=self.get_stats().get_mod('dex'))
        return int(self.calculate_stat('armor'))

    def get_spellbook(self):
        if self.character_data is None: raise Exception('You must call get_character() first.')
        potential_spells = [s for s in self.character_data.get('spells', []) if not s.get('removed', False)]

        slots = {}
        for lvl in range(1, 10):
            num_slots = int(self.calculate_stat(f"level{lvl}SpellSlots"))
            slots[str(lvl)] = num_slots

        spell_lists = {}  # list_id: (ab, dc, scam)
        for sl in self.character_data.get('spellLists', []):
            try:
                ab_calc = sl.get('attackBonus')
                ab = int(self.evaluator.eval(ab_calc))
                dc = int(self.evaluator.eval(sl.get('saveDC')))
                try:
                    scam = self.get_stats().get_mod(next(m for m in STAT_NAMES if m in ab_calc))
                except StopIteration:
                    scam = 0
                spell_lists[sl['_id']] = (ab, dc, scam)
            except:
                pass
        sab, dc, scam = sorted(spell_lists.values(), key=lambda k: k[0], reverse=True)[0] if spell_lists else (0, 0, 0)

        spells = []
        for spell in potential_spells:
            spell_list_id = spell['parent']['id']
            spell_ab, spell_dc, spell_mod = spell_lists.get(spell_list_id, (None, None, None))
            if spell_ab == sab:
                spell_ab = None
            if spell_dc == dc:
                spell_dc = None
            if spell_mod == scam:
                spell_mod = None

            result, strict = search(compendium.spells, spell['name'].strip(), lambda sp: sp.name, strict=True)
            if result and strict:
                spells.append(SpellbookSpell.from_spell(result, sab=spell_ab, dc=spell_dc, mod=spell_mod))
            else:
                spells.append(SpellbookSpell(spell['name'].strip(), sab=spell_ab, dc=spell_dc, mod=spell_mod))

        spellbook = Spellbook(slots, slots, spells, dc, sab, self.get_levels().total_level, scam)

        log.debug(f"Completed parsing spellbook: {spellbook.to_dict()}")

        return spellbook

    def is_live(self):
        dicecloud_client = DicecloudClient.getInstance()
        if dicecloud_client.user_id in self.character_data['characters'][0]['writers'] \
                or dicecloud_client.user_id == self.character_data['characters'][0]['owner']:
            return 'dicecloud'
        return None

    def get_custom_counters(self):
        counters = []

        for res in CLASS_RESOURCES:
            res_value = self.calculate_stat(res)
            if res_value > 0:
                display_type = 'bubble' if res_value < 6 else None
                co = {  # we have to initialize counters this way, which is meh
                    "name": CLASS_RESOURCE_NAMES.get(res, 'Unknown'),
                    "value": res_value, "minv": '0', "maxv": str(res_value),
                    "reset": CLASS_RESOURCE_RESETS.get(res),
                    "display_type": display_type, "live_id": res
                }
                counters.append(co)
        for f in self.character_data.get('features', []):
            if not f.get('enabled'): continue
            if f.get('removed'): continue
            if not ('uses' in f and f['uses']): continue
            reset = None
            desc = f.get('description', '').lower()
            if 'short rest' in desc or 'short or long rest' in desc:
                reset = 'short'
            elif 'long rest' in desc:
                reset = 'long'
            try:
                initial_value = self.evaluator.eval(f['uses'])
            except draconic.DraconicException:
                raise ExternalImportError(f"Invalid max uses on limited use feature {f['name']}: {f['uses']}")
            display_type = 'bubble' if initial_value < 7 else None
            co = {
                "name": f['name'],
                "value": initial_value, "minv": '0', "maxv": str(initial_value),
                "reset": reset,
                "display_type": display_type, "live_id": f['_id']
            }
            counters.append(co)

        return counters

    # helper funcs
    def calculate_stat(self, stat, base=0):
        """Calculates and returns the stat value."""
        if self.character_data is None: raise Exception('You must call get_character() first.')
        if not base and stat in self._cache:
            return self._cache[stat]
        character = self.character_data
        effects = character.get('effects', [])
        add = 0
        mult = 1
        maxV = None
        minV = None
        for effect in effects:
            if effect.get('stat') != stat or not effect.get('enabled', True) or effect.get('removed', False):
                continue
            operation = effect.get('operation', 'base')
            if operation not in ('base', 'add', 'mul', 'min', 'max'):
                continue
            if effect.get('value') is not None:
                value = effect.get('value')
            else:
                calculation = effect.get('calculation', '').replace('{', '').replace('}', '').strip()
                if not calculation: continue
                try:
                    value = self.evaluator.eval(calculation)
                except SyntaxError:
                    continue
                except KeyError:
                    raise
            if not isinstance(value, (int, float)):
                continue
            if operation == 'base' and value > base:
                base = value
            elif operation == 'add':
                add += value
            elif operation == 'mul':
                mult *= value
            elif operation == 'min':
                minV = value if minV is None else value if value < minV else minV
            elif operation == 'max':
                maxV = value if maxV is None else value if value > maxV else maxV
        out = (base + add) * mult
        if minV is not None:
            out = max(out, minV)
        if maxV is not None:
            out = min(out, maxV)
        if not base:
            self._cache[stat] = out
        return out

    def parse_attack(self, atk_dict) -> Attack:
        """Calculates and returns a dict."""
        if self.character_data is None: raise Exception('You must call get_character() first.')

        log.debug(f"Processing attack {atk_dict.get('name')}")

        # setup temporary local vars
        temp_names = {}
        if atk_dict.get('parent', {}).get('collection') == 'Spells':
            spellParentID = atk_dict.get('parent', {}).get('id')
            try:
                spellObj = next(s for s in self.character_data.get('spells', []) if s.get('_id') == spellParentID)
            except StopIteration:
                pass
            else:
                spellListParentID = spellObj.get('parent', {}).get('id')
                try:
                    spellListObj = next(
                        s for s in self.character_data.get('spellLists', []) if s.get('_id') == spellListParentID)
                except StopIteration:
                    pass
                else:
                    try:
                        temp_names['attackBonus'] = int(
                            self.evaluator.eval(spellListObj.get('attackBonus')))
                        temp_names['DC'] = int(self.evaluator.eval(spellListObj.get('saveDC')))
                    except Exception as e:
                        log.debug(f"Exception parsing spellvars: {e}")

        temp_names['rageDamage'] = self.calculate_stat('rageDamage')
        old_names = self.evaluator.names.copy()
        self.evaluator.names.update(temp_names)
        log.debug(f"evaluator tempnames: {temp_names}")

        # attack bonus
        bonus_calc = atk_dict.get('attackBonus', '').replace('{', '').replace('}', '')
        if not bonus_calc:
            bonus = None
        else:
            try:
                bonus = int(self.evaluator.eval(bonus_calc))
            except:
                bonus = None

        # damage
        def damage_sub(match):
            out = match.group(1)
            try:
                log.debug(f"damage_sub: evaluating {out}")
                return str(self.evaluator.eval(out))
            except Exception as ex:
                log.debug(f"exception in damage_sub: {ex}")
                return match.group(0)

        damage_calc = atk_dict.get('damage', '')
        damage = re.sub(r'{(.*?)}', damage_sub, damage_calc)
        damage = damage.replace('{', '').replace('}', '')
        if not damage:
            damage = None
        else:
            damage += ' [{}]'.format(atk_dict.get('damageType'))

        # details
        details = atk_dict.get('details', None)
        if details:
            details = re.sub(r'{([^{}]*)}', damage_sub, details)

        # build attack
        name = atk_dict['name']
        attack = Attack.new(name, bonus, damage, details)

        self.evaluator.names = old_names

        return attack


def func_if(condition, t, f):
    return t if condition else f


def larger(x, y):
    return 1 if x > y else 0


class DicecloudEvaluator(draconic.SimpleInterpreter):
    DEFAULT_FUNCTIONS = {'ceil': ceil, 'floor': floor, 'max': max, 'min': min, 'round': round, 'func_if': func_if,
                         'larger': larger}

    def __init__(self):
        super(DicecloudEvaluator, self).__init__(builtins=self.DEFAULT_FUNCTIONS)

    def eval(self, expr):
        expr = re.sub(r'if\s*\(', 'func_if(', expr)  # 0.5ms avg
        return super().eval(expr.strip())

    def _preflight(self):
        pass

    def _eval_name(self, node):
        lowernames = {k.lower(): v for k, v in self.names.items()}
        try:
            return lowernames[node.id.lower()]
        except KeyError:
            return super()._eval_name(node)

    def _eval_call(self, node):
        if isinstance(node.func, ast.Num):
            func = lambda n: n * self._eval(node.func)
        else:
            func = self._eval(node.func)

        return func(
            *(self._eval(a) for a in node.args),
            **dict(self._eval(k) for k in node.keywords)
        )


if __name__ == '__main__':
    import asyncio
    import json
    from utils.argparser import argparse

    while True:
        url_ = input("Dicecloud sheet ID: ")
        parser = DicecloudParser(url_)
        char = asyncio.get_event_loop().run_until_complete(parser.load_character('', argparse('')))
        print(json.dumps(char.to_dict(), indent=2))
