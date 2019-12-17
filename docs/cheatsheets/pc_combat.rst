Player Combat Guide
===============================

This Guide will help players join combat and use actions on their turns.

.. note::
   arguments surrounded like <this> are required, and arguments in [brackets] are optional. Put spaces around arguments that contain spaces.

.. note::
   This guide will move *roughly* in chronological order, meaning commands near the top should be run first.

Joining Combat
---------------------------

To join combat, your DM must first start it.  Once they have, proceed below to the following commands::

   !i cadd [arguments]

This will add you **Current Active** character in SheetManager to combat.

   Common arguments:
      * -h (hides AC/HP)
      * adv (gives advantage on initiative roll)
      * dis (gives disadvantage on initiative roll)

To add a character that is not tracked by Avrae you can use the following.::

   !i add <initiative modifier> <name> [arguments]

The character will be added to the initiative as the name provided.

  .. note::
      If you add an untracked character you will want to supply -hp <max HP> to set Hit points and -ac <AC> to set Armor class.

What now?!

You are all setup and ready to go for when your turn comes!


Your turn
-----------------------------

Its your Turn! Lets go through some commands you can use:

Attack with a weapon.::
   !i attack <target name> <weapon name> [arguments]

To see a list of your character's attacks use !a

Cast a spell.::
   !i cast <spell name> -t <target name> [arguments]


.. note::
   You can use !i aoo <combatant name> <target name> <weapon name> [arguments] for Attacks of Opportunity when it is not your turn.


Helper Commands
-----------------------

To Modify a combatant's HP value::

   !i hp <combatant name> [operator] <value>

To modify an attribute of a combatant::

   !i opt <combatant name> <arguments>

Most common Arguments:
     * -ac <AC> (sets AC to new value)
     * -resist/immune/vulv <damage type> (gives resistance, immunity, or vulnerability or specified type)
     * -h (toggles weather combatants AC and HP are hidden.)

To add Effects to a combatant::

   !i effect <combatant name> <duration> <effect name> [roll arguments]

.. note::
   duration is number of rounds.  If roll arguments are passed they will append to any calls of !i attack from the effected combatant until the effect ends.

To remove Effects from a combatant::

   !i re <combatant name> [effect name]
