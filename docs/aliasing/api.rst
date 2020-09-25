Aliasing API
============

So you want to write aliases for your commonly used commands - cool!
This cheatsheet details some of the nitty-gritty syntactical shenanigans that you can use to make your aliases very powerful.

When placed inline in an alias, any syntax in the syntax table will have the listed effect.
For a list of built-in cvars, see the :ref:`cvar-table`.

For a list of user-created aliases, plus help aliasing, join the `Avrae Discord <https://support.avrae.io>`_!

Draconic
--------
The language used in Avrae aliases is a custom modified version of Python, called Draconic. In most cases,
Draconic uses the same syntax and base types as Python - any exceptions will be documented here!

As Draconic is meant to both be an operational and templating language, there are multiple ways to use Draconic
inside your alias.

.. _syntax-table:

Syntax
------
This section details the special syntax used in the Draconic language. Note that these syntaxes are only evaluated in
an alias, the ``test`` command, or the ``tembed`` command.

Rolls
^^^^^
**Syntax**: ``{diceexpr}``

**Description**: Rolls the expression inside the curly braces and is replaced by the result. If an error occurs,
is replaced by ``0``. Variables are allowed inside the expression.

**Examples**

>>> !test Rolling 1d20: {1d20}
Rolling 1d20: 7

>>> !test Strength check: {1d20 + strengthMod}
Strength check: 21

Values
^^^^^^
**Syntax**: ``<var>``

**Description**: Replaced by the value of the variable, implicitly cast to ``str``.
The variable can be a user variable, character variable, or a local variable set in a Draconic script.

**Examples**

>>> !test My strength modifier is: <strengthMod>
My strength modifier is: 2

Draconic Expressions
^^^^^^^^^^^^^^^^^^^^
**Syntax**: ``{{code}}``

**Description**: Runs the Draconic code inside the braces and is replaced by the value the code evaluates to.
If the code evaluates to ``None``, is removed from the output.

See below for a list of builtin Draconic functions.

**Examples**

>>> !test 1 more than my strength score is {{strength + 1}}!
1 more than my strength score is 15!

>>> !test My roll was {{"greater than" if roll("1d20") > 10 else "less than"}} 10!
My roll was less than 10!

Draconic Blocks
^^^^^^^^^^^^^^^
**Syntax**

.. code-block:: text

    <drac2>
    code
    </drac2>

**Description**: Runs the multi-line Draconic code between the delimiters. If a value is returned (via the ``return``
keyword), is replaced by the returned value.

**Examples**

>>> !test <drac2>
... out = []
... for i in range(5):
...   out.append(i * 2)
...   if i == 2:
...     break
... return out
... </drac2>
[0, 2, 4]

>>> !test <drac2>
... out = []
... for stat in ['strength', 'dexterity', 'constitution']:
...   out.append(get(stat))
... </drac2>
... My STR, DEX, and CON scores are {{out}}!
My STR, DEX, and CON scores are [12, 18, 14]!

Argument Parsing
^^^^^^^^^^^^^^^^
Often times when writing aliases, you will need to access user input. These special strings will be replaced
with user arguments (if applicable)!

**Syntax**: ``%1%``, ``%2%``, etc.

**Description**: Replaced with the Nth argument passed to the alias. If the argument contains spaces, the replacement
will contain quotes around the argument.

**Syntax**: ``%*%``

**Description**: Replaced with the unmodified string following the alias.

**Syntax**: ``&1&``, ``&2&``, etc.

**Description**: Replaced with the Nth argument passed to the alias. If the argument contains spaces, the replacement
will **not** contain quotes around the argument. Additionally, any quotes in the argument will be backslash-escaped.

**Syntax**: ``&*&``

**Description**: Replaced with the string following the alias. Any quotes will be backslash-escaped.

**Syntax**: ``&ARGS&``

**Description**: Replaced with a list representation of all arguments - usually you'll want to put this in Draconic
code.

**Examples**

>>> !alias asdf echo %2% %1%
>>> !asdf first "second arg"
"second arg" first

>>> !alias asdf echo %*% first
>>> !asdf second "third word"
second "third word" first

>>> !alias asdf echo &1& was the first arg
>>> !asdf "hello world"
hello world was the first arg

>>> !alias asdf echo &*& words
>>> !asdf second "third word"
second \"third word\" words

>>> !alias asdf echo &ARGS&
>>> !asdf first "second arg"
['first', 'second arg']

.. _cvar-table:

Cvar Table
----------
This table lists the available cvars when a character is active.

================ =========================================== ====
Name             Description                                 Type
================ =========================================== ====
armor            Armor Class.                                int
charisma         Charisma score.                             int
charismaMod      Charisma modifier.                          int
charismaSave     Charisma saving throw modifier.             int
constitution     Constitution score.                         int
constitutionMod  Constitution modifier.                      int
constitutionSave Constitution saving throw modifier.         int
description      Full character description.                 str
dexterity        Dexterity score.                            int
dexterityMod     Dexterity modifier.                         int
dexteritySave    Dexterity saving throw modifier.            int
hp               Maximum hit points.                         int
image            Character image URL.                        str
intelligence     Intelligence score.                         int
intelligenceMod  Intelligence modifier.                      int
intelligenceSave Intelligence saving throw modifier.         int
level            Character level.                            int
name             The character's name.                       str
proficiencyBonus Proficiency bonus.                          int
spell            The character's spellcasting ability mod.   int
strength         Strength score.                             int
strengthMod      Strength modifier.                          int
strengthSave     Strength saving throw modifier.             int
wisdom           Wisdom score.                               int
wisdomMod        Wisdom modifier.                            int
wisdomSave       Wisdom saving throw modifier.               int
XLevel           How many levels a character has in class X. int
================ =========================================== ====

.. note::
    ``XLevel`` is not guaranteed to exist for any given ``X``, and may not exist for GSheet 1.3/1.4 characters.
    It is recommended to use ``AliasCharacter.levels.get()`` to access arbitrary levels instead.

.. _function-reference:

Function Reference
------------------

.. warning::
    It may be possible to corrupt your character data by incorrectly calling functions. Script at your own risk.

All Contexts
^^^^^^^^^^^^

These functions are available in any scripting context, regardless if you have a character active or not.

Python Builtins
"""""""""""""""

.. function:: all(iterable)

    Return ``True`` if all elements of the *iterable* are true, or if the iterable is empty.

.. function:: any(iterable)

    Return ``True`` if any element of the *iterable* is true. If the iterable is empty, return ``False``.

.. function:: ceil(x)

    Rounds a number up to the nearest integer. See :func:`math.ceil`.

    :param x: The number to round.
    :type x: float or int
    :return: The smallest integer >= x.
    :rtype: int

.. function:: float(x)

    Converts *x* to a floating point number.

    :param x: The value to convert.
    :type x: str, int, or float
    :return: The float.
    :rtype: float

.. function:: floor(x)

    Rounds a number down to the nearest integer. See :func:`math.floor`.

    :param x: The number to round.
    :type x: float or int
    :return: The largest integer <= x.
    :rtype: int

.. function:: int(x)

    Converts *x* to an integer.

    :param x: The value to convert.
    :type x: str, int, or float
    :return: The integer.
    :rtype: int

.. function:: len(s)

    Return the length (the number of items) of an object. The argument may be a sequence
    (such as a string, bytes, tuple, list, or range) or a collection (such as a dictionary, set, or frozen set).

    :return: The length of the argument.
    :rtype: int

.. function:: max(iterable, *[, key, default])
              max(arg1, arg2, *args[, key])

    Return the largest item in an iterable or the largest of two or more arguments.

    If one positional argument is provided, it should be an iterable. The largest item in the iterable is returned.
    If two or more positional arguments are provided, the largest of the positional arguments is returned.

    There are two optional keyword-only arguments.
    The key argument specifies a one-argument ordering function like that used for :func:`list.sort()`.
    The default argument specifies an object to return if the provided iterable is empty.
    If the iterable is empty and default is not provided, a :exc:`ValueError` is raised.

    If multiple items are maximal, the function returns the first one encountered.

.. function:: min(iterable, *[, key, default])
              min(arg1, arg2, *args[, key])

    Return the smallest item in an iterable or the smallest of two or more arguments.

    If one positional argument is provided, it should be an iterable. The smallest item in the iterable is returned.
    If two or more positional arguments are provided, the smallest of the positional arguments is returned.

    There are two optional keyword-only arguments.
    The key argument specifies a one-argument ordering function like that used for :func:`list.sort()`.
    The default argument specifies an object to return if the provided iterable is empty.
    If the iterable is empty and default is not provided, a :exc:`ValueError` is raised.

    If multiple items are minimal, the function returns the first one encountered.

.. function:: range(stop)
              range(start, stop[, step])

    Returns a list of numbers in the specified range.

    If the step argument is omitted, it defaults to ``1``. If the start argument is omitted, it defaults to ``0``.
    If step is zero, :exc:`ValueError` is raised.

    For a positive step, the contents of a range ``r`` are determined by the formula
    ``r[i] = start + step*i`` where ``i >= 0`` and ``r[i] < stop``.

    For a negative step, the contents of the range are still determined by the formula
    ``r[i] = start + step*i``, but the constraints are ``i >= 0`` and ``r[i] > stop``.

    A range object will be empty if r[0] does not meet the value constraint.
    Ranges do support negative indices, but these are interpreted as indexing from the end of the sequence determined
    by the positive indices.

    :param int start: The start of the range (inclusive).
    :param int stop: The end of the range (exclusive).
    :param int step: The step value.
    :return: The range of numbers.
    :rtype: list

.. function:: round(number[, ndigits])

    Return number rounded to ndigits precision after the decimal point.
    If ndigits is omitted or is None, it returns the nearest integer to its input.

    :param number: The number to round.
    :type number: float or int
    :param int ndigits: The number of digits after the decimal point to keep.
    :return: The rounded number.
    :rtype: float

.. function:: sqrt(x)

    See :func:`math.sqrt`.

    :return: The square root of *x*.
    :rtype: float

.. function:: str(x)

    Converts *x* to a string.

    :param x: The value to convert.
    :type x: Any
    :return: The string.
    :rtype: str

.. function:: sum(iterable[, start])

    Sums *start* and the items of an *iterable* from left to right and returns the total. *start* defaults to ``0``.
    The *iterable*’s items are normally numbers, and the start value is not allowed to be a string.

.. function:: time()

    Return the time in seconds since the UNIX epoch (Jan 1, 1970, midnight UTC) as a floating point number.
    See :func:`time.time`.

    :return: The epoch time.
    :rtype: float

Draconic Functions
""""""""""""""""""

.. autofunction:: utils.argparser.argparse(args)

    >>> args = argparse("adv -rr 2 -b 1d4[bless]")
    >>> args.adv()
    1
    >>> args.last('rr')
    '2'
    >>> args.get('b')
    ['1d4[bless]']

.. autofunction:: aliasing.evaluators.ScriptingEvaluator.character()

.. autofunction:: aliasing.evaluators.ScriptingEvaluator.combat()

    .. note::
        If called outside of a character context, ``combat().me`` will be ``None``.

.. attribute:: ctx

    The context the alias was invoked in. See :class:`~aliasing.api.context.AliasContext` for more details.

    Note that this is an automatically bound name and not a function.

    :type: :class:`~aliasing.api.context.AliasContext`


.. autofunction:: aliasing.evaluators.ScriptingEvaluator.delete_uvar(name)

.. autofunction:: aliasing.evaluators.ScriptingEvaluator.dump_json

.. autofunction:: aliasing.api.functions.err

.. autofunction:: aliasing.evaluators.ScriptingEvaluator.exists(name)

.. autofunction:: aliasing.evaluators.ScriptingEvaluator.get(name, default=None)

.. autofunction:: aliasing.evaluators.ScriptingEvaluator.get_gvar(address)

.. autofunction:: aliasing.evaluators.ScriptingEvaluator.load_json

.. function:: randint(x)

    Returns a random integer in the range ``[0..x)``.

    :param int x: The upper limit (non-inclusive).
    :return: A random integer.
    :rtype: int

.. autofunction:: aliasing.api.functions.roll

.. autofunction:: aliasing.evaluators.ScriptingEvaluator.set_uvar(name, value)

.. autofunction:: aliasing.evaluators.ScriptingEvaluator.set_uvar_nx(name, value)

.. autofunction:: aliasing.api.functions.typeof

.. autofunction:: aliasing.evaluators.ScriptingEvaluator.uvar_exists(name)

.. autofunction:: aliasing.api.functions.vroll(rollStr, multiply=1, add=0)

.. warning::
    The following functions are deprecated and should be avoided:

    .. autofunction:: aliasing.evaluators.ScriptingEvaluator.chanid()

    .. autofunction:: aliasing.evaluators.ScriptingEvaluator.servid()

    .. autofunction:: aliasing.evaluators.ScriptingEvaluator.set(name, value)

Character Context
^^^^^^^^^^^^^^^^^

These functions are only available when a character is active in a scripting context. Otherwise, attempts to call
these functions will raise a :exc:`FunctionRequiresCharacter` exception.

.. warning::

    As of v2.2.0, *all* character context functions have been deprecated and should be replaced. See each function's
    documentation for its replacement.

Custom Counters
"""""""""""""""

.. warning::

    .. function:: cc_exists(name)

        .. deprecated:: 2.5.0
            Use ``character().cc_exists()`` instead.

        Returns whether a custom counter exists.

        :param str name: The name of the custom counter to check.
        :returns: Whether the counter exists.
        :rtype: bool

    .. function:: cc_str(name)

        .. deprecated:: 2.5.0
            Use ``character().cc_str()`` instead.

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

    .. function:: create_cc(name, minVal=None, maxVal=None, reset=None, dispType=None)

        .. deprecated:: 2.5.0
            Use ``character().create_cc()`` instead.

        Creates a custom counter. If a counter with the same name already exists, it will replace it.

        :param str name: The name of the counter to create.
        :param str minVal: The minimum value of the counter. Supports :ref:`cvar-table` parsing.
        :param str maxVal: The maximum value of the counter. Supports :ref:`cvar-table` parsing.
        :param str reset: One of ``'short'``, ``'long'``, ``'hp'``, ``'none'``, or ``None``.
        :param str dispType: Either ``None`` or ``'bubble'``.

    .. function:: create_cc_nx(name, minVal=None, maxVal=None, reset=None, dispType=None)

        .. deprecated:: 2.5.0
            Use ``character().create_cc_nx()`` instead.

        Creates a custom counter if one with the given name does not already exist.
        Equivalent to:

        >>> if not cc_exists(name):
        >>>     create_cc(name, minVal, maxVal, reset, dispType)

    .. function:: delete_cc(name)

        .. deprecated:: 2.5.0
            Use ``character().delete_cc()`` instead.

        Deletes a custom counter.

        :param str name: The name of the custom counter to delete.
        :raises: :exc:`ConsumableException` if the counter does not exist.

    .. function:: get_cc(name)

        .. deprecated:: 2.5.0
            Use ``character().get_cc()`` instead.

        Gets the value of a custom counter.

        :param str name: The name of the custom counter to get.
        :returns: The current value of the counter.
        :rtype: int
        :raises: :exc:`ConsumableException` if the counter does not exist.


    .. function:: get_cc_max(name)

        .. deprecated:: 2.5.0
            Use ``character().get_cc_max()`` instead.

        Gets the maximum value of a custom counter.

        :param str name: The name of the custom counter maximum to get.
        :returns: The maximum value of the counter. If a counter has no maximum, it will return an obscenely large number (2^31-1).
        :rtype: int
        :raises: :exc:`ConsumableException` if the counter does not exist.

    .. function:: get_cc_min(name)

        .. deprecated:: 2.5.0
            Use ``character().get_cc_min()`` instead.

        Gets the minimum value of a custom counter.

        :param str name: The name of the custom counter minimum to get.
        :returns: The minimum value of the counter. If a counter has no minimum, it will return an obscenely small number (-2^31).
        :rtype: int
        :raises: :exc:`ConsumableException` if the counter does not exist.

    .. function:: mod_cc(name, value, strict=False)

        .. deprecated:: 2.5.0
            Use ``character().mod_cc()`` instead.

        Modifies the value of a custom counter. Equivalent to ``set_cc(name, get_cc(name) + value, strict)``.

    .. function:: set_cc(name, value, strict=False)

        .. deprecated:: 2.5.0
            Use ``character().set_cc()`` instead.

        Sets the value of a custom counter.

        :param str name: The name of the custom counter to set.
        :param int value: The value to set the counter to.
        :param bool strict: If ``True``, will raise a :exc:`CounterOutOfBounds` if the new value is out of bounds, otherwise silently clips to bounds.
        :raises: :exc:`ConsumableException` if the counter does not exist.

Spell Slots
"""""""""""

.. warning::

    .. function:: get_slots(level)

        .. deprecated:: 2.5.0
            Use ``character().spellbook.get_slots()`` instead.

        Gets the number of remaining spell slots of a given level that a character has.

        :param int level: The level to get the remaining slots of.
        :returns: The number of remaining slots of that level.
        :rtype: int

    .. function:: get_slots_max(level)

        .. deprecated:: 2.5.0
            Use ``character().spellbook.get_slots_max()`` instead.

        Gets the maximum number of spell slots of a given level that a character has.

        :param int level: The level to get the maximum slots of.
        :returns: The maximum number of slots of that level.
        :rtype: int

    .. function:: set_slots(level, value)

        .. deprecated:: 2.5.0
            Use ``character().spellbook.set_slots()`` instead.

        Sets how many spell slots of a given level a character has.

        :param int level: The level of spell slots to set.
        :param int value: The value to set the remaining slots to.
        :raises: :exc:`CounterOutOfBounds` if the number of slots is invalid.

    .. function:: slots_str(level)

        .. deprecated:: 2.5.0
            Use ``character().spellbook.slots_str()`` instead.

        Returns a string representing how many spell slots a character has of a given level.

        :param int level: The level to get the slots of.
        :returns: A string representing the current remaining and maximum number of slots of that level.
        :rtype: str

    .. function:: use_slot(level)

        .. deprecated:: 2.5.0
            Use ``character().spellbook.use_slot()`` instead.

        Uses one spell slot of a given level. Equivalent to ``set_slots(level, get_slots(level) - 1)``.

Hit Points
""""""""""

.. warning::

    .. function:: get_hp()

        .. deprecated:: 2.5.0
            Use ``character().hp`` instead.

        :returns: The character's current hit points.
        :rtype: int

    .. function:: get_temphp()

        .. deprecated:: 2.5.0
            Use ``character().temp_hp`` instead.

        :returns: The character's current temporary hit points.
        :rtype: int

    .. function:: hp_str()

        .. deprecated:: 2.5.0
            Use ``character().hp_str()`` instead.

        Returns a string representing a character's current HP, max HP, and temp HP.

    .. function:: mod_hp(value, overflow=True)

        .. deprecated:: 2.5.0
            Use ``character().modify_hp()`` instead.

        Modifies the character's remaining hit points by *value*. If *value* is negative, will deal damage to temp HP first.

        :param int value: How much to modify remaining HP by.
        :param bool overflow: If ``False``, clips the new HP value to ``[0..hp]``.

    .. function:: set_hp(value)

        .. deprecated:: 2.5.0
            Use ``character().set_hp()`` instead.

        Sets the character's remaining hit points. Ignores temp HP.

        :param int value: The new value for hit points.

    .. function:: set_temphp(value)

        .. deprecated:: 2.5.0
            Use ``character().set_temp_hp()`` instead.

        Sets the character's remaining temp HP.

        :param int value: The new value for temporary hit points.

Cvars
"""""

.. warning::

    .. note::
        All custom character variables are locally bound to a Draconic scope. To access their values, use them like a normal
        name.

    .. function:: delete_cvar(name)

        .. deprecated:: 2.5.0
            Use ``character().delete_cvar()`` instead.

        Deletes a custom character variable. Does nothing if the cvar does not exist.

        :param str name: The name of the variable to delete.

    .. function:: set_cvar(name, value)

        .. deprecated:: 2.5.0
            Use ``character().set_cvar()`` instead.

        Sets a custom character variable, which will be available in all scripting contexts using this character.

        :param str name: The name of the variable to set. Must be a valid identifier and not be in the :ref:`cvar-table`.
        :param str value: The value to set it to.

    .. function:: set_cvar_nx(name, value)

        .. deprecated:: 2.5.0
            Use ``character().set_cvar_nx()`` instead.

        Sets a custom character variable if it is not already set.

        :param str name: The name of the variable to set. Must be a valid identifier and not be in the :ref:`cvar-table`.
        :param str value: The value to set it to.

Other
"""""

.. warning::

    .. function:: get_raw()

        .. deprecated:: 2.5.0
            Deprecated without replacement. Use ``character()`` to get a representation of the character instead.

        Returns a raw representation of character data.

See Also
--------

Draconic's syntax is very similar to Python. Other Python features supported in Draconic include:

* `Ternary Operators <https://stackoverflow.com/a/394814>`_ (``x if a else y``)
* `Slicing <https://stackoverflow.com/a/663175>`_ (``"Hello world!"[2:4]``)
* `Operators <https://docs.python.org/3/reference/expressions.html#unary-arithmetic-and-bitwise-operations>`_ (``2 + 2``, ``"foo" in "foobar"``, etc)
* `Assignments <https://docs.python.org/3/reference/simple_stmts.html#assignment-statements>`_ (``a = 15``)
* `List Comprehensions <https://docs.python.org/3/tutorial/datastructures.html#list-comprehensions>`_

Initiative Models
-----------------

SimpleCombat
^^^^^^^^^^^^

.. autoclass:: aliasing.api.combat.SimpleCombat()
    :members:

    .. attribute:: combatants

        A list of all :class:`~aliasing.api.combat.SimpleCombatant` in combat.

    .. attribute:: current

        The :class:`~aliasing.api.combat.SimpleCombatant` or :class:`~aliasing.api.combat.SimpleGroup`
        representing the combatant whose turn it is.

    .. attribute:: me

        The :class:`~aliasing.api.combat.SimpleCombatant` representing the active character in combat, or ``None``
        if the character is not in the combat.

    .. attribute:: round_num

        An :class:`int` representing the round number of the combat.

    .. attribute:: turn_num

        An :class:`int` representing the initiative score of the current turn.

SimpleCombatant
^^^^^^^^^^^^^^^

.. autoclass:: aliasing.api.combat.SimpleCombatant(AliasStatBlock)
    :inherited-members:
    :members:

    .. attribute:: effects

        A list of :class:`~aliasing.api.combat.SimpleEffect` active on the combatant.

        :type: list of :class:`~aliasing.api.combat.SimpleEffect`

    .. attribute:: init

        What the combatant rolled for initiative.

        :type: int

    .. attribute:: initmod

        An int representing the combatant's initiative modifier.

        :type: int

    .. attribute:: level

        .. deprecated:: 2.5.0
            Use ``SimpleCombatant.levels.total_level`` or ``SimpleCombatant.spellbook.caster_level`` instead.

        The combatant's spellcaster level. ``0`` if the combatant is not a player or spellcaster.

        :type: int

    .. attribute:: resists

        .. deprecated:: 2.5.0
            Use ``SimpleCombatant.resistances`` instead.

        The combatant's resistances, immunities, and vulnerabilities.

        :type: :class:`~aliasing.api.statblock.AliasResistances`

    .. attribute:: type

        The type of the object (``"combatant"``), to determine whether this is a group or not.

        :type: str


SimpleGroup
^^^^^^^^^^^

.. autoclass:: aliasing.api.combat.SimpleGroup()
    :members:

    .. attribute:: combatants

        A list of all :class:`~aliasing.api.combat.SimpleCombatant` in this group.

    .. attribute:: type

        The type of the object (``"group"``), to determine whether this is a group or not.

        :type: str

SimpleEffect
^^^^^^^^^^^^

.. autoclass:: aliasing.api.combat.SimpleEffect()
    :members:

    .. attribute:: conc

        Whether the effect requires concentration.

        :type: bool

    .. attribute:: duration

        The initial duration of the effect, in rounds (``-1`` = infinite).

        :type: int

    .. attribute:: effect

        The applied effect of the object.

        :type: dict

    .. attribute:: name

        The name of the effect.

        :type: str

    .. attribute:: remaining

        The remaining duration of the effect, in rounds.

        :type: int

SimpleRollResult
----------------

.. autoclass:: aliasing.api.functions.SimpleRollResult()

    .. attribute:: dice

        The rolled dice (e.g. ``1d20 (5)``).

        :type: str

    .. attribute:: total

        The total of the roll.

        :type: int

    .. attribute:: full

        The string representing the roll.

        :type: str

    .. attribute:: result

        The RollResult object returned by the roll.

        :type: :class:`d20.RollResult`

    .. attribute:: raw

        The Expression object returned by the roll. Equivalent to ``SimpleRollResult.result.expr``.

        :type: :class:`d20.Expression`

    .. automethod:: consolidated

    .. automethod:: __str__

ParsedArguments
---------------

.. autoclass:: utils.argparser.ParsedArguments()
    :members:

Context Models
--------------

AliasContext
^^^^^^^^^^^^

.. autoclass:: aliasing.api.context.AliasContext()
    :members:

AliasGuild
^^^^^^^^^^

.. autoclass:: aliasing.api.context.AliasGuild()
    :members:

AliasChannel
^^^^^^^^^^^^

.. autoclass:: aliasing.api.context.AliasChannel()
    :members:

AliasAuthor
^^^^^^^^^^^

.. autoclass:: aliasing.api.context.AliasAuthor()
    :members:

AliasCharacter
--------------

.. autoclass:: aliasing.api.character.AliasCharacter(AliasStatBlock)
    :members:
    :inherited-members:

AliasCustomCounter
^^^^^^^^^^^^^^^^^^

.. autoclass:: aliasing.api.character.AliasCustomCounter()
    :members:

AliasDeathSaves
^^^^^^^^^^^^^^^

.. autoclass:: aliasing.api.character.AliasDeathSaves()
    :members:

StatBlock Models
----------------

AliasStatBlock
^^^^^^^^^^^^^^

.. autoclass:: aliasing.api.statblock.AliasStatBlock()
    :members:

AliasBaseStats
^^^^^^^^^^^^^^

.. autoclass:: aliasing.api.statblock.AliasBaseStats()
    :members:

AliasLevels
^^^^^^^^^^^

.. autoclass:: aliasing.api.statblock.AliasLevels()
    :members:

    .. attribute:: for (cls, level) in AliasLevels:

        Iterates over pairs of class names and the number of levels in that class.

        :type: Iterable[tuple[str, int]]

AliasAttackList
^^^^^^^^^^^^^^^

.. autoclass:: aliasing.api.statblock.AliasAttackList()
    :members:

    .. attribute:: str(AliasAttackList)

        Returns a string representation of all attacks in this attack list.

        :type: str

    .. attribute:: len(AliasAttackList)

        Returns the number of attacks in this attack list.

        :type: int

    .. attribute:: for attack in AliasAttackList:

        Iterates over attacks in this attack list.

        :type: Iterable[:class:`~aliasing.api.statblock.AliasAttack`]

    .. attribute:: AliasAttackList[i]

        Gets the *i*-th indexed attack.

        :type: :class:`~aliasing.api.statblock.AliasAttack`


AliasAttack
^^^^^^^^^^^^^^

.. autoclass:: aliasing.api.statblock.AliasAttack()
    :members:

    .. attribute:: str(AliasAttack)

        Returns a string representation of this attack.

        :type: str

AliasSkill
^^^^^^^^^^^^^^

.. autoclass:: aliasing.api.statblock.AliasSkill()
    :members:

AliasSkills
^^^^^^^^^^^^^^

.. autoclass:: aliasing.api.statblock.AliasSkills()

    .. attribute:: for (skill_name, skill) in AliasSkills:

        Iterates over pairs of skill names and corresponding skills.

        :type: Iterable[tuple[str, :class:`~aliasing.api.statblock.AliasSkill`]]

    .. attribute:: acrobatics
        animalHandling
        arcana
        athletics
        deception
        history
        initiative
        insight
        intimidation
        investigation
        medicine
        nature
        perception
        performance
        persuasion
        religion
        sleightOfHand
        stealth
        survival
        strength
        dexterity
        constitution
        intelligence
        wisdom
        charisma

        The skill modifier for the given skill.

        :type: :class:`~aliasing.api.statblock.AliasSkill`

AliasSaves
^^^^^^^^^^^^^^

.. autoclass:: aliasing.api.statblock.AliasSaves()
    :members:

    .. attribute:: for (save_name, skill) in AliasSaves:

        Iterates over pairs of save names and corresponding save.

        :type: Iterable[tuple[str, :class:`~aliasing.api.statblock.AliasSkill`]]

AliasResistances
^^^^^^^^^^^^^^^^

.. autoclass:: aliasing.api.statblock.AliasResistances()
    :members:

Resistance
^^^^^^^^^^

.. autoclass:: cogs5e.models.sheet.resistance.Resistance()
    :members:

    .. attribute:: dtype

        The damage type.

        :type: str

    .. attribute:: unless

        A set of tokens that if present, this resistance will not apply.

        :type: set[str]

    .. attribute:: only

        A set of tokens that unless present, this resistance will not apply.

        :type: set[str]

AliasSpellbook
^^^^^^^^^^^^^^

.. autoclass:: aliasing.api.statblock.AliasSpellbook()
    :members:

    .. attribute:: spell in AliasSpellbook

        Returns whether the spell named *spell* (str) is known.

        :type: bool

AliasSpellbookSpell
"""""""""""""""""""

.. autoclass:: aliasing.api.statblock.AliasSpellbookSpell()
    :members: