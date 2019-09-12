.. currentmodule:: cogs5e.funcs.scripting

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

.. autofunction:: cogs5e.funcs.scripting.functions.verbose_roll
