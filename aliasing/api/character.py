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

    # helpers
    def _get_consumable(self, name):
        consumable = next((con for con in self._character.consumables if con.name == name), None)
        if consumable is None:
            raise ConsumableException(f"There is no counter named {name}.")
        return consumable

    # methods
    # --- ccs ---
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
        """
        self._get_consumable(name).set(int(value), strict)

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

    def create_cc(self, name: str, *args, **kwargs):
        """
        Creates a custom counter. If a counter with the same name already exists, it will replace it.

        :param str name: The name of the counter to create.
        :param str minVal: The minimum value of the counter. Supports :ref:`cvar-table` parsing.
        :param str maxVal: The maximum value of the counter. Supports :ref:`cvar-table` parsing.
        :param str reset: One of ``'short'``, ``'long'``, ``'hp'``, ``'none'``, or ``None``.
        :param str dispType: Either ``None`` or ``'bubble'``.
        """
        if self.cc_exists(name):
            self.delete_cc(name)
        self.create_cc_nx(name, *args, **kwargs)

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

    # --- private helpers ----
    async def func_commit(self, ctx):
        await self._character.commit(ctx)
