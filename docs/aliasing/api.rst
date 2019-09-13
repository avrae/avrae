Aliasing API
============

So you want to write aliases for your commonly used commands - cool!
This cheatsheet details some of the nitty-gritty syntactical shenanigans that you can use to make your aliases very powerful.

When placed inline in an alias, any syntax in the syntax table will have the listed effect.
For a list of built-in cvars, see the :ref:`cvar-table`.

For a list of user-created aliases, plus help aliasing, join the `Avrae Discord <https://support.avrae.io>`_!

.. _syntax-table:

Syntax Table
------------
This table details the special syntax used in the Draconic language. Note that these syntaxes are only evaluated in
an alias, the ``test`` command, or the ``tembed`` command.

+------------------------+----------------------------------------------------------------------------------------+
| Syntax                 | Description                                                                            |
+========================+========================================================================================+
| ``{CVAR/roll}``        | Evaluates the cvar/rolls the input.                                                    |
+------------------------+----------------------------------------------------------------------------------------+
| ``<CVAR>``             | Prints the value of the cvar.                                                          |
+------------------------+----------------------------------------------------------------------------------------+
| ``%1%``, ``%2%``, etc. | Replaced with the value of the nth argument passed to the alias.                       |
+------------------------+----------------------------------------------------------------------------------------+
| ``%*%``                | Replaced with the string following the alias.                                          |
+------------------------+----------------------------------------------------------------------------------------+
| ``&1&``, ``&2&``, etc. | Replaced with the raw value of the nth argument passed to the alias.                   |
+------------------------+----------------------------------------------------------------------------------------+
| ``&*&``                | Replaced with the escaped value of the string following the alias.                     |
+------------------------+----------------------------------------------------------------------------------------+
| ``&ARGS&``             | Replaced with a list of all arguments.                                                 |
+------------------------+----------------------------------------------------------------------------------------+
| ``{{code}}``           | Runs the statement as raw Python-like code. See below for a list of allowed functions. |
+------------------------+----------------------------------------------------------------------------------------+

.. _syntax-examples:

Examples
^^^^^^^^

>>> !test Rolling 1d20: {1d20}
Rolling 1d20: 7

>>> !test My strength modifier is: <strengthMod>
My strength modifier is: 2

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

>>> !test {{strength_plus_one=strength+1}}1 more than my strength score is {{strength_plus_one}}!
1 more than my strength score is 15!

>>> !test My roll was {{"greater than" if roll("1d20") > 10 else "less than"}} 10!
My roll was less than 10!

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

.. autofunction:: cogs5e.funcs.scripting.evaluators.ScriptingEvaluator.chanid()

.. autofunction:: cogs5e.funcs.scripting.evaluators.ScriptingEvaluator.combat()

.. autofunction:: cogs5e.funcs.scripting.evaluators.ScriptingEvaluator.delete_uvar(name)

.. autofunction:: cogs5e.funcs.scripting.functions.dump_json

.. autofunction:: cogs5e.funcs.scripting.functions.err

.. autofunction:: cogs5e.funcs.scripting.evaluators.ScriptingEvaluator.exists(name)

.. autofunction:: cogs5e.funcs.scripting.evaluators.ScriptingEvaluator.get(name, default=None)

.. autofunction:: cogs5e.funcs.scripting.evaluators.ScriptingEvaluator.get_gvar(address)

.. autofunction:: cogs5e.funcs.scripting.functions.load_json

.. function:: randint(x)

    Returns a random integer in the range ``[0..x)``.

    :param int x: The upper limit (non-inclusive).
    :return: A random integer.
    :rtype: int

.. autofunction:: cogs5e.funcs.scripting.evaluators.ScriptingEvaluator.servid()

.. autofunction:: cogs5e.funcs.scripting.evaluators.ScriptingEvaluator.set(name, value)

.. autofunction:: cogs5e.funcs.scripting.evaluators.ScriptingEvaluator.set_uvar(name, value)

.. autofunction:: cogs5e.funcs.scripting.evaluators.ScriptingEvaluator.set_uvar_nx(name, value)

.. autofunction:: cogs5e.funcs.scripting.functions.simple_roll

.. autofunction:: cogs5e.funcs.scripting.functions.typeof

.. autofunction:: cogs5e.funcs.scripting.evaluators.ScriptingEvaluator.uvar_exists(name)

.. autofunction:: cogs5e.funcs.scripting.functions.vroll(rollStr, multiply=1, add=0)

Character Context
^^^^^^^^^^^^^^^^^
