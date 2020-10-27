Automation Reference
====================

This page details the structure of Avrae's Automation system, the backbone behind custom spells and attacks.

Basic Structure
---------------
An automation run is made up of a list of *effects*. See below for what each effect does.

All Automation runs provide the following variables:

- ``caster`` (:class:`~aliasing.api.statblock.AliasStatBlock`) The character, combatant, or monster who is running the automation.
- ``targets`` (list of :class:`~aliasing.api.statblock.AliasStatBlock`) A list of combatants targeted by this automation (i.e. the ``-t`` argument).

Target
------
.. code-block:: typescript

    {
        type: "target";
        target: "all"|"each"|int|"self";
        effects: Effect[];
    }

A Target effect should only show up as a top-level effect.
It designates what creatures to affect.

.. attribute:: target

    - ``"all"``: Affects all targets (usually save spells)
    - ``"each"``: Affects each target (usually attack spells)
    - ``int``: Affects the Nth target (1-indexed)
    - ``"self"``: Affects the caster

.. attribute:: effects

    A list of effects that each targeted creature will be subject to.

**Variables**

- ``target`` (:class:`~aliasing.api.statblock.AliasStatBlock`) The current target.
- ``targetIteration`` (:class:`int`) If running multiple iterations (i.e. ``-rr``), the current iteration.

Attack
------
.. code-block:: typescript

    {
        type: "attack";
        hit: Effect[];
        miss: Effect[];
        attackBonus?: IntExpression;
    }

An Attack effect makes an attack roll against a targeted creature.
It must be inside a Target effect.

.. attribute:: hit

     A list of effects to execute on a hit.

.. attribute:: miss

     A list of effects to execute on a miss.

.. attribute:: attackBonus

     *optional* - An IntExpression that details what attack bonus to use (defaults to caster's spell attack mod).

**Variables**

- ``lastAttackDidHit`` (:class:`bool`) Whether the attack hit.
- ``lastAttackDidCrit`` (:class:`bool`) If the attack hit, whether it crit.

Save
----
.. code-block:: typescript

    {
        type: "save";
        stat: "str"|"dex"|"con"|"int"|"wis"|"cha";
        fail: Effect[];
        success: Effect[];
        dc?: IntExpression;
    }

A Save effect forces a targeted creature to make a saving throw.
It must be inside a Target effect.

.. attribute:: stat

     The type of saving throw.

.. attribute:: fail

     A list of effects to execute on a failed save.

.. attribute:: success

     A list of effects to execute on a successful save.

.. attribute:: dc

     *optional* - An IntExpression that details what DC to use (defaults to caster's spell DC).

**Variables**

- ``lastSaveDidPass`` (:class:`bool`) Whether the target passed the save.

Damage
------
.. code-block:: typescript

    {
        type: "damage";
        damage: AnnotatedString;
        overheal?: boolean;
        higher?: {int: string};
        cantripScale?: boolean;
    }

Deals damage to a targeted creature. It must be inside a Target effect.

.. attribute:: damage

     How much damage to deal. Can use variables defined in a Meta tag.

.. attribute:: overheal

    .. versionadded:: 1.4.1

     *optional* - Whether this damage should allow a target to exceed its hit point maximum.

.. attribute:: higher

     *optional* - How much to add to the damage when a spell is cast at a certain level.

.. attribute:: cantripScale

     *optional* - Whether this roll should scale like a cantrip.

**Variables**

- ``lastDamage`` (:class:`int`) The amount of damage dealt.

TempHP
------
.. code-block:: typescript

    {
        type: "temphp";
        amount: AnnotatedString;
        higher?: {int: string};
        cantripScale?: boolean;
    }

Sets the target's THP. It must be inside a Target effect.

.. attribute:: amount

     How much temp HP the target should have. Can use variables defined in a Meta tag.

.. attribute:: higher

     *optional* - How much to add to the THP when a spell is cast at a certain level.

.. attribute:: cantripScale

     *optional* - Whether this roll should scale like a cantrip.

**Variables**

- ``lastTempHp`` (:class:`int`) The amount of temp HP granted.

IEffect
-------
.. code-block:: typescript

    {
        type: "ieffect";
        name: string;
        duration: int | IntExpression;
        effects: AnnotatedString;
        end?: boolean;
    }

Adds an InitTracker Effect to a targeted creature, if the automation target is in combat.
It must be inside a Target effect.

.. attribute:: name

     The name of the effect to add.

.. attribute:: duration

     The duration of the effect, in rounds of combat. Can use variables defined in a Meta tag.

.. attribute:: effects

     The effects to add (see :func:`~cogs5e.funcs.scripting.combat.SimpleCombatant.add_effect()`).
     Can use variables defined in a Meta tag.

.. attribute:: end

     *optional* - Whether the effect timer should tick on the end of the turn, rather than start.

Roll
----
.. code-block:: typescript

    {
        type: "roll";
        dice: AnnotatedString;
        name: string;
        higher?: {int: string};
        cantripScale?: boolean;
        hidden?: boolean;
    }

Rolls some dice and saves the result in a variable. Displays the roll and its name in a Meta field, unless
``hidden`` is ``true``.

.. attribute:: dice

     An AnnotatedString detailing what dice to roll.

.. attribute:: name

     What to save the result as.

.. attribute:: higher

     *optional* - How much to add to the roll when a spell is cast at a certain level.

.. attribute:: cantripScale

     *optional* - Whether this roll should scale like a cantrip.

.. attribute:: hidden

     *optional* - If ``true``, won't display the roll in the Meta field, or apply any bonuses from -d.

**Variables**

- ``lastRoll`` (:class:`int`) The total of the roll.

Text
----
.. code-block:: typescript

    {
        type: "text";
        text: AnnotatedString;
    }

Outputs a short amount of text in the resulting embed.

.. attribute:: text

    An AnnotatedString detailing the text to display.

AnnotatedString
---------------
An AnnotatedString is a string that can access saved variables.
To access a variable, surround the name in brackets (e.g. ``{damage}``).
Available variables include:

- implicit variables from Effects (see relevant effect for a list of variables it provides)
- any defined in a ``Roll`` or ``Set Variable`` effect
- all variables from the :ref:`cvar-table`

This will replace the bracketed portion with the value of the meta variable.

To perform math inside an AnnotatedString, surround the formula with two curly braces
(e.g. ``{{floor(dexterityMod+spell)}}``).

IntExpression
-------------
An IntExpression is similar to an AnnotatedString in its ability to use variables and functions. However, it has the
following differences:

- Curly braces around the expression are not required
- An IntExpression can only contain one expression
- The result of an IntExpression must be an integer.

These are valid IntExpressions:

- ``8 + proficiencyBonus + dexterityMod``
- ``12``
- ``floor(level / 2)``

These are *not* valid IntExpressions:

- ``1d8``
- ``DC {8 + proficiencyBonus + dexterityMod}``


Examples
--------
A normal attack:

.. code-block:: json

    [
      {
        "type": "target",
        "target": "each",
        "effects": [
          {
            "type": "attack",
            "attackBonus": "dexterityMod + proficiencyBonus",
            "hit": [
              {
                "type": "damage",
                "damage": "1d10[piercing]"
              }
            ],
            "miss": []
          }
        ]
      }
    ]

A spell that requires a Dexterity save for half damage:

.. code-block:: json

    [
      {
        "type": "roll",
        "dice": "8d6[fire]",
        "name": "damage",
        "higher": {
          "4": "1d6[fire]",
          "5": "2d6[fire]",
          "6": "3d6[fire]",
          "7": "4d6[fire]",
          "8": "5d6[fire]",
          "9": "6d6[fire]"
        }
      },
      {
        "type": "target",
        "target": "all",
        "effects": [
          {
            "type": "save",
            "stat": "dex",
            "fail": [
              {
                "type": "damage",
                "damage": "{damage}"
              }
            ],
            "success": [
              {
                "type": "damage",
                "damage": "({damage})/2"
              }
            ]
          }
        ]
      },
      {
        "type": "text",
        "text": "Each creature in a 20-foot radius must make a Dexterity saving throw. A target takes 8d6 fire damage on a failed save, or half as much damage on a successful one."
      }
    ]

An attack from a poisoned blade:

.. code-block:: json

    [
      {
        "type": "target",
        "target": "each",
        "effects": [
          {
            "type": "attack",
            "attackBonus": "strengthMod + proficiencyBonus",
            "hit": [
              {
                "type": "damage",
                "damage": "1d10[piercing]"
              },
              {
                "type": "save",
                "stat": "con",
                "dc": "12",
                "fail": [
                  {
                    "type": "damage",
                    "damage": "1d6[poison]"
                  }
                ],
                "success": []
              }
            ],
            "miss": []
          }
        ]
      },
      {
        "type": "text",
        "text": "On a hit, a target must make a DC 12 Constitution saving throw or take 1d6 poison damage."
      }
    ]
