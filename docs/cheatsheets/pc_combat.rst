.. _pc_combat:

Player Combat Guide
===============================

This guide will help players join combat and use actions on their turns.

.. note::
    Arguments surrounded like ``<this>`` are required, and arguments in ``[brackets]`` are optional.
    Put quotes around arguments that contain spaces.

.. note::
    This guide will move *roughly* in chronological order, meaning commands near the top should be run first.

Joining Combat
---------------------------

To join combat, your DM must first start it. Once they have, proceed below to the following commands::

   !i join [arguments]

This will add your **active** character to combat.

Common arguments:
    * ``-h`` (hides AC/HP)
    * ``adv/dis`` (gives advantage/disadvantage on initiative roll)
    * ``-p <#>`` (places at prerolled init)

You are all setup and ready to go for when your turn comes!

Your Turn
-----------------------------

It's your turn! On your turn, the most common actions are either attacking or casting a spell:

Attacking
^^^^^^^^^
To attack, just use the same command you would use out of combat::

    !attack <attack name> -t <target name> [arguments]

To see a list of your character's attacks, use ``!attack list``.

As many targets as necessary may be provided by adding more ``-t <target name>``, in the case of attacks that target multiple creatures
(such as a breath weapon).

.. note::
    This command will work even when it is not your turn in combat.

    If you control a summoned creature, refer to the :ref:`dm_combat`.

To see all valid arguments, refer to the ``!attack`` documentation.

Casting a Spell
^^^^^^^^^^^^^^^
To cast a spell, it's also the same command in and out of combat::

   !cast <spell name> -t <target name> [arguments]

To see a list of your spells, use ``!spellbook``.

As many targets as necessary may be provided by adding more ``-t <target name>``, in the case of spells that target multiple creatures
(such as Fireball).

.. note::
    This command will work even when it is not your turn in combat.

    If you control a familiar or summoned creature, refer to the :ref:`dm_combat`.

To see all valid arguments, refer to the ``!cast`` documentation.

Examples
^^^^^^^^

.. code-block:: diff

    !attack dagger -t KO1 -rr 2
    # attacks KO1 with a dagger twice

    !attack longbow -t WY1 adv
    # attacks WY1 with a longbow at advantage

    !attack "fire breath" -t BA1 -t BA2
    # makes BA1 and BA2 make saves against a breath weapon

    !cast bless -t Rook -t Edmund -l 3
    # casts Bless at 3rd level on Rook and Edmund, and attaches an effect to automatically add 1d4

    !cast "fire bolt" -t BA3
    # casts Fire Bolt at BA3

Ending Your Turn
^^^^^^^^^^^^^^^^
When you're done with your turn, use this command to move to the next combatant::

    !i next

Helper Commands
-----------------------
These commands should help manually change the state of combat. For more reference, see the :ref:`dm_combat`.

HP
^^
To modify your character's HP::

    !g hp <value>

To set your character's HP::

    !g hp set <value>

To add temporary HP::

    !g thp <value>

To set your character's maximum HP (note the different base command)::

    !i hp <character name> max <value>

Examples
""""""""

.. code-block:: diff

    !g hp -5
    # deals 5 damage

    !g hp set 100
    # sets the character's HP to 100

    !g thp 11
    # gives the character 11 temp HP

    !g hp +2d4+2
    # heals for 2d4+2 HP