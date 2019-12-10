Player Combat Guide
===============================

This Guide will help players join combat and use actions on their turns.

.. note::
   arguments surrounded like <this> are required, and arguments in [brackets] are optional. Put spaces around arguments that contain spaces.

.. note::
   This guide will move *roughly* in chronological order, meaning commands near the top should be run first.

Joining Combat
---------------------------

To join combat, your DM must first start it.  Once they have, proceed below to the follwoing commands.

   !init cadd [arguments]

   This will add you **Current Active** character in SheetManager to combat.

   Common arguments:
      -h (hides AC/HP)
      adv (gives advantage on initiative roll)
      dis (gives disadvatage on initiative roll)

To add add a character that is no tracked by Avrae you can use the following:

   !init add <initiative modifier> <name> [arguments]

   .. note::
      If you add an untracked character you will want to supply -hp <max HP> to set Hit points and -ac <AC> to set Armor class.

What now?!

You are all setup and ready to go for when your turn comes!


Your turn
-----------------------------

Its your Turn! Lets go through some commands you can use:

Attack with a weapon:
   !init attack <target name> <weapon name> [arguments]

   To see a list of your character's attacks use !a

Cast a spell:
   !init cast <spell name> -t <target name> [arguments]

   .. note::
      You can use !init aoo <combatant name> <target name> <weapon name> [arguments] for Attacks of Opportunity when it is not your turn.


Helper Commands
-----------------------

To Modify a combatant's HP value:

   !init hp <combatant name> [operator] <value>

To modify an attribute of a combatant (most common uses are -ac <AC>, -resist/immune/vulv <damage type>, -h)

   !init opt <combatant name> <arguments>

   Most common Arguments:
     -ac <AC> (sets AC to new value)
     -resist/immune/vulv <damage type> (gives resistance, immunity, or vulnerability or specified type)
     -h (toggles wether combatants AC and HP are hidden.)

To add Effects :

   !init effect <combatant name> <duration> <effect name> [roll arguments]

   duration is number of rounds.  If roll arguments are passed they will append to any calls of !init attack from the effected combatant until the effect ends.

To remove Effects:

   !init re <combatant name> [effect name]
