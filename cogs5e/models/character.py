
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
import random

from discord import InvalidArgument

from cogs5e.models.errors import NoCharacter, ConsumableNotFound, CounterOutOfBounds, NoReset


class Character: # TODO: refactor old commands to use this
    def __init__(self, ctx):
        user_characters = ctx.bot.db.not_json_get(ctx.message.author.id + '.characters', {})
        active_character = ctx.bot.db.not_json_get('active_characters', {}).get(ctx.message.author.id)
        if active_character is None:
            raise NoCharacter()
        character = user_characters[active_character]
        self.character = character
        self.id = active_character

    def get_name(self):
        return self.character.get('stats', {}).get('name', "Unnamed")

    def get_image(self):
        return self.character.get('stats', {}).get('image')

    def get_color(self):
        return self.character.get('settings', {}).get('color') or random.randint(0, 0xffffff)

    def commit(self, ctx):
        """Writes a character object to the database, under the contextual author."""
        user_characters = ctx.bot.db.not_json_get(ctx.message.author.id + '.characters', {})
        user_characters[self.id] = self.character  # commit
        return ctx.bot.db.not_json_set(ctx.message.author.id + '.characters', user_characters)

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
        _max = kwargs.pop('maxValue')
        _min = kwargs.pop('minValue')
        _reset = kwargs.pop('reset')
        try:
            assert _reset in ('short', 'long', 'none') or _reset is None
            assert _max.isnumber() or _max is None
            assert _min.isnumber() or _min is None
        except AssertionError:
            raise InvalidArgument("Invalid reset, max, or min.")
        if _max is not None and _min is not None:
            try:
                assert _max >= _min
            except AssertionError:
                raise InvalidArgument("Max value is less than min value.")
        if _reset and _max is None: raise InvalidArgument("Reset passed but no maximum passed.")
        newCounter = {'value': _max or 0}
        if _max: newCounter['max'] = _max
        if _min: newCounter['min'] = _min
        if _reset and _max: newCounter['reset'] = _reset

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
            assert self.character['consumables']['custom'][name].get('min', -(2 ** 64)) < newValue < \
                   self.character['consumables']['custom'][name].get('max', 2 ** 64 - 1)
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
        for name in self.character.get('consumables', {}).get('custom', {}):
            try:
                self.reset_consumable(name)
            except NoReset:
                pass
            else:
                reset.append(name)
        return reset