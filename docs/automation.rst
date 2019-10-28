Automation Reference
====================

This page details the structure of Avrae's Automation system, the backbone behind custom spells and attacks.

Basic Structure
---------------
An automation run is made up of a list of *effects*.
See below for what each effect does.

.. code-block:: typescript

    {
        type: string;
        meta?: Effect[];
    }

All effects in an effect's ``meta`` will be executed before the
rest of the effect, if there is a meta.

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

Attack
------
.. code-block:: typescript

    {
        type: "attack";
        hit: Effect[];
        miss: Effect[];
        attackBonus?: AnnotatedString;
    }

An Attack effect makes an attack roll against a targeted creature.
It must be inside a Target effect.

.. attribute:: hit

     A list of effects to execute on a hit.

.. attribute:: miss

     A list of effects to execute on a miss.

.. attribute:: attackBonus

     *optional* - An AnnotatedString that details what attack bonus to use (defaults to caster's spell attack mod).


Save
----
.. code-block:: typescript

    {
        type: "save";
        stat: "str"|"dex"|"con"|"int"|"wis"|"cha";
        fail: Effect[];
        success: Effect[];
        dc?: AnnotatedString;
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

     *optional* - An AnnotatedString that details what DC to use (defaults to caster's spell DC).

Damage
------
.. code-block:: typescript

    {
        type: "damage";
        damage: AnnotatedString;
        higher?: {int: string};
        cantripScale?: boolean;
    }

Deals damage to a targeted creature. It must be inside a Target effect.

.. attribute:: damage

     How much damage to deal. Can use variables defined in a Meta tag.

.. attribute:: higher

     *optional* - How much to add to the damage when a spell is cast at a certain level.

.. attribute:: cantripScale

     *optional* - Whether this roll should scale like a cantrip.

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

IEffect
-------
.. code-block:: typescript

    {
        type: "ieffect";
        name: string;
        duration: int | AnnotatedString;
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
        dice: string;
        name: string;
        higher?: {int: string};
        cantripScale?: boolean;
        hidden?: boolean;
    }

Rolls some dice and saves the result. Should be in a Meta tag.

.. attribute:: dice

     What dice to roll.

.. attribute:: name

     What to save the result as.

.. attribute:: higher

     *optional* - How much to add to the roll when a spell is cast at a certain level.

.. attribute:: cantripScale

     *optional* - Whether this roll should scale like a cantrip.

.. attribute:: hidden

     *optional* - If ``true``, won't display the roll in the Meta field, or apply any bonuses from -d.

Text
----
.. code-block:: typescript

    {
        type: "text";
        text: string;
    }

Outputs a short amount of text in the resulting embed.

.. attribute:: text

    The text to display.

AnnotatedString
---------------
An AnnotatedString is a string that can access saved variables from a meta effect.
To access a variable, surround the name in brackets (e.g. ``{damage}``).
Available variables are any defined in Meta effects and the :ref:`cvar-table`.

This will replace the bracketed portion with the value of the meta variable (usually a roll).

To perform math inside an AnnotatedString, surround the formula with two curly braces
(e.g. ``{{floor(dexterityMod+spell)}}``).

Examples
--------
A normal attack:

.. code-block:: json

    [
      {
        "type": "target",
        "target": "each",
        "attackBonus": "{dexterityMod + proficiencyBonus}",
        "effects": [
          {
            "type": "attack",
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
        ],
        "meta": [
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
            "attackBonus": "{strengthMod + proficiencyBonus}",
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
