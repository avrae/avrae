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

.. note::
    It is highly recommended to be familiar with the Python language before diving into Draconic, as the two
    use the same syntax and types.

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
If the code evaluates to ``None``, is removed from the output, otherwise it is cast to ``str``.

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

**Description**: Runs the multi-line Draconic code between the delimiters. If a non-``None`` value is returned (via the
``return`` keyword), is replaced by the returned value, cast to ``str``.

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

Non-Code, Space-Aware
"""""""""""""""""""""

**Syntax**: ``%1%``, ``%2%``, ..., ``%N%``

**Description**: Replaced with the Nth argument passed to the alias. If the argument contains spaces, the replacement
will contain quotes around the argument.

Non-Code, Preserving All
""""""""""""""""""""""""

**Syntax**: ``%*%``

**Description**: Replaced with the unmodified string following the alias.

In Code, Quote-Escaping
"""""""""""""""""""""""

**Syntax**: ``&1&``, ``&2&``, etc.

**Description**: Replaced with the Nth argument passed to the alias. If the argument contains spaces, the replacement
will **not** contain quotes around the argument. Additionally, any quotes in the argument will be backslash-escaped.

In Code, Quote-Escaping All
"""""""""""""""""""""""""""

**Syntax**: ``&*&``

**Description**: Replaced with the string following the alias. Any quotes will be backslash-escaped.

In Code, List Literal
"""""""""""""""""""""

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
charisma         Charisma score.                             int
charismaMod      Charisma modifier.                          int
charismaSave     Charisma saving throw modifier.             int
constitution     Constitution score.                         int
constitutionMod  Constitution modifier.                      int
constitutionSave Constitution saving throw modifier.         int
dexterity        Dexterity score.                            int
dexterityMod     Dexterity modifier.                         int
dexteritySave    Dexterity saving throw modifier.            int
intelligence     Intelligence score.                         int
intelligenceMod  Intelligence modifier.                      int
intelligenceSave Intelligence saving throw modifier.         int
strength         Strength score.                             int
strengthMod      Strength modifier.                          int
strengthSave     Strength saving throw modifier.             int
wisdom           Wisdom score.                               int
wisdomMod        Wisdom modifier.                            int
wisdomSave       Wisdom saving throw modifier.               int
armor            Armor Class.                                int
color            The CSettings color for the character       str
description      Full character description.                 str
hp               Maximum hit points.                         int
image            Character image URL.                        str
level            Character level.                            int
name             The character's name.                       str
proficiencyBonus Proficiency bonus.                          int
spell            The character's spellcasting ability mod.   int
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

Python Builtins
^^^^^^^^^^^^^^^

.. function:: abs(x)

    Takes a number (float or int) and returns the absolute value of that number.

    :param x: The number to find the absolute value of.
    :type x: float or int
    :return: The absolute value of x.
    :rtype: float or int

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

.. function:: enumerate(x[, start=0)

    Returns a iterable of tuples containing a count and the values from the iterable.

    :param x: The value to convert.
    :type x: iterable
    :param start: The starting value for the count
    :type start: int
    :return: enumerate of count and objects.
    :rtype: iterable[tuple[int, any]]

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
^^^^^^^^^^^^^^^^^^

.. function:: argparse(args, parse_ephem=True)

    Given an argument string or list, returns the parsed arguments using the argument nondeterministic finite automaton.

    If *parse_ephem* is False, arguments like ``-d1`` are saved literally rather than as an ephemeral argument.

    .. note::

        Arguments must begin with a letter and not end with a number (e.g. ``d``, ``e12s``, ``a!!``). Values immediately
        following a flag argument (i.e. one that starts with ``-``) will not be parsed as arguments unless they are also
        a flag argument.

        There are three exceptions to this rule: ``-i``, ``-h``, and ``-v``, none of which take additional values.

    :param args: A list or string of arguments.
    :param bool parse_ephem:  Whether to treat args like ``-d1`` as ephemeral arguments or literal ones.
    :return: The parsed arguments
    :rtype: :class:`~utils.argparser.ParsedArguments()`

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

.. autofunction:: aliasing.evaluators.ScriptingEvaluator.load_yaml

.. autofunction:: aliasing.evaluators.ScriptingEvaluator.dump_yaml

.. autofunction:: aliasing.evaluators.ScriptingEvaluator.load_json

.. autofunction:: aliasing.evaluators.ScriptingEvaluator.dump_json

.. autofunction:: aliasing.api.functions.err

.. autofunction:: aliasing.evaluators.ScriptingEvaluator.exists(name)

.. autofunction:: aliasing.evaluators.ScriptingEvaluator.get(name, default=None)

.. autofunction:: aliasing.evaluators.ScriptingEvaluator.get_gvar(address)

.. autofunction:: aliasing.evaluators.ScriptingEvaluator.get_svar(name[, default=None])

.. autofunction:: aliasing.evaluators.ScriptingEvaluator.get_uvars()

.. autofunction:: aliasing.evaluators.ScriptingEvaluator.get_uvar(name[, default=None])

.. function:: randint(stop)
              randint(start, stop[, step])

    Returns a random integer in the range ``[start..stop)``.
    
    If the step argument is omitted, it defaults to ``1``. If the start argument is omitted, it defaults to ``0``.
    If step is zero, :exc:`ValueError` is raised.

    For a positive step, the contents of a range ``r`` are determined by the formula
    ``r[i] = start + step*i`` where ``i >= 0`` and ``r[i] < stop``.

    For a negative step, the contents of the range are still determined by the formula
    ``r[i] = start + step*i``, but the constraints are ``i >= 0`` and ``r[i] > stop``.

    :param int start: The lower limit (inclusive).
    :param int stop: The upper limit (non-inclusive).
    :param int step: The step value.
    :return: A random integer.
    :rtype: int

.. function:: randchoice(seq)
    
    Returns a random item from ``seq``.
    
    :param seq: The itterable to choose a random item from.
    :type seq: iterable.
    :return: A random item from the iterable.
    :rtype: Any.

.. function:: randchoices(population, weights=None, cum_weights=None, k=1)
    
    Returns a list of random items from ``population`` of ``k`` length with either weighted or cumulatively weighted odds.
    The ``weights`` [2,1,1] are equal to ``cum_weights`` [2,3,4]. 
    If no ``weights`` or ``cum_weights`` are input, the items in ``population`` will have equal odds of being chosen.
    If no ``k`` is input, the output length will be 1.
    
    :param population: The itterable to choose random items from.
    :type population: iterable.
    :param weights: The odds for each item in the ``population`` iterable.
    :type weights: list of integers, floats, and fractions but not decimals
    :param cum_weights: The cumulative odds for each item in the ``population`` itterable.
    :type cum_weights: list of integers, floats, and fractions but not decimals
    :param k: The length of the output.
    :type k: int
    :return: A list of random items from the iterable.
    :rtype: list
    
.. autofunction:: aliasing.api.functions.roll

.. autofunction:: aliasing.evaluators.ScriptingEvaluator.set_uvar(name, value)

.. autofunction:: aliasing.evaluators.ScriptingEvaluator.set_uvar_nx(name, value)

.. autofunction:: aliasing.evaluators.ScriptingEvaluator.signature(data=0)

.. autofunction:: aliasing.evaluators.ScriptingEvaluator.verify_signature(data)

    If you are building your own application and want to verify these signatures yourself, we provide an API endpoint
    you can use to verify signatures!

    Below is an example of Python code to verify a signature using the ``httpx`` (requests-like) library:

    .. code-block:: python

        signature = "Dc3SEuDEMKIJZ0qbasAAAQKZ2xjlQgAAAAAAAAAAAAAAAAAABQ==.B5RLdufsD9utKaDou+94LEfOgpA="
        async with httpx.AsyncClient() as client:
            r = await client.post(
                "https://api.avrae.io/bot/signature/verify",
                json={"signature": signature}
            )
        print(r.json(indent=2))

    The endpoint's response model is the same as ``verify_signature()`` sans the ``guild``, ``channel``, and ``author``
    keys (IDs are still present).

.. autofunction:: aliasing.api.functions.typeof

.. autofunction:: aliasing.evaluators.ScriptingEvaluator.using

.. autofunction:: aliasing.evaluators.ScriptingEvaluator.uvar_exists(name)

.. autofunction:: aliasing.api.functions.vroll(rollStr, multiply=1, add=0)

.. autofunction:: aliasing.api.functions.parse_coins(args: str) -> dict

Variable Scopes
---------------

In addition to Python's normal variable scoping rules, Avrae introduces 4 new scopes in the form of character variables,
user variables, server variables, and global variables. The intended purpose and binding rules of each are detailed
below.

+---------------+------+-------+----------+------------+-------------------+
| Variable Type | Read | Write | Binding  | Scope      | Who               |
+===============+======+=======+==========+============+===================+
| Cvar          | Yes  | Yes   | Implicit | Character  | User              |
+---------------+------+-------+----------+------------+-------------------+
| Uvar          | Yes  | Yes   | Implicit | User       | User              |
+---------------+------+-------+----------+------------+-------------------+
| Svar          | Yes  | No    | Explicit | Server     | Anyone on server  |
+---------------+------+-------+----------+------------+-------------------+
| Gvar          | Yes  | No    | Explicit | Everywhere | Anyone            |
+---------------+------+-------+----------+------------+-------------------+
| Init Metadata | Yes  | Yes   | Explicit | Initiative | Anyone in channel |
+---------------+------+-------+----------+------------+-------------------+

Character Variables
^^^^^^^^^^^^^^^^^^^
*aka cvars*

Character variables are variables bound to a character. These are usually used to set character-specific defaults
or options for aliases and snippets (e.g. a character's familiar type/name). When running an alias or snippet, cvars are
*implicitly* bound as local variables in the runtime at the runtime's instantiation.

Cvars can be written or deleted in Draconic using :meth:`.AliasCharacter.set_cvar` and
:meth:`.AliasCharacter.delete_cvar`, respectively.

All characters contain some built-in character variables (see :ref:`cvar-table`). These cannot be overwritten.

User Variables
^^^^^^^^^^^^^^
*aka uvars*

User variables are bound per Discord user, and will go with you regardless of what server or character you are on.
These variables are usually used for user-specific options (e.g. a user's timezone, favorite color, etc.). When running
an alias or snippet, uvars are *implicitly* bound as local variables in the runtime at the runtime's instantiation. If a
cvar and uvar have the same name, the cvar takes priority.

Uvars can be written or deleted in Draconic using :meth:`~aliasing.evaluators.ScriptingEvaluator.set_uvar` or
:meth:`~aliasing.evaluators.ScriptingEvaluator.delete_uvar`, respectively.

Server Variables
^^^^^^^^^^^^^^^^
*aka svars*

Server variables are named variables bound per Discord server, and can only be accessed in the Discord server they are
bound in. These variables are usually used for server-specific options for server aliases (e.g. stat rolling methods,
server calendar, etc.). Unlike cvars and uvars, svars must be *explicitly* retrieved in an alias by calling
:meth:`~aliasing.evaluators.ScriptingEvaluator.get_svar`. Svars can be listed and read by anyone on the server, so be
careful what data you store!

Svars can only be written or deleted using ``!svar <name> <value>`` and ``!svar delete <name>``, respectively. These
commands can only be issued by a member who has Administrator Discord permissions or a Discord role named "Server
Aliaser" or "Dragonspeaker".

Global Variables
^^^^^^^^^^^^^^^^
*aka gvars*

Global variables are uniquely named variables that are accessible by anyone, anywhere in Avrae. These variables are
usually used for storing large amounts of read-only data (e.g. an alias' help message, a JSON file containing cards,
etc.). These variables are automatically assigned a unique name on creation (in the form of a 36 character UUID), and
must be *explicitly* retrieved in an alias by calling :meth:`~aliasing.evaluators.ScriptingEvaluator.get_gvar`.
Gvars can be read by anyone, so be careful what data you store!

Gvars can only be created using ``!gvar create <value>``, and by default can only be edited by its creator. See
``!help gvar`` for more information.

Honorable Mention: Initiative Metadata
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Initiative metadata is a form of key-value pair storage attached to an ongoing initiative in a given channel. This
storage is usually used for storing a medium-sized amount of programmatic information about an ongoing initiative (e.g.
an alias' metadata on each combatant).

Metadata can be created, retrieved, and deleted using the :meth:`.SimpleCombat.set_metadata`,
:meth:`.SimpleCombat.get_metadata`, and :meth:`.SimpleCombat.delete_metadata` methods, respectively.

.. _using-imports:

Using Imports
-------------

Imports are a way for alias authors to share common code across multiple aliases, provide common libraries of code for
other authors to write code compatible with your alias, and more!

If you already have the address of a module to import, use :meth:`~aliasing.evaluators.ScriptingEvaluator.using` at the
top of your code block in order to import the module into your namespace. For example:

.. code-block:: text

    !alias hello-world echo <drac2>
    using(
        hello="50943a96-381b-427e-adb9-eea8ebf61f27"
    )
    return hello.hello()
    </drac2>

Use ``!gvar 50943a96-381b-427e-adb9-eea8ebf61f27`` to take a peek at the ``hello`` module!

You can also import multiple modules in the same expression:

.. code-block:: text

    !alias hello-world echo <drac2>
    using(
        hello="50943a96-381b-427e-adb9-eea8ebf61f27",
        hello_utils="0bbddb9f-c86f-4af8-9e04-1964425b1554"
    )
    return f"{hello.hello('you')}\n{hello_utils.hello_to_my_character()}"
    </drac2>

The ``hello_utils`` module (``!gvar 0bbddb9f-c86f-4af8-9e04-1964425b1554``) also demonstrates how modules can import
other modules!

Each imported module is bound to a namespace that contains each of the names (constants, functions, etc) defined in the
module. For example, the ``hello`` module (``50943a96-381b-427e-adb9-eea8ebf61f27``) defines the ``HELLO_WORLD``
constant and ``hello()`` function, so a consumer could access these with ``hello.HELLO_WORLD`` and ``hello.hello()``,
respectively.

.. warning::

    Only import modules from trusted sources! The entire contents of an imported module is executed once upon
    import, and can do bad things like delete all of your variables.

    All gvar modules are open-source by default, so it is encouraged to view the imported module using ``!gvar``.

.. note::

    Modules do not have access to the argument parsing special syntax (i.e. ``&ARGS&``, ``%1%``, etc), and the variables
    listed in the Cvar Table are not implicitly bound in a module's execution.

Writing Modules
^^^^^^^^^^^^^^^

Modules are easy to publish and update! Simply create a gvar that contains valid Draconic code (**without** wrapping it
in any delimiters such as ``<drac2>``).

We encourage modules to follow the following format to make them easy to read:

.. code-block:: python

    # recommended_module_name
    # This is a short description about what the module does.
    #
    # SOME_CONSTANT: some documentation about what this constant is
    # some_function(show, the, args): some short documentation about what this function does
    #     and how to call it
    #     wow, this is long! use indentation if you need multiple lines
    #     but otherwise longer documentation should go in the function's """docstring"""

    SOME_CONSTANT = 3.141592

    def some_function(show, the, args):
        """Here is where the longer documentation about the function can go."""
        pass

Use ``!gvar 50943a96-381b-427e-adb9-eea8ebf61f27`` and ``!gvar 0bbddb9f-c86f-4af8-9e04-1964425b1554`` to view
the ``hello`` and ``hello_utils`` example modules used above for an example!

.. note::

    Because all gvars are public to anyone who knows the address, modules are open-source by default.

Catching Exceptions
-------------------

Draconic supports a modified version of Python's exception handling ("try-except") syntax, the most significant
difference being that exceptions must be caught explicitly by passing the *exact name* of the exception type to the
``except`` clause as a string or tuple of strings. A bare ``except`` may also be used to catch any exception in the
``try`` block.

For example, to cast an arbitrary string to an integer and catch errors raised by ``int()``:

.. code-block:: text

    !test <drac2>
    some_string = "123"
    try:
        return int(some_string)
    except ("ValueError", "TypeError"):
        return "I couldn't parse an int!"
    </drac2>

.. note::

    Unlike Python, only the exact exception type given by a string will be matched, without subclass checking.

Draconic ``try`` statements also support ``else`` and ``finally`` blocks, similar to Python.

See Also
--------

Draconic's syntax is very similar to Python. Other Python features supported in Draconic include:

* `Ternary Operators <https://stackoverflow.com/a/394814>`_ (``x if a else y``)
* `Slicing <https://stackoverflow.com/a/663175>`_ (``"Hello world!"[2:4]``)
* `Operators <https://docs.python.org/3/reference/expressions.html#unary-arithmetic-and-bitwise-operations>`_ (``2 + 2``, ``"foo" in "foobar"``, etc)
* `Assignments <https://docs.python.org/3/reference/simple_stmts.html#assignment-statements>`_ (``a = 15``)
* `List Comprehensions <https://docs.python.org/3/tutorial/datastructures.html#list-comprehensions>`_
* `Functions <https://docs.python.org/3/tutorial/controlflow.html#defining-functions>`_
* `Lambda Expressions <https://docs.python.org/3/tutorial/controlflow.html#lambda-expressions>`_
* `Argument Unpacking <https://docs.python.org/3/tutorial/controlflow.html#unpacking-argument-lists>`_

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

    .. attribute:: groups

        A list of all :class:`~aliasing.api.combat.SimpleGroup` in combat.

    .. attribute:: me

        The :class:`~aliasing.api.combat.SimpleCombatant` representing the active character in combat, or ``None``
        if the character is not in the combat.

    .. attribute:: name

        The name of the combat (:class:`str`), or ``None`` if no custom name is set.

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

    .. attribute:: type

        The type of the object (``"combatant"``), to determine whether this is a group or not.

        :type: str


SimpleGroup
^^^^^^^^^^^

.. autoclass:: aliasing.api.combat.SimpleGroup()
    :members:

    .. attribute:: combatants

        A list of all :class:`~aliasing.api.combat.SimpleCombatant` in this group.

        :type: list of :class:`~aliasing.api.combat.SimpleCombatant`

    .. attribute:: type

        The type of the object (``"group"``), to determine whether this is a group or not.

        :type: str

    .. attribute:: init

        What the group rolled for initiative.

        :type: int

SimpleEffect
^^^^^^^^^^^^

.. autoclass:: aliasing.api.combat.SimpleEffect()
    :members:

    .. attribute:: combatant_name

        The name of the combatant this effect is on.

        :type: str

    .. attribute:: conc

        Whether the effect requires concentration.

        :type: bool

    .. attribute:: desc

        The description of the effect.

        :type: str

    .. attribute:: duration

        The initial duration of the effect, in rounds. ``None`` if the effect has indefinite duration.

        :type: int or None

    .. attribute:: effect

        The applied passive effects of the object:

        .. code-block:: text

            {
                attack_advantage: int
                to_hit_bonus: str
                damage_bonus: str
                magical_damage: bool
                silvered_damage: bool
                resistances: List[Resistance]
                immunities: List[Resistance]
                vulnerabilities: List[Resistance]
                ignored_resistances: List[Resistance]
                ac_value: int
                ac_bonus: int
                max_hp_value: int
                max_hp_bonus: int
                save_bonus: str
                save_adv: List[str]
                save_dis: List[str]
                check_bonus: str
            }

        Each attribute in the dictionary is optional and may not be present.

        :type: dict

    .. attribute:: name

        The name of the effect.

        :type: str

    .. attribute:: remaining

        The remaining duration of the effect, in rounds. ``None`` if the effect has indefinite duration.

        :type: int or None

    .. attribute:: ticks_on_end

        Whether the effect duration ticks at the end of the combatant's turn or at the start.

        :type: bool

    .. attribute:: attacks

        A list of the attacks granted by the effect.

        :type: list

    .. attribute:: buttons

        A list of the buttons granted by the effect.

        :type: list

.. _ieffectargs:

Initiative Effect Args
^^^^^^^^^^^^^^^^^^^^^^

The *passive_effects*, *attacks*, and *buttons* arguments to ``SimpleCombatant.add_effect()`` should be a dict/list that
follows the schema below, respectively.

Some examples are provided below.

.. code-block:: python

    class PassiveEffects:
        attack_advantage: Optional[enums.AdvantageType]
        to_hit_bonus: Optional[str255]
        damage_bonus: Optional[str255]
        magical_damage: Optional[bool]
        silvered_damage: Optional[bool]
        resistances: Optional[List[str255]]
        immunities: Optional[List[str255]]
        vulnerabilities: Optional[List[str255]]
        ignored_resistances: Optional[List[str255]]
        ac_value: Optional[int]
        ac_bonus: Optional[int]
        max_hp_value: Optional[int]
        max_hp_bonus: Optional[int]
        save_bonus: Optional[str255]
        save_adv: Optional[Set[str]]
        save_dis: Optional[Set[str]]
        check_bonus: Optional[str255]
        check_adv: Optional[Set[str]]
        check_dis: Optional[Set[str]]

    class AttackInteraction:
        attack: AttackModel  # this can be any attack built on the Avrae Dashboard
        override_default_dc: Optional[int]
        override_default_attack_bonus: Optional[int]
        override_default_casting_mod: Optional[int]

    class ButtonInteraction:
        automation: Automation  # this can be any automation built on the Avrae Dashboard
        label: str
        verb: Optional[str255]
        style: Optional[conint(ge=1, le=4)]
        override_default_dc: Optional[int]
        override_default_attack_bonus: Optional[int]
        override_default_casting_mod: Optional[int]

**Example: Passive Effects**

Also see :ref:`passiveeffects` for more information.

.. code-block:: python

    combatant.add_effect(
        "Some Magical Effect",
        passive_effects={
            "attack_advantage": 1,
            "damage_bonus": "1d4 [fire]",
            "magical_damage": True,
            "resistances": ["fire", "nonmagical slashing"],
            "ac_bonus": 2,
            "save_adv": ["dexterity"]
        }
    )

**Example: Granting Attacks**

Also see :ref:`attackinteraction` for more information. Note that the Automation schema differs slightly from the
aliasing API.

.. code-block:: python

    combatant.add_effect(
        "Some Magical Effect",
        attacks=[{
            "attack": {
                "_v": 2,
                "name": "Magical Attack",
                "verb": "shows off the power of",
                "automation": [
                    {
                        "type": "target",
                        "target": "each",
                        "effects": [
                            {
                                "type": "attack",
                                "hit": [
                                    {
                                        "type": "damage",
                                        "damage": "1d10[fire]"
                                    }
                                ],
                                "miss": []
                            }
                        ]
                    }
                ]
            }
        }]
    )

**Example: Granting Buttons**

Also see :ref:`buttoninteraction` for more information. Note that the Automation schema differs slightly from the
aliasing API.

.. code-block:: python

    combatant.add_effect(
        "Some Magical Effect",
        buttons=[{
            "label": "On Fire",
            "verb": "is burning",
            "style": 4,
            "automation": [
                {
                    "type": "target",
                    "target": "self",
                    "effects": [
                        {
                            "type": "damage",
                            "damage": "1d6 [fire]"
                        }
                    ]
                }
            ]
        }]
    )

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

AliasCategory
^^^^^^^^^^^^^

.. autoclass:: aliasing.api.context.AliasCategory()
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

AliasAction
^^^^^^^^^^^

.. autoclass:: aliasing.api.character.AliasAction()
    :members:

AliasCoinpurse
^^^^^^^^^^^^^^

.. autoclass:: aliasing.api.character.AliasCoinpurse()
    :members:

    .. attribute:: str(AliasCoinpurse)

        Returns a string representation of the entire coinpurse. If the character setting for Compact Coins is enabled, this will only return your float gold, otherwise will return all 5 coin types.

        :type: str

    .. attribute:: pp
        gp
        ep
        sp
        cp

        The value of the given coin type.

        :type: int

    .. attribute:: AliasCoinpurse[cointype]

        Gets the value of the given coin type.

        :type: int

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
