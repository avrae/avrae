
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
import logging
import random
import re

from cogs5e.funcs.dice import roll
from cogs5e.models.errors import NoCharacter, ConsumableNotFound, CounterOutOfBounds, NoReset, InvalidArgument

log = logging.getLogger(__name__)

class Character: # TODO: refactor old commands to use this
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

    def get_name(self):
        return self.character.get('stats', {}).get('name', "Unnamed")

    def get_image(self):
        return self.character.get('stats', {}).get('image')

    def get_color(self):
        return self.character.get('settings', {}).get('color') or random.randint(0, 0xffffff)

    def get_max_hp(self):
        return self.character.get('hp', 0)

    def evaluate_cvar(self, varstr):
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

    def set_active(self, ctx):
        """Sets the character as active. Returns self."""
        active_characters = ctx.bot.db.not_json_get('active_characters', {})
        active_characters[ctx.message.author.id] = self.id
        ctx.bot.db.not_json_set('active_characters', active_characters)
        return self

    def initialize_consumables(self):
        try:
            assert self.character.get('consumables') is not None
        except AssertionError:
            self.character['consumables'] = {}
        self._initialize_hp()
        self._initialize_deathsaves()

    def _initialize_hp(self):
        try:
            assert self.character['consumables'].get('hp') is not None
        except AssertionError:
            self.character['consumables']['hp'] = {'value': self.get_max_hp(), 'reset': 'long', 'max': self.get_max_hp(), 'min': 0}

    def _initialize_deathsaves(self):
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
        newCounter = {'value': self.evaluate_cvar(_max) or 0}
        if _max is not None: newCounter['max'] = _max
        if _min is not None: newCounter['min'] = _min
        if _reset and _max is not None: newCounter['reset'] = _reset
        log.debug(f"Creating new counter {newCounter}")

        self.character['consumables']['custom'][name] = newCounter # TODO: integrate with cvar sys

        return self

    def set_consumable(self, name, newValue:int):
        """Sets the value of a character's consumable, returning the Character object.
        Raises CounterOutOfBounds if newValue is out of bounds."""
        self._initialize_custom_counters()
        try:
            assert self.character['consumables']['custom'].get(name) is not None
        except AssertionError:
            raise ConsumableNotFound()
        try:
            assert self.evaluate_cvar(self.character['consumables']['custom'][name].get('min', -(2 ** 64))) <= newValue <= \
                   self.evaluate_cvar(self.character['consumables']['custom'][name].get('max', 2 ** 64 - 1))
        except:
            raise CounterOutOfBounds()
        self.character['consumables']['custom'][name]['value'] = newValue

        return self

    def get_consumable(self, name):
        """Returns the dict object of the consumable, or raises NoConsumable."""
        custom_counters = self.character.get('consumables', {}).get('custom', {})
        counter = custom_counters.get(name)
        if counter is None: raise ConsumableNotFound()
        return counter

    def get_all_consumables(self):
        """Returns the dict object of all custom counters."""
        custom_counters = self.character.get('consumables', {}).get('custom', {})
        return custom_counters

    def delete_consumable(self, name):
        """Deletes a consumable. Returns the Character object."""
        custom_counters = self.character.get('consumables', {}).get('custom', {})
        try: del custom_counters[name]
        except KeyError: raise ConsumableNotFound()
        self.character['consumables']['custom'] = custom_counters
        return self

    def reset_consumable(self, name):
        """Resets a consumable to its maximum value, if applicable.
        Returns the Character object."""
        counter = self.get_consumable(name)
        if counter.get('reset') == 'none': raise NoReset()
        if counter.get('max') is None: raise NoReset()

        self.set_consumable(name, counter.get('max'))

        return self

    def reset_all_consumables(self):
        """Resets all applicable consumables.
        Returns a list of the names of all reset counters."""
        reset = []
        reset.extend(self.on_hp()) # TODO
        reset.extend(self.short_rest()) # TODO
        reset.extend(self.long_rest()) # TODO
        for name, value in self.character.get('consumables', {}).get('custom', {}).items():
            if value.get('reset') is None:
                try:
                    self.reset_consumable(name)
                except NoReset:
                    pass
                else:
                    reset.append(name)
        return reset