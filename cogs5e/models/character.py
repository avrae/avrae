"""
{'type': 'dicecloud',
 'version': 6, #v6: added stat cvars
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
 'overrides': {},
 'cvars': {}}
"""
import ast
import copy
import logging
import random
import re
from math import *

import simpleeval

from cogs5e.funcs.dice import roll
from cogs5e.models.dicecloudClient import dicecloud_client
from cogs5e.models.errors import NoCharacter, ConsumableNotFound, CounterOutOfBounds, NoReset, InvalidArgument, \
    OutdatedSheet, EvaluationError, InvalidSpellLevel
from cogs5e.sheets.dicecloud import CLASS_RESOURCES
from utils.functions import get_selection

log = logging.getLogger(__name__)


class Character:
    def __init__(self, _dict, _id):
        self.character = _dict
        self.id = _id
        self.live = self.character.get('live') and self.character.get('type') == 'dicecloud'

    @classmethod
    def from_ctx(cls, ctx):
        user_characters = ctx.bot.db.not_json_get(ctx.message.author.id + '.characters', {})
        active_character = ctx.bot.db.not_json_get('active_characters', {}).get(ctx.message.author.id)
        if active_character is None:
            raise NoCharacter()
        character = user_characters[active_character]
        return cls(character, active_character)

    @classmethod
    def from_bot_and_ids(cls, bot, author_id, character_id):
        user_characters = bot.db.not_json_get(author_id + '.characters', {})
        character = user_characters.get(character_id)
        if character is None: raise NoCharacter()
        return cls(character, character_id)

    def get_name(self):
        return self.character.get('stats', {}).get('name', "Unnamed")

    def get_image(self):
        return self.character.get('stats', {}).get('image', '')

    def get_color(self):
        return self.character.get('settings', {}).get('color') or random.randint(0, 0xffffff)

    def get_max_hp(self):
        return self.character.get('hp', 0)

    def get_level(self):
        """@:returns int - the character's total level."""
        return self.character.get('levels', {}).get('level', 0)

    def get_prof_bonus(self):
        """@:returns int - the character's proficiency bonus."""
        return self.character.get('stats', {}).get('proficiencyBonus', 0)

    def get_saves(self):
        """@:returns dict - the character's saves and modifiers."""
        return self.character.get('saves', {})

    def get_skills(self):
        """@:returns dict - the character's skills and modifiers."""
        return self.character.get('skills', {})

    def get_skill_effects(self):
        """@:returns dict - the character's skill effects and modifiers."""
        return self.character.get('skill_effects', {})

    def get_attacks(self):
        """@:returns list - the character's list of attack dicts."""
        return self.character.get('attacks', [])

    def get_max_spellslots(self, level: int):
        """@:returns the maximum number of spellslots of level level a character has.
        @:returns 0 if none.
        @:raises OutdatedSheet if character does not have spellbook."""
        try:
            assert 'spellbook' in self.character
        except AssertionError:
            raise OutdatedSheet()

        return int(self.character.get('spellbook', {}).get('spellslots', {}).get(str(level), 0))

    def get_spell_list(self):
        """@:returns list - a list of the names of all spells the character can cast.
        @:raises OutdatedSheet if character does not have spellbook."""
        try:
            assert 'spellbook' in self.character
        except AssertionError:
            raise OutdatedSheet()

        return self.character.get('spellbook', {}).get('spells', [])

    def get_save_dc(self):
        """@:returns int - the character's spell save DC.
        @:raises OutdatedSheet if character does not have spellbook."""
        try:
            assert 'spellbook' in self.character
        except AssertionError:
            raise OutdatedSheet()

        return self.character.get('spellbook', {}).get('dc', 0)

    def get_spell_ab(self):
        """@:returns int - the character's spell attack bonus.
        @:raises OutdatedSheet if character does not have spellbook."""
        try:
            assert 'spellbook' in self.character
        except AssertionError:
            raise OutdatedSheet()

        return self.character.get('spellbook', {}).get('attackBonus', 0)

    def get_setting(self, setting, default=None):
        """Gets the value of a csetting.
        @:returns the csetting's value, or default."""
        setting = self.character.get('settings', {}).get(setting)
        if setting is None: return default
        return setting

    def set_setting(self, setting, value):
        """Sets the value of a csetting.
                @:returns self"""
        if self.character.get('settings') is None:
            self.character['settings'] = {}
        self.character['settings'][setting] = value
        return self

    def parse_cvars(self, cstr, ctx=None):
        """Parses cvars.
        :param ctx: The Context the cvar is parsed in.
        :param cstr: The string to parse.
        :returns string - the parsed string."""
        character = self.character
        ops = r"([-+*/().<>=])"
        cvars = character.get('cvars', {})
        stat_vars = character.get('stat_cvars', {})
        stat_vars['color'] = hex(self.get_color())[2:]
        user_vars = ctx.bot.db.jhget("user_vars", ctx.message.author.id, {}) if ctx else {}

        _vars = user_vars
        _vars.update(cvars)
        global_vars = None  # we'll load them if we need them

        changed = False

        # define our weird functions here
        def get_cc(name):
            return self.get_consumable_value(name)

        def get_cc_max(name):
            return self.evaluate_cvar(self.get_consumable(name).get('max', str(2 ** 32 - 1)))

        def get_cc_min(name):
            return self.evaluate_cvar(self.get_consumable(name).get('min', str(-(2 ** 32))))

        def set_cc(name, value: int, strict=False):
            self.set_consumable(name, value, strict)
            nonlocal changed
            changed = True
            return ''

        def mod_cc(name, val: int, strict=False):
            return set_cc(name, get_cc(name) + val, strict)

        def get_slots(level: int):
            return self.get_remaining_slots(level)

        def get_slots_max(level: int):
            return self.get_max_spellslots(level)

        def set_slots(level: int, value: int):
            self.set_remaining_slots(level, value)
            nonlocal changed
            changed = True
            return ''

        def use_slot(level: int):
            self.use_slot(level)
            nonlocal changed
            changed = True
            return ''

        def get_hp():
            return self.get_current_hp()

        def set_hp(val: int):
            self.set_hp(val)
            nonlocal changed
            changed = True
            return ''

        def mod_hp(val: int, overflow: bool = True):
            if not overflow:
                return set_hp(min(self.get_current_hp() + val, self.get_max_hp()))
            else:
                return set_hp(self.get_current_hp() + val)

        def set_cvar(name, val: str):
            self.set_cvar(name, val)
            _names[name] = str(val)
            nonlocal changed
            changed = True
            return ''

        def get_gvar(name):
            nonlocal global_vars
            if global_vars is None:  # load only if needed
                global_vars = ctx.bot.db.jget("global_vars", {})
            return global_vars.get(name, {}).get('value')

        _funcs = simpleeval.DEFAULT_FUNCTIONS.copy()
        _funcs['roll'] = simple_roll
        _funcs['vroll'] = verbose_roll
        _funcs.update(floor=floor, ceil=ceil, round=round, len=len, max=max, min=min,
                      get_cc=get_cc, set_cc=set_cc, get_cc_max=get_cc_max, get_cc_min=get_cc_min, mod_cc=mod_cc,
                      get_slots=get_slots, get_slots_max=get_slots_max, set_slots=set_slots, use_slot=use_slot,
                      get_hp=get_hp, set_hp=set_hp, mod_hp=mod_hp,
                      set_cvar=set_cvar, get_gvar=get_gvar)
        _ops = simpleeval.DEFAULT_OPERATORS.copy()
        _ops.pop(ast.Pow)  # no exponents pls
        _names = copy.copy(_vars)
        _names.update(stat_vars)
        _names.update({"True": True, "False": False, "currentHp": self.get_current_hp()})
        evaluator = simpleeval.EvalWithCompoundTypes(functions=_funcs, operators=_ops, names=_names)

        def set_value(name, value):
            evaluator.names[name] = value
            return ''

        evaluator.functions['set'] = set_value

        def cvarrepl(match):
            return f"{match.group(1)}{_vars.get(match.group(2), match.group(2))}"

        for var in re.finditer(r'{{([^{}]+)}}', cstr):
            raw = var.group(0)
            varstr = var.group(1)

            for cvar, value in _vars.items():
                varstr = re.sub(r'(^|\s)(' + cvar + r')(?=\s|$)', cvarrepl, varstr)

            try:
                cstr = cstr.replace(raw, str(evaluator.eval(varstr)), 1)
            except Exception as e:
                raise EvaluationError(e)

        for var in re.finditer(r'{([^{}]+)}', cstr):
            raw = var.group(0)
            varstr = var.group(1)
            out = ""
            tempout = ''
            for substr in re.split(ops, varstr):
                temp = substr.strip()
                # if temp.startswith('/'):
                #     _last = character
                #     for path in out.split('/'):
                #         if path:
                #             try:
                #                 _last = _last.get(path, {})
                #             except AttributeError:
                #                 break
                #     temp = str(_last)
                tempout += str(_vars.get(temp, temp)) + " "
            for substr in re.split(ops, tempout):
                temp = substr.strip()
                out += str(stat_vars.get(temp, temp)) + " "
            cstr = cstr.replace(raw, str(roll(out).total), 1)
        for var in re.finditer(r'<([^<>]+)>', cstr):
            raw = var.group(0)
            if re.match(r'<([@#]|:.+:)[&!]{0,2}\d+>', raw): continue  # ignore mentions, channels, emotes
            out = var.group(1)
            if out.startswith('/'):
                _last = character
                for path in out.split('/'):
                    if path:
                        try:
                            _last = _last.get(path, {})
                        except AttributeError:
                            break
                out = str(_last)
            out = str(_vars.get(out, out))
            out = str(stat_vars.get(out, out))
            cstr = cstr.replace(raw, out, 1)
        if changed and ctx:
            self.commit(ctx)
        return cstr

    def evaluate_cvar(self, varstr):
        """Evaluates a cvar.
        @:param varstr - the name of the cvar to parse.
        @:returns int - the value of the cvar, or 0 if evaluation failed."""
        ops = r"([-+*/().<>=])"
        varstr = str(varstr).strip('<>{}')

        cvars = self.character.get('cvars', {})
        stat_vars = self.character.get('stat_cvars', {})
        out = ""
        tempout = ''
        for substr in re.split(ops, varstr):
            temp = substr.strip()
            if temp.startswith('/'):
                _last = self.character
                for path in out.split('/'):
                    if path:
                        try:
                            _last = _last.get(path, {})
                        except AttributeError:
                            break
                temp = str(_last)
            tempout += str(cvars.get(temp, temp)) + " "
        for substr in re.split(ops, tempout):
            temp = substr.strip()
            out += str(stat_vars.get(temp, temp)) + " "
        return roll(out).total

    def get_cvar(self, name):
        return self.character.get('cvars', {}).get(name)

    def set_cvar(self, name, val: str):
        """Sets a cvar to a string value."""
        if any(c in name for c in '/()[]\\.^$*+?|{}'):
            raise InvalidArgument("Cvar contains invalid character.")
        self.character['cvars'] = self.character.get('cvars', {})  # set value
        self.character['cvars'][name] = str(val)
        return self

    def get_cvars(self):
        return self.character.get('cvars', {})

    def get_stat_vars(self):
        return self.character.get('stat_cvars', {})

    def commit(self, ctx):
        """Writes a character object to the database, under the contextual author. Returns self."""
        user_characters = ctx.bot.db.not_json_get(ctx.message.author.id + '.characters', {})
        user_characters[self.id] = self.character  # commit
        ctx.bot.db.not_json_set(ctx.message.author.id + '.characters', user_characters)
        return self

    def manual_commit(self, bot, author_id):
        user_characters = bot.db.not_json_get(author_id + '.characters', {})
        user_characters[self.id] = self.character  # commit
        bot.db.not_json_set(author_id + '.characters', user_characters)
        return self

    def set_active(self, ctx):
        """Sets the character as active. Returns self."""
        active_characters = ctx.bot.db.not_json_get('active_characters', {})
        active_characters[ctx.message.author.id] = self.id
        ctx.bot.db.not_json_set('active_characters', active_characters)
        return self

    def initialize_consumables(self):
        """Initializes a character's consumable counters. Returns self."""
        try:
            assert self.character.get('consumables') is not None
        except AssertionError:
            self.character['consumables'] = {}
        self._initialize_hp()
        self._initialize_deathsaves()
        self._initialize_spellslots()
        return self

    def _initialize_hp(self):
        try:
            assert self.character.get('consumables') is not None
        except AssertionError:
            self.character['consumables'] = {}
        try:
            assert self.character['consumables'].get('hp') is not None
        except AssertionError:
            self.character['consumables']['hp'] = {'value': self.get_max_hp(), 'reset': 'long',
                                                   'max': self.get_max_hp(), 'min': 0}

    def get_hp(self):
        """Returns the Counter dictionary."""
        self._initialize_hp()
        return self.character['consumables']['hp']

    def get_current_hp(self):
        """Returns the integer value of the remaining HP."""
        return self.get_hp()['value']

    def set_hp(self, newValue):
        """Sets the character's hit points. Returns the Character object."""
        self._initialize_hp()
        hp = self.get_hp()
        self.character['consumables']['hp']['value'] = max(hp['min'], int(newValue))  # bounding

        self.on_hp()

        if self.live:
            self._sync_hp()

        return self

    def _sync_hp(self):
        def update_callback(error, data):
            if error:
                log.warning(error)
                if error.get('error') == 403:  # character no longer shared
                    self.character['live'] = False
                    self.live = False
            else:
                log.debug(data)

        dicecloud_client.update('characters', {'_id': self.id[10:]},
                                {'$set': {"hitPoints.adjustment": self.get_current_hp() - self.get_max_hp()}},
                                callback=update_callback)

    def modify_hp(self, value):
        """Modifies the character's hit points. Returns the Character object."""
        self.set_hp(self.get_current_hp() + value)
        return self

    def reset_hp(self):
        """Resets the character's HP to max. Returns the Character object."""
        self.set_hp(self.get_max_hp())
        return self

    def _initialize_deathsaves(self):
        try:
            assert self.character.get('consumables') is not None
        except AssertionError:
            self.character['consumables'] = {}
        try:
            assert self.character['consumables'].get('deathsaves') is not None
        except AssertionError:
            self.character['consumables']['deathsaves'] = {'fail': {'value': 0, 'reset': 'hp', 'max': 3, 'min': 0},
                                                           'success': {'value': 0, 'reset': 'hp', 'max': 3, 'min': 0}}

    def get_deathsaves(self):
        self._initialize_deathsaves()
        return self.character['consumables']['deathsaves']

    def get_ds_str(self):
        """
        :rtype: str
        :return: A bubble representation of a character's death saves.
        """
        ds = self.get_deathsaves()
        successes = '\u25c9' * ds['success']['value'] + '\u3007' * (3 - ds['success']['value'])
        fails = '\u25c9' * ds['fail']['value'] + '\u3007' * (3 - ds['fail']['value'])
        return f"S {successes} | {fails} F"

    def add_successful_ds(self):
        """Adds a successful death save to the character.
        Returns True if the character is stable."""
        self._initialize_deathsaves()
        self.character['consumables']['deathsaves']['success']['value'] = min(3, self.character['consumables'][
            'deathsaves']['success']['value'] + 1)
        return self.character['consumables']['deathsaves']['success']['value'] == 3

    def add_failed_ds(self):
        """Adds a failed death save to the character.
        Returns True if the character is dead."""
        self._initialize_deathsaves()
        self.character['consumables']['deathsaves']['fail']['value'] = min(3, self.character['consumables'][
            'deathsaves']['fail']['value'] + 1)
        return self.character['consumables']['deathsaves']['fail']['value'] == 3

    def reset_death_saves(self):
        """Resets successful and failed death saves to 0. Returns the Character object."""
        self._initialize_deathsaves()
        self.character['consumables']['deathsaves']['success']['value'] = 0
        self.character['consumables']['deathsaves']['fail']['value'] = 0
        return self

    def _initialize_spellslots(self):
        """Sets up a character's spellslot consumables.
        @:raises OutdatedSheet if sheet does not have spellbook."""
        try:
            assert self.character.get('consumables') is not None
        except AssertionError:
            self.character['consumables'] = {}
        try:
            assert self.character['consumables'].get('spellslots') is not None
        except AssertionError:
            ss = {}
            for lvl in range(1, 10):
                m = self.get_max_spellslots(lvl)
                ss[str(lvl)] = {'value': m, 'reset': 'long', 'max': m, 'min': 0}
            self.character['consumables']['spellslots'] = ss

    def get_spellslots(self):
        """Returns the Counter dictionary."""
        self._initialize_spellslots()
        return self.character['consumables']['spellslots']

    def get_remaining_slots(self, level: int):
        """@:param level - The spell level.
        @:returns the integer value representing the number of spellslots remaining."""
        try:
            assert 0 <= level < 10
        except AssertionError:
            raise InvalidSpellLevel()
        if level == 0: return 1  # cantrips
        return int(self.get_spellslots()[str(level)]['value'])

    def get_remaining_slots_str(self, level: int = None):
        """@:param level: The level of spell slot to return.
        @:returns A string representing the character's remaining spell slots."""
        out = ''
        if level:
            assert 0 < level < 10
            _max = self.get_max_spellslots(level)
            remaining = self.get_remaining_slots(level)
            numEmpty = _max - remaining
            filled = '\u25c9' * remaining
            empty = '\u3007' * numEmpty
            out += f"`{level}` {filled}{empty}\n"
        else:
            for level in range(1, 10):
                _max = self.get_max_spellslots(level)
                remaining = self.get_remaining_slots(level)
                if _max:
                    numEmpty = _max - remaining
                    filled = '\u25c9' * remaining
                    empty = '\u3007' * numEmpty
                    out += f"`{level}` {filled}{empty}\n"
        if out == '':
            out = "No spell slots."
        return out

    def set_remaining_slots(self, level: int, value: int, sync: bool = True):
        """Sets the character's remaining spell slots of level level.
        @:param level - The spell level.
        @:param value - The number of remaining spell slots.
        @:returns self"""
        try:
            assert 0 < level < 10
        except AssertionError:
            raise InvalidSpellLevel()
        try:
            assert 0 <= value <= self.get_max_spellslots(level)
        except AssertionError:
            raise CounterOutOfBounds()

        self._initialize_spellslots()
        self.character['consumables']['spellslots'][str(level)]['value'] = int(value)

        if self.live and sync:
            self._sync_slots()

        return self

    def _sync_slots(self):
        def update_callback(error, data):
            if error:
                log.warning(error)
                if error.get('error') == 403:  # character no longer shared
                    self.character['live'] = False
                    self.live = False
            else:
                log.debug(data)

        spell_dict = {}
        for lvl in range(1, 10):
            spell_dict[f'level{lvl}SpellSlots.adjustment'] = self.get_remaining_slots(lvl) - self.get_max_spellslots(
                lvl)
        dicecloud_client.update('characters', {'_id': self.id[10:]},
                                {'$set': spell_dict},
                                callback=update_callback)

    def use_slot(self, level: int):
        """Uses one spell slot of level level.
        @:returns self
        @:raises CounterOutOfBounds if there are no remaining slots of the requested level."""
        try:
            assert 0 <= level < 10
        except AssertionError:
            raise InvalidSpellLevel()
        if level == 0: return self
        ss = self.get_spellslots()
        val = ss[str(level)]['value'] - 1
        if val < ss[str(level)]['min']: raise CounterOutOfBounds()
        self.set_remaining_slots(level, val)
        return self

    def reset_spellslots(self):
        """Resets all spellslots to their max value.
        @:returns self"""
        for level in range(1, 10):
            self.set_remaining_slots(level, self.get_max_spellslots(level), False)
        self._sync_slots()
        return self

    def _initialize_spellbook(self):
        """Sets up a character's spellbook override.
        @:raises OutdatedSheet if sheet does not have spellbook."""
        try:
            assert self.character.get('spellbook') is not None
        except AssertionError:
            raise OutdatedSheet()

    def _initialize_spell_overrides(self):
        """Sets up a character's spell overrides."""
        try:
            assert self.character.get('overrides') is not None
        except AssertionError:
            self.character['overrides'] = {}
        if not 'spells' in self.character['overrides']:
            self.character['overrides']['spells'] = []

    def add_known_spell(self, spell):
        """Adds a spell to the character's known spell list.
        :param spell (dict) - the Spell dictionary.
        :returns self"""
        self._initialize_spellbook()
        spells = set(self.character['spellbook']['spells'])
        spells.add(spell['name'])
        self.character['spellbook']['spells'] = list(spells)

        if not self.live:
            self._initialize_spell_overrides()
            overrides = set(self.character['overrides']['spells'])
            overrides.add(spell['name'])
            self.character['overrides']['spells'] = list(overrides)
        return self

    def remove_known_spell(self, spell_name):
        """
        Removes a spell from the character's spellbook override.
        :param spell_name: (str) The name of the spell to remove.
        :return: (str) The name of the removed spell.
        """
        assert not self.live
        self._initialize_spellbook()
        self._initialize_spell_overrides()
        overrides = set(self.character['overrides'].get('spells', []))
        spell_name = next((s for s in overrides if spell_name.lower() == s.lower()), None)
        if spell_name:
            overrides.remove(spell_name)
            self.character['overrides']['spells'] = list(overrides)
            spells = set(self.character['spellbook']['spells'])
            spells.remove(spell_name)
            self.character['spellbook']['spells'] = list(spells)
        return spell_name

    def _initialize_custom_counters(self):
        try:
            assert self.character.get('consumables') is not None
        except AssertionError:
            self.character['consumables'] = {}
        try:
            assert self.character['consumables'].get('custom') is not None
        except AssertionError:
            self.character['consumables']['custom'] = {}

    def create_consumable(self, name, **kwargs):
        """Creates a custom consumable, returning the character object."""
        self._initialize_custom_counters()
        _max = kwargs.get('maxValue')
        _min = kwargs.get('minValue')
        _reset = kwargs.get('reset')
        _type = kwargs.get('displayType')
        _live_id = kwargs.get('live')
        try:
            assert _reset in ('short', 'long', 'none') or _reset is None
        except AssertionError:
            raise InvalidArgument("Invalid reset.")
        if _max is not None and _min is not None:
            maxV = self.evaluate_cvar(_max)
            try:
                assert maxV >= self.evaluate_cvar(_min)
            except AssertionError:
                raise InvalidArgument("Max value is less than min value.")
            if maxV == 0:
                raise InvalidArgument("Max value cannot be 0.")
        if _reset and _max is None: raise InvalidArgument("Reset passed but no maximum passed.")
        if _type == 'bubble' and (_max is None or _min is None): raise InvalidArgument(
            "Bubble display requires a max and min value.")
        newCounter = {'value': self.evaluate_cvar(_max) or 0}
        if _max is not None: newCounter['max'] = _max
        if _min is not None: newCounter['min'] = _min
        if _reset and _max is not None: newCounter['reset'] = _reset
        newCounter['type'] = _type
        newCounter['live'] = _live_id
        log.debug(f"Creating new counter {newCounter}")

        self.character['consumables']['custom'][name] = newCounter

        return self

    def set_consumable(self, name, newValue: int, strict=False):
        """Sets the value of a character's consumable, returning the Character object.
        Raises CounterOutOfBounds if newValue is out of bounds."""
        self._initialize_custom_counters()
        try:
            assert self.character['consumables']['custom'].get(name) is not None
        except AssertionError:
            raise ConsumableNotFound()
        try:
            _min = self.evaluate_cvar(self.character['consumables']['custom'][name].get('min', str(-(2 ** 32))))
            _max = self.evaluate_cvar(self.character['consumables']['custom'][name].get('max', str(2 ** 32 - 1)))
            if strict:
                assert _min <= int(newValue) <= _max
            else:
                newValue = min(max(_min, int(newValue)), _max)

        except AssertionError:
            raise CounterOutOfBounds()
        self.character['consumables']['custom'][name]['value'] = int(newValue)

        if self.character['consumables']['custom'][name].get('live') and self.live:
            used = _max - newValue
            self._sync_consumable(self.character['consumables']['custom'][name], used)

        return self

    def _sync_consumable(self, counter, used):
        """Syncs a consumable's uses with dicecloud."""

        def update_callback(error, data):
            if error:
                log.warning(error)
                if error.get('error') == 403:  # character no longer shared
                    self.character['live'] = False  # this'll be committed since we're modifying something to sync
                    self.live = False
            else:
                log.debug(data)

        if counter['live'] in CLASS_RESOURCES:
            dicecloud_client.update('characters', {'_id': self.id[10:]},
                                    {'$set': {f"{counter['live']}.adjustment": -used}},
                                    callback=update_callback)
        else:
            dicecloud_client.update('features', {'_id': counter['live']},
                                    {'$set': {"used": used}},
                                    callback=update_callback)

    def get_consumable(self, name):
        """Returns the dict object of the consumable, or raises NoConsumable."""
        custom_counters = self.character.get('consumables', {}).get('custom', {})
        counter = custom_counters.get(name)
        if counter is None: raise ConsumableNotFound()
        return counter

    def get_consumable_value(self, name):
        """@:returns int - the integer value of the consumable."""
        return int(self.get_consumable(name).get('value', 0))

    async def select_consumable(self, ctx, name):
        """@:param name (str): The name of the consumable to search for.
        @:returns dict - the consumable.
        @:raises ConsumableNotFound if the consumable does not exist."""
        custom_counters = self.character.get('consumables', {}).get('custom', {})
        choices = [(cname, counter) for cname, counter in custom_counters.items() if cname.lower() == name.lower()]
        if not choices:
            choices = [(cname, counter) for cname, counter in custom_counters.items() if name.lower() in cname.lower()]
        if not choices:
            raise ConsumableNotFound()
        else:
            return await get_selection(ctx, choices, return_name=True)

    def get_all_consumables(self):
        """Returns the dict object of all custom counters."""
        custom_counters = self.character.get('consumables', {}).get('custom', {})
        return custom_counters

    def delete_consumable(self, name):
        """Deletes a consumable. Returns the Character object."""
        custom_counters = self.character.get('consumables', {}).get('custom', {})
        try:
            del custom_counters[name]
        except KeyError:
            raise ConsumableNotFound()
        self.character['consumables']['custom'] = custom_counters
        return self

    def reset_consumable(self, name):
        """Resets a consumable to its maximum value, if applicable.
        Returns the Character object."""
        counter = self.get_consumable(name)
        if counter.get('reset') == 'none': raise NoReset()
        if counter.get('max') is None: raise NoReset()

        self.set_consumable(name, self.evaluate_cvar(counter.get('max')))

        return self

    def _reset_custom(self, scope):
        """Resets custom counters with given scope."""
        reset = []
        for name, value in self.character.get('consumables', {}).get('custom', {}).items():
            if value.get('reset') == scope:
                try:
                    self.reset_consumable(name)
                except NoReset:
                    pass
                else:
                    reset.append(name)
        return reset

    def on_hp(self):
        """Resets all applicable consumables.
        Returns a list of the names of all reset counters."""
        reset = []
        reset.extend(self._reset_custom('hp'))
        if self.get_current_hp() > 0:  # lel
            self.reset_death_saves()
            reset.append("Death Saves")
        return reset

    def short_rest(self):
        """Resets all applicable consumables.
        Returns a list of the names of all reset counters."""
        reset = []
        reset.extend(self.on_hp())
        reset.extend(self._reset_custom('short'))
        if self.get_setting('srslots', False):
            self.reset_spellslots()
            reset.append("Spell Slots")
        return reset

    def long_rest(self):
        """Resets all applicable consumables.
        Returns a list of the names of all reset counters."""
        reset = []
        reset.extend(self.on_hp())
        reset.extend(self.short_rest())
        reset.extend(self._reset_custom('long'))
        self.reset_hp()
        reset.append("HP")
        if not self.get_setting('srslots', False):
            self.reset_spellslots()
            reset.append("Spell Slots")
        return reset

    def reset_all_consumables(self):
        """Resets all applicable consumables.
        Returns a list of the names of all reset counters."""
        reset = []
        reset.extend(self.on_hp())
        reset.extend(self.short_rest())
        reset.extend(self.long_rest())
        reset.extend(self._reset_custom(None))
        return reset


# helper methods
def simple_roll(rollStr):
    return roll(rollStr).total


class SimpleRollResult:
    def __init__(self, dice, total, full):
        self.dice = dice.strip()
        self.total = total
        self.full = full.strip()

    def __str__(self):
        return self.full


def verbose_roll(rollStr):
    rolled = roll(rollStr, inline=True)
    return SimpleRollResult(rolled.rolled, rolled.total, rolled.skeleton)
