import cogs5e.models.sheet.player as player_api
from aliasing import helpers
from aliasing.api.statblock import AliasStatBlock
from cogs5e.models.errors import ConsumableException


class AliasCharacter(AliasStatBlock):
    def __init__(self, character, interpreter=None):
        """
        :type character: cogs5e.models.character.Character
        :type interpreter: draconic.DraconicInterpreter
        """
        super().__init__(character)
        self._character = character
        self._interpreter = interpreter
        # memoized attrs
        self._consumables = None
        self._death_saves = None

    # helpers
    def _get_consumable(self, name):
        consumable = next((con for con in self._character.consumables if con.name == name), None)
        if consumable is None:
            raise ConsumableException(f"There is no counter named {name}.")
        return consumable

    # methods
    # --- death saves ---
    @property
    def death_saves(self):
        if self._death_saves is None:
            self._death_saves = AliasDeathSaves(self._character.death_saves)
        return self._death_saves

    # --- ccs ---
    @property
    def consumables(self):
        """
        Returns a list of custom counters on the character.

        :rtype: list[AliasCustomCounter]
        """
        if self._consumables is None:
            self._consumables = [AliasCustomCounter(cc) for cc in self._character.consumables]
        return self._consumables

    def get_cc(self, name):
        """
        Gets the value of a custom counter.

        :param str name: The name of the custom counter to get.
        :returns: The current value of the counter.
        :rtype: int
        :raises: :exc:`ConsumableException` if the counter does not exist.
        """
        return self._get_consumable(name).value

    def get_cc_max(self, name):
        """
        Gets the maximum value of a custom counter.

        :param str name: The name of the custom counter maximum to get.
        :returns: The maximum value of the counter. If a counter has no maximum, it will return INT_MAX (2^31-1).
        :rtype: int
        :raises: :exc:`ConsumableException` if the counter does not exist.
        """
        return self._get_consumable(name).get_max()

    def get_cc_min(self, name):
        """
        Gets the minimum value of a custom counter.

        :param str name: The name of the custom counter minimum to get.
        :returns: The minimum value of the counter. If a counter has no minimum, it will return INT_MIN (-2^31).
        :rtype: int
        :raises: :exc:`ConsumableException` if the counter does not exist.
        """
        return self._get_consumable(name).get_min()

    def set_cc(self, name, value: int, strict=False):
        """
        Sets the value of a custom counter.

        :param str name: The name of the custom counter to set.
        :param int value: The value to set the counter to.
        :param bool strict: If ``True``, will raise a :exc:`CounterOutOfBounds` if the new value is out of bounds, otherwise silently clips to bounds.
        :raises: :exc:`ConsumableException` if the counter does not exist.
        :returns: The cc's new value.
        :rtype: int
        """
        return self._get_consumable(name).set(int(value), strict)

    def mod_cc(self, name, val: int, strict=False):
        """
        Modifies the value of a custom counter. Equivalent to ``set_cc(name, get_cc(name) + value, strict)``.
        """
        return self.set_cc(name, self.get_cc(name) + val, strict)

    def delete_cc(self, name):
        """
        Deletes a custom counter.

        :param str name: The name of the custom counter to delete.
        :raises: :exc:`ConsumableException` if the counter does not exist.
        """
        to_delete = self._get_consumable(name)
        self._character.consumables.remove(to_delete)

    def create_cc_nx(self, name: str, minVal: str = None, maxVal: str = None, reset: str = None,
                     dispType: str = None):
        """
        Creates a custom counter if one with the given name does not already exist.
        Equivalent to:

        >>> if not cc_exists(name):
        >>>     create_cc(name, minVal, maxVal, reset, dispType)
        """
        if not self.cc_exists(name):
            new_consumable = player_api.CustomCounter.new(self._character, name, minVal, maxVal, reset, dispType)
            self._character.consumables.append(new_consumable)
            self._consumables = None  # reset cache
            return AliasCustomCounter(new_consumable)

    def create_cc(self, name: str, *args, **kwargs):
        """
        Creates a custom counter. If a counter with the same name already exists, it will replace it.

        :param str name: The name of the counter to create.
        :param str minVal: The minimum value of the counter. Supports :ref:`cvar-table` parsing.
        :param str maxVal: The maximum value of the counter. Supports :ref:`cvar-table` parsing.
        :param str reset: One of ``'short'``, ``'long'``, ``'hp'``, ``'none'``, or ``None``.
        :param str dispType: Either ``None`` or ``'bubble'``.
        :rtype: AliasCustomCounter
        :returns: The newly created counter.
        """
        if self.cc_exists(name):
            self.delete_cc(name)
        return self.create_cc_nx(name, *args, **kwargs)

    def cc_exists(self, name):
        """
        Returns whether a custom counter exists.

        :param str name: The name of the custom counter to check.
        :returns: Whether the counter exists.
        """
        return name in [con.name for con in self._character.consumables]

    def cc_str(self, name):
        """
        Returns a string representing a custom counter.

        :param str name: The name of the custom counter to get.
        :returns: A string representing the current value, maximum, and minimum of the counter.
        :rtype: str
        :raises: :exc:`ConsumableException` if the counter does not exist.

        Example:

        >>> cc_str("Ki")
        '11/17'
        >>> cc_str("Bardic Inspiration")
        '◉◉◉〇〇'
        """
        return str(self._get_consumable(name))

    # --- cvars ---
    @property
    def cvars(self):
        """
        Returns a dict of cvars bound on this character.

        :rtype: dict
        """
        return self._character.cvars.copy()

    def set_cvar(self, name, val: str):
        """
        Sets a custom character variable, which will be available in all scripting contexts using this character.

        :param str name: The name of the variable to set. Must be a valid identifier and not be in the :ref:`cvar-table`.
        :param str value: The value to set it to.
        """
        helpers.set_cvar(self._character, name, val)
        # noinspection PyProtectedMember
        self._interpreter._names[name] = str(val)

    def set_cvar_nx(self, name, val: str):
        """
        Sets a custom character variable if it is not already set.

        :param str name: The name of the variable to set. Must be a valid identifier and not be in the :ref:`cvar-table`.
        :param str value: The value to set it to.
        """
        if name not in self._character.cvars:
            self.set_cvar(name, val)

    def delete_cvar(self, name):
        """
        Deletes a custom character variable. Does nothing if the cvar does not exist.

        :param str name: The name of the variable to delete.
        """
        if name in self._character.cvars:
            del self._character.cvars[name]

    # --- other properties ---
    @property
    def owner(self):
        """
        Returns the id of this character's owner.

        :rtype: int
        """
        return self._character.owner

    @property
    def upstream(self):
        """
        Returns the upstream key for this character.

        :rtype: str
        """
        return self._character.upstream

    @property
    def sheet_type(self):
        """
        Returns the sheet type of this character (beyond, dicecloud, google).

        :rtype: str
        """
        return self._character.sheet_type

    @property
    def race(self):
        """
        Gets the character's race.

        :rtype: str or None
        """
        return self._character.race

    @property
    def background(self):
        """
        Gets the character's background.

        :rtype: str or None
        """
        return self._character.background

    @property
    def csettings(self):
        """
        Gets a copy of the character's settings dict.

        :rtype: dict
        """
        return self._character.options.options.copy()

    # --- private helpers ----
    async def func_commit(self, ctx):
        await self._character.commit(ctx)


class AliasCustomCounter:
    def __init__(self, cc):
        """
        :type cc: cogs5e.models.sheet.player.CustomCounter
        """
        self._cc = cc

    @property
    def name(self):
        """
        Returns the cc's name.

        :rtype: str
        """
        return self._cc.name

    @property
    def value(self):
        """
        Returns the current value of the cc.

        :rtype: int
        """
        return self._cc.value

    @property
    def max(self):
        """
        Returns the maximum value of the cc, or 2^31-1 if the cc has no max.

        :rtype: int
        """
        return self._cc.get_max()

    @property
    def min(self):
        """
        Returns the minimum value of the cc, or -2^31 if the cc has no min.

        :rtype: int
        """
        return self._cc.get_min()

    @property
    def reset_on(self):
        """
        Returns the condition on which the cc resets. ('long', 'short', 'none', None)

        :rtype: str or None
        """
        return self._cc.reset_on

    @property
    def display_type(self):
        """
        Returns the cc's display type. (None, 'bubble')

        :rtype: str
        """
        return self._cc.display_type

    def set(self, new_value, strict=False):
        """
        Sets the cc's value to a new value.

        :param int new_value: The new value to set.
        :param bool strict: Whether to error when going out of bounds (true) or to clip silently (false).
        :return: The cc's new value.
        :rtype: int
        """
        return self._cc.set(new_value, strict)

    def reset(self):
        """
        Resets the cc to its max. Errors if the cc has no max or no reset.

        :return: The cc's new value.
        :rtype: int
        """
        return self._cc.reset()

    def __str__(self):
        return str(self._cc)

    def __repr__(self):
        return f"<AliasCustomCounter name={self.name} value={self.value} max={self.max} min={self.min} " \
               f"reset_on={self.reset_on} display_type={self.display_type}>"


class AliasDeathSaves:
    def __init__(self, death_saves):
        """
        :type death_saves: cogs5e.models.sheet.player.DeathSaves
        """
        self._death_saves = death_saves

    @property
    def successes(self):
        """
        Returns the number of successful death saves.

        :rtype: int
        """
        return self._death_saves.successes

    @property
    def fails(self):
        """
        Returns the number of failed death saves.

        :rtype: int
        """
        return self._death_saves.fails

    def succeed(self, num=1):
        """
        Adds one or more successful death saves.

        :param int num: The number of successful death saves to add.
        """
        self._death_saves.succeed(num)

    def fail(self, num=1):
        """
        Adds one or more failed death saves.

        :param int num: The number of failed death saves to add.
        """
        self._death_saves.fail(num)

    def is_stable(self):
        """
        Returns whether or not the character is stable.

        :rtype: bool
        """
        return self._death_saves.is_stable()

    def is_dead(self):
        """
        Returns whether or not the character is dead.

        :rtype: bool
        """
        return self._death_saves.is_dead()

    def reset(self):
        """
        Resets all death saves.
        """
        self._death_saves.reset()

    def __str__(self):
        return str(self._death_saves)

    def __repr__(self):
        return f"<AliasDeathSaves successes={self.successes} fails={self.fails}>"
