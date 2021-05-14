Automation Reference
====================

This page details the structure of Avrae's Automation system, the backbone behind custom spells and attacks.

Basic Structure
---------------
An automation run is made up of a list of *effects*. See below for what each effect does.

All Automation runs provide the following variables:

- ``caster`` (:class:`~aliasing.api.statblock.AliasStatBlock`) The character, combatant, or monster who is running the automation.
- ``targets`` (list of :class:`~aliasing.api.statblock.AliasStatBlock`, :class:`str`, or None) A list of combatants targeted by this automation (i.e. the ``-t`` argument).

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
- ``targetIteration`` (:class:`int`) If running multiple iterations (i.e. ``-rr``), the current iteration (1-indexed).

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
- ``lastAttackRollTotal`` (:class:`int`) The result of the last to-hit roll (0 if no roll was made).
- ``lastAttackNaturalRoll`` (:class:`int`) The natural roll of the last to-hit roll (e.g. `10` in `1d20 (10) + 5 = 15`;
  0 if no roll was made).

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
- ``lastSaveDC`` (:class:`int`) The DC of the last save roll.
- ``lastSaveRollTotal`` (:class:`int`) The result of the last save roll (0 if no roll was made).
- ``lastSaveNaturalRoll`` (:class:`int`) The natural roll of the last save roll (e.g. `10` in `1d20 (10) + 5 = 15`;
  0 if no roll was made).

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
        conc?: boolean;
        desc?: AnnotatedString;
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

.. attribute:: conc

     *optional* - Whether the effect requires concentration.

.. attribute:: desc

     *optional* - The description of the effect (displays on combatant's turn).

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

Set Variable
------------
.. versionadded:: 2.7.0

.. code-block:: typescript

    {
        type: "variable";
        name: string;
        value: IntExpression;
        higher?: {int: IntExpression};
        onError?: IntExpression;
    }

Saves the result of an ``IntExpression`` to a variable without displaying anything.

.. attribute:: name

     The name of the variable to save.

.. attribute:: value

     The value to set the variable to.

.. attribute:: higher

     *optional* - What to set the variable to instead when a spell is cast at a higher level.

.. attribute:: onError

     *optional* - If provided, what to set the variable to if the normal value would throw an error.

Condition
---------
.. versionadded:: 2.7.0

.. code-block:: typescript

    {
        type: "condition";
        condition: IntExpression;
        onTrue: Effect[];
        onFalse: Effect[];
        errorBehaviour?: "true" | "false" | "both" | "neither" | "raise";
    }

Run certain effects if a special condition is met, or other effects otherwise.

.. attribute:: condition

     The condition to check.

.. attribute:: onTrue

     The effects to run if ``condition`` is ``True`` or any non-zero value.

.. attribute:: onFalse

     The effects to run if ``condition`` is ``False`` or ``0``.

.. attribute:: errorBehaviour

     How to behave if the condition raises an error:

    - ``"true"``: Run the ``onTrue`` effects.
    - ``"false"``: Run the ``onFalse`` effects. (*default*)
    - ``"both"``: Run both the ``onTrue`` and ``onFalse`` effects, in that order.
    - ``"neither"``: Skip this effect.
    - ``"raise"``: Raise the error and halt execution.

Use Counter
-----------
.. versionadded:: 2.10.0

.. code-block:: typescript

    {
        type: "counter";
        counter: string | SpellSlotReference | AbilityReference;
        amount: IntExpression;
        allowOverflow?: boolean;
        errorBehaviour?: null | "warn" | "raise";
    }

Uses a number of charges of the given counter, and displays the remaining amount and delta.

.. note::
    Regardless of the current target, this effect will always use the *caster's* counter/spell slots!

.. attribute:: counter

    The name of the counter to use (case-sensitive, full match only), or a reference to a spell slot
    (see :ref:`SpellSlotReference`).

.. attribute:: amount

     The number of charges to use. If negative, will add charges instead of using them.

.. attribute:: allowOverflow

     *optional, default False* - If False, attempting to overflow/underflow a counter (i.e. use more charges than
     available or add charges exceeding max) will error instead of clipping to bounds.

.. attribute:: errorBehaviour

     *optional, default "warn"* - How to behave if modifying the counter raises an error:

    - ``null``: All errors are silently consumed.
    - ``"warn"``: Automation will continue to run, and any errors will appear in the output. (*default*)
    - ``"raise"``: Raise the error and halt execution.

    Some, but not all, possible error conditions are:

    - The target does not have counters (e.g. they are a monster)
    - The counter does not exist
    - ``allowOverflow`` is false and the new value is out of bounds

**Variables**

- ``lastCounterName`` (:class:`str`) The name of the last used counter. If it was a spell slot, the level of the slot (safe to cast to int, i.e. ``int(lastCounterName)``). (``None`` on error).
- ``lastCounterRemaining`` (:class:`int`) The remaining charges of the last used counter (0 on error).
- ``lastCounterUsedAmount`` (:class:`int`) The amount of the counter successfully used.
- ``lastCounterRequestedAmount`` (:class:`int`) The amount of the counter requested to be used (i.e. the amount
  specified by automation or requested by ``-amt``, regardless of the presence of the ``-i`` arg).

.. _SpellSlotReference:

SpellSlotReference
^^^^^^^^^^^^^^^^^^

.. code-block:: typescript

    {
        slot: number;
    }

.. attribute:: slot

    The level of the spell slot to reference (``[1..9]``).

.. _AbilityReference:

AbilityReference
^^^^^^^^^^^^^^^^

.. code-block:: typescript

    {
        id: number;
        typeId: number;
    }

In most cases, an ``AbilityReference`` should not be constructed manually; use the Automation editor to select an
ability instead. A list of valid abilities can be retrieved from the API at ``/gamedata/limiteduse``.

.. note::
    The Automation Engine will make a best effort at discovering the appropriate counter to use for the
    given ability - in most cases this won't affect the chosen counter, but in some cases, it may
    lead to some unexpected behaviour. Some examples of counter discovery include:

    - Choosing ``Channel Divinity (Paladin)`` may discover a counter granted by the Cleric's Channel Divinity feature
    - Choosing ``Breath Weapon (Gold)`` may discover a counter for a breath weapon of a different color
    - Choosing ``Sorcery Points (Sorcerer)`` may discover a counter granted by the Metamagic Adept feat

.. attribute:: id

    The ID of the ability referenced.

.. attribute:: typeId

    The DDB entity type ID of the ability referenced.

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

Attack
^^^^^^

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

Save
^^^^

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

Attack & Save
^^^^^^^^^^^^^

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

Draining Attack
^^^^^^^^^^^^^^^

An attack that heals the caster for half the amount of damage dealt:

.. code-block:: json

    [
      {
        "type": "variable",
        "name": "lastDamage",
        "value": "0"
      },
      {
        "type": "target",
        "target": "each",
        "effects": [
          {
            "type": "attack",
            "attackBonus": "charismaMod + proficiencyBonus",
            "hit": [
              {
                "type": "damage",
                "damage": "3d6[necrotic]"
              }
            ],
            "miss": []
          }
        ]
      },
      {
        "type": "target",
        "target": "self",
        "effects": [
          {
            "type": "damage",
            "damage": "-{lastDamage}/2 [heal]"
          }
        ]
      },
      {
        "type": "text",
        "text": "On a hit, the target takes 3d6 necrotic damage, and you regain hit points equal to half the amount of necrotic damage dealt."
      }
    ]

Target Health-Based
^^^^^^^^^^^^^^^^^^^

A spell that does different amounts of damage based on whether or not the target is damaged:

.. code-block:: json

    [
      {
        "type": "target",
        "target": "each",
        "effects": [
          {
            "type": "save",
            "stat": "wis",
            "fail": [
              {
                "type": "condition",
                "condition": "target.hp < target.max_hp",
                "onTrue": [
                  {
                    "type": "damage",
                    "damage": "1d8 [necrotic]"
                  }
                ],
                "onFalse": [
                  {
                    "type": "damage",
                    "damage": "1d4 [necrotic]"
                  }
                ],
                "errorBehaviour": "both"
              }
            ],
            "success": []
          }
        ]
      },
      {
        "type": "text",
        "text": "The target must succeed on a Wisdom saving throw or take 1d4 necrotic damage. If the target is missing any of its hit points, it instead takes 1d8 necrotic damage."
      }
    ]

Area Draining Effect
^^^^^^^^^^^^^^^^^^^^

An effect that heals the caster for the total damage dealt:

.. code-block:: json

    [
      {
        "type": "variable",
        "name": "totalDamage",
        "value": "0"
      },
      {
        "type": "target",
        "target": "each",
        "effects": [
          {
            "type": "damage",
            "damage": "1d6 [necrotic]"
          },
          {
            "type": "variable",
            "name": "totalDamage",
            "value": "totalDamage + lastDamage"
          }
        ]
      },
      {
        "type": "target",
        "target": "self",
        "effects": [
          {
            "type": "damage",
            "damage": "-{totalDamage} [heal]"
          }
        ]
      },
      {
        "type": "text",
        "text": "Each creature within 10 feet of you takes 1d6 necrotic damage. You regain hit points equal to the sum of the necrotic damage dealt."
      }
    ]