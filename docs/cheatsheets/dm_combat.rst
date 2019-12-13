DM Combat Guide
===========================



.. note::
   arguments surrounded like <this> are required, and arguments in [brackets] are optional. Put spaces around arguments that contain spaces.

.. note::
   This guide will move *roughly* in chronological order, meaning commands near the top should be run first.

Starting combat
-----------------

First, combat must be started in a channel.  All commands should be posted in the **Same** discord channel that combat was started in.  Combat cant be started by using the following command:

   !i begin

Avrae will output the summary message and pin it, then a quick reminder on how to add yourself to combat (for a player).

After combat is started, you will need to add monsters and combatants. you can add monsters that can be looked up with !monster with this command:

   !i madd <monster name> [arguments]

Common arguments include:
    -n <number of monsters> (ex. -n 5)
    -name <monster name scheme> (ex. -name "Orc#" -n 2) (adds Orc1 and Orc2)

Then to at them to combat use this command:

   !i add <initiative modifier> <name> [arguments]

   If you are adding a homebrew monster and haven't imported it with !bestiary, but still want to use the integrated tracker you have to use this command.

Hiding Stats
----------------

As a DM, you probably want to hide certain stats from your players.  !i has arguments for hiding stats as well:

   !i add <initiative modifier> <name> -h

This will Hide HP and AC.

Adding Homebrew Monsters
------------------------------

To add a homebrew monster that hasn't been imported with !bestiary, Use the following:

   !i add <initiative modifier> <name>

You can also set the HP and AC of the added monster.

   !i add <initiative modifier> <name> -hp <max HP> -ac <AC>

Running combat
-------------------

Once you have finished setting up combat and your players have joined this commant will go to the next turn in the order and combat will begin.

   !i next

On their turn players and monsters can use the following to do actions.

   !i attack <target name> <weapon name> [arguments]

.. note::
   If a player or monster makes an Attack of Opportunity they can use !i aoo <combatant name> <target name> <weapon name> [arguments]

To see valid arguments you refer to the !attack and !monster_atk documentation.

To see a list of Monsters attacks:

   !ma <monster name>

Helper Commands
------------------

To Modify a combatant's HP value:

   !i hp <combatant name> [operator] <value>

To modify an attribute of a combatant (most common uses are -ac <AC>, -resist/immune/vulv <damage type>, -h)

   !i opt <combatant name> <arguments>

   Most common Arguments:
     -ac <AC> (sets AC to new value)
     -resist/immune/vulv <damage type> (gives resistance, immunity, or vulnerability or specified type)
     -h (toggles wether combatants AC and HP are hidden.)

To add Effects :

   !i effect <combatant name> <duration> <effect name> [roll arguments]

   duration is number of rounds.  If roll arguments are passed they will append to any calls of !i attack from the effected combatant until the effect ends.

To remove Effects:

   !i re <combatant name> [effect name]

Removing from Combat
---------------------

To remove from combat:

   !i remove <combatant name>

Ending Combat
---------------------

To end combat (Avrae will ask if you wish to end combat, reply "yes"):

   !i end
