DM Combat Guide
===========================

.. note::
   arguments surrounded like ``<this>`` are required, and arguments in ``[brackets]`` are optional. Put quotes around arguments that contain spaces.

.. note::
   This guide will move *roughly* in chronological order, meaning commands near the top should be run first.

Starting Combat
-----------------

First, combat must be started in a channel.  All commands should be posted in the **same** Discord channel that combat was started in.  Combat can be started by using the following command. ::


   !i begin

Avrae will output the summary message and pin it, then a quick reminder on how to add yourself to combat (for a player).

Adding Monsters
^^^^^^^^^^^^^^^^^^^^^^^^
After combat is started, you will need to add monsters and combatants. You can add official monsters with this command. ::

   !i madd <monster name> [arguments]

Common arguments include:
    * ``-n <number of monsters>`` (ex. ``-n 5`` adds 5 creatures)
    * ``-name <monster name scheme>`` (ex. ``-name "Orc#" -n 2`` adds Orc1 and Orc2)
    * ``-group <group name>`` (makes all creatures in the group act on the same initiative)
    * ``-rollhp`` (rolls for a creature's HP)
    * ``-hp <hp>`` (overrides a creature's initial HP)
    * ``-ac <ac>`` (overrides a creature's initial AC)

Remember to surround any arguments with spaces in them with quotes!

Adding Other Combatants
^^^^^^^^^^^^^^^^^^^^^^^
If you're adding a combatant without a sheet, you can add a generic combatant with::

   !i add <initiative modifier> <name> [arguments]

Examples of combatants that might need to be added like this are:
    * an object
    * a lair action
    * a homebrew monster that hasn't been imported using the Bestiary system

Hiding Stats
^^^^^^^^^^^^

As a DM, you probably want to hide certain stats from your players. By default, any monsters added with ``!i madd``
will have their stats hidden, but you must hide generic combatants' stats yourself::

   !i add <initiative modifier> <name> -h

This will hide HP and AC.

Examples
^^^^^^^^

.. code-block:: diff

    !i madd "young red dragon"
    # adds a Young Red Dragon to combat with stats hidden

    !i madd kobold -n 5 -group Kobolds -rollhp
    # adds 5 Kobolds, named KO1-KO5, with rolled HP, to a group named Kobolds

    !i add 20 "Lair Action" -p
    # adds a Lair Action on initiative 20

    !i add 0 Longboat -ac 15 -hp 300
    # adds an object with 300 HP, an AC of 15, and +0 initiative

Running Combat
-------------------

Once you have finished setting up combat and your players have joined, this command will go to the next turn in the order and combat will begin. ::

   !i next

On a player's turn, it's up to the player to run commands to take their actions. See the :ref:`pc_combat`.

When a monster's turn comes up, the most common actions to take are attacking or casting a spell.

Attacking
^^^^^^^^^
To attack another combatant, use this command::

   !i attack <attack name> -t <target name> [arguments]

This uses the attack list of whatever combatant's turn it is. To see a list of available attacks, run ``!i attack list``.

As many targets as necessary may be provided by adding more ``-t <target name>``, in the case of attacks that target multiple creatures
(such as a breath weapon).

.. note::
    If a monster makes an Attack of Opportunity, the syntax is ``!i aoo <combatant name> <attack name> -t <target name> [arguments]``.

    Alternatively, you may use ``!ma <monster name> <attack name> -t <target name> [arguments]``.

To see all valid arguments, refer to the ``!attack`` and ``!ma`` documentation.

Casting a Spell
^^^^^^^^^^^^^^^
To cast a spell, use this command::

   !i cast <spell name> [-t <target name>] [arguments]

This uses the spell list of whatever combatant's turn it is.

As many targets as necessary may be provided by adding more ``-t <target name>``, in the case of spells that target multiple creatures
(such as Fireball).

.. note::
    If a monster casts as a reaction, the syntax is ``!i rc <combatant name> <spell name> [-t <target name>] [arguments]``.

    Alternatively, you may use ``!mcast <monster name> <spell name> [-t <target name>] [arguments]``, although this will
    not track the spell slots for the monster in initiative.

To see all valid arguments, refer to the ``!cast`` and ``!mcast`` documentation.

Examples
^^^^^^^^

.. code-block:: diff

    !i attack dagger -t Caitlyn -rr 2
    # attacks a player named Caitlyn with a dagger twice

    !i attack longbow -t Em adv
    # attacks a player named Em with a longbow at advantage

    !i attack "fire breath" -t Ara -t Padellis
    # makes Ara and Padellis make saves against a breath weapon

    !i cast bless -t KO1 -t KO2
    # casts Bless on two kobolds, and attaches an effect to automatically add 1d4

    !i cast "fire bolt" -t Qal
    # casts Fire Bolt at Qal


Helper Commands
------------------
These commands should help manually change the state of combat.

HP
^^
To modify a combatant's HP::

    !i hp <combatant name> <value>

To set a combatant's HP::

    !i hp <combatant name> set <value>

To set a combatant's maximum HP::

    !i hp <combatant name> max <value>

Examples
""""""""

.. code-block:: diff

    !i hp ko1 -5
    # deals 5 damage to KO1

    !i hp Licia set 100
    # sets Licia's HP to 100

    !i hp Taren max 44
    # sets Taren's max HP to 44

    !i hp yo1 +1d4+1
    # heals YO1 for 1d4+1 HP

Attributes
^^^^^^^^^^
To modify an attribute of a combatant::

   !i opt <combatant name> <arguments>

Most common arguments:
    * ``-ac <AC>`` (sets AC to new value)
    * ``-resist/immune/vuln <damage type>`` (gives resistance, immunity, or vulnerability or specified type)
    * ``-h`` (toggles whether combatants AC and HP are hidden.)

Effects
^^^^^^^
Effects can be used to track status effects that last a certain duration and modify a combatant's attacks, resistances,
AC, or other attributes. For a full list of attributes, see ``!help i effect``.

Some attacks and spells, such as Bless, will automatically add appropriate effects to their targets.

To add effects to combatants::

   !i effect <target name> <effect name> [arguments]

Most common arguments:
    * ``-dur <duration>`` (sets the duration of the effect, in rounds)
    * ``-b <bonus>`` (adds a bonus to all of the target's attack to-hits)
    * ``-d <damage>`` (adds bonus damage to all of the target's attacks)
    * ``-resist/immune/vuln <type>`` (sets resistance to a damage type)

To remove Effects from combatants::

   !i re <combatant name> [effect name]

Examples
""""""""

.. code-block:: diff

    !i effect Jozu Rage -dur 10 -d 2
    # adds a Rage effect to Jozu that adds 2 damage to their attacks and lasts 10 rounds

    !i effect Flore Bless -dur 10 -b 1d4 -sb 1d4
    # adds a Bless effect to Flore that adds 1d4 to their attacks and saves, that lasts 10 rounds

    !i effect Padellis "Mage Armor" -ac +3
    # adds a Mage Armor effect to Padellis that adds 3 to their AC

    !i effect Greg "Fire Shield" -resist fire -dur 1
    # adds an effect to Greg that makes him resist fire until next round

Removing from Combat
---------------------

To remove someone from combat::

   !i remove <combatant name>

Ending Combat
---------------------

To end combat (Avrae will ask if you wish to end combat, reply "yes")::

   !i end

After combat ends, Avrae will send the person who ended it a summary of the combat.
