Getting Started
===============
Avrae is a powerful bot, but it can be pretty daunting to get everything set up! Here's
three quick steps to getting a character sheet linked with Avrae, and ready to play in a game!

Step 1: Invite Avrae to Your Server
-----------------------------------
The first step is to add Avrae to your server. Make sure you have the **Manage Server** permission, and head over to
`invite.avrae.io <https://invite.avrae.io/>`_.

Optional: Setting a Prefix
^^^^^^^^^^^^^^^^^^^^^^^^^^
After you add Avrae, you might want to change the prefix in case other bots use the same prefix::

  !prefix <prefix> - Insert any prefix you want to use based on your server (ex. !, #, $, !!, etc.)

Using Help
^^^^^^^^^^

With the built in !help command, you get information about other commands in the bot. Here is the syntax for using help::

  !help <command>

For example, ``!help attack`` will bring up the help dialog for the !attack command. Try it out for yourself! ::

  !help

Help will give you examples of commands you can use and information about them.

Step 2: Add a Character
-----------------------
Once you have your stats, think of what character you want to play and make them a sheet on
`D&D Beyond <https://www.dndbeyond.com/>`_, `Dicecloud <https://dicecloud.com/>`_,
or `Google Sheets <https://gsheet2.avrae.io/>`_!

Once you're done making your character, make sure it's publicly viewable (Avrae needs to be able to see your sheet),
grab the sharing URL, and follow the steps below depending on what sheet system you chose to use.
You should see your character's stats pop up in Discord!

D&D Beyond
^^^^^^^^^^
To add a character from D&D Beyond, use the following command::

  !import https://ddb.ac/characters/...

.. note::
    If you link your D&D Beyond and Discord accounts and your DM links your campaign to a channel, your character's
    rolls made on D&D Beyond or the Player App will appear in Discord!

Dicecloud
^^^^^^^^^
To add a character from Dicecloud, use the following command::

  !import https://dicecloud.com/character/...

.. note::
    Avrae can update your HP and consumables live on Dicecloud - share the sheet with edit permissions with ``avrae``.

Google Sheets
^^^^^^^^^^^^^
To add a character from GSheet, use the following command::

  !import https://docs.google.com/spreadsheets/d/...

.. note::
    You will need to share your sheet with ``avrae-320@avrae-bot.iam.gserviceaccount.com``.

Step 3: Ready to Roll
---------------------
You're ready to roll now! You can use the ``!check`` command to roll skill checks, ``!save`` for saving throws,
and ``!attack`` to attack with your weapons!

For example:
    * ``!check arcana`` - rolls an Intelligence (Arcana) check
    * ``!save dexterity`` - rolls a Dexterity Save
    * ``!attack longsword`` - rolls an attack with a longsword

Next Steps
----------
For more detailed documentation on how each command works, you can use ``!help <command>`` to view a list of supported
arguments, or come join us at the `Avrae Development Discord <https://support.avrae.io>`_!

