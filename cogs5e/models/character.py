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
from cogs5e.models.errors import NoCharacter, ConsumableNotFound, CounterOutOfBounds, NoReset, InvalidArgument, \
    OutdatedSheet, EvaluationError, InvalidSpellLevel
from utils.functions import get_selection

log = logging.getLogger(__name__)


class Character:  # TODO: refactor old commands to use this

    def __init__(self, _dict, _id):
        self.character = _dict
        self.id = _id

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

        return self.character.get('spellbook', {}).get('spellslots', {}).get(str(level), 0)

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
        :param cstr - The string to parse.
        :returns string - the parsed string."""
        character = self.character
        ops = r"([-+*/().<>=])"
        cvars = character.get('cvars', {})
        stat_vars = character.get('stat_cvars', {})

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

        def set_hp(val: int):
            self.set_hp(val)
            nonlocal changed
            changed = True
            return ''

        def mod_hp(val: int):
            return set_hp(self.get_current_hp() + val)

        _funcs = simpleeval.DEFAULT_FUNCTIONS.copy()
        _funcs['roll'] = simple_roll
        _funcs.update(floor=floor, ceil=ceil, round=round, len=len, max=max, min=min,
                      get_cc=get_cc, set_cc=set_cc, get_slots=get_slots, set_slots=set_slots, use_slot=use_slot,
                      set_hp=set_hp)
        _ops = simpleeval.DEFAULT_OPERATORS.copy()
        _ops.pop(ast.Pow)  # no exponents pls
        _names = copy.copy(cvars)
        _names.update(stat_vars)
        _names.update({"True": True, "False": False, "currentHp": self.get_current_hp()})
        evaluator = simpleeval.SimpleEval(functions=_funcs, operators=_ops, names=_names)

        def set_value(name, value):
            evaluator.names[name] = value
            return ''

        evaluator.functions['set'] = set_value

        def cvarrepl(match):
            return f"{match.group(1)}{cvars.get(match.group(2), match.group(2))}"

        for var in re.finditer(r'{{([^{}]+)}}', cstr):
            raw = var.group(0)
            varstr = var.group(1)

            for cvar, value in cvars.items():
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
                tempout += str(cvars.get(temp, temp)) + " "
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
            out = str(cvars.get(out, out))
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

        return self

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

    def add_successful_ds(self):
        """Adds a successful death save to the character.
        Returns True if the character is stable."""
        self._initialize_deathsaves()
        self.character['consumables']['deathsaves']['success']['value'] += 1
        return self.character['consumables']['deathsaves']['success']['value'] == 3

    def add_failed_ds(self):
        """Adds a failed death save to the character.
        Returns True if the character is dead."""
        self._initialize_deathsaves()
        self.character['consumables']['deathsaves']['fail']['value'] += 1
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
        return self.get_spellslots()[str(level)]['value']

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

    def set_remaining_slots(self, level: int, value: int):
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
        self.character['consumables']['spellslots'][str(level)]['value'] = value

        return self

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
            self.set_remaining_slots(level, self.get_max_spellslots(level))

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
        try:
            assert _reset in ('short', 'long', 'none') or _reset is None
        except AssertionError:
            raise InvalidArgument("Invalid reset.")
        if _max is not None and _min is not None:
            try:
                assert self.evaluate_cvar(_max) >= self.evaluate_cvar(_min)
            except AssertionError:
                raise InvalidArgument("Max value is less than min value.")
        if _reset and _max is None: raise InvalidArgument("Reset passed but no maximum passed.")
        if _type == 'bubble' and (_max is None or _min is None): raise InvalidArgument(
            "Bubble display requires a max and min value.")
        newCounter = {'value': self.evaluate_cvar(_max) or 0}
        if _max is not None: newCounter['max'] = _max
        if _min is not None: newCounter['min'] = _min
        if _reset and _max is not None: newCounter['reset'] = _reset
        newCounter['type'] = _type
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

        return self

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
