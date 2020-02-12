Aliasing Basics
======================

Avrae has vast potential for making long commands simple.  It allows you to create and maintain commands. These commands can be used personally or shared with other users on a server.  Let's take a look at some of the basics of automation that you can start using in your server.

.. note::
  If you have experience with JSON and API's and are looking for more advanced documentation, head on over to the `Aliasing API Page <aliasing/api.html>`_.

Command Types
------------------------

Avrae has a few different types of commands that are used for different purposes.

**Alias** - Used to shorten commands that would require a large or lengthy amount of text to use,
to run code before running an Avrae command, or to write your own custom command.
(In many cases, aliases are used to track features or abilities)

  Examples for Alias usage:
    - Short rest
    - Long rest
    - Sorcerer Font of Magic
    - Barbarian Rage (Effects)
    - Dash, Dodge, Hide Actions

**Snippet** - Used to augment dice rolls like saves, attacks, or ability checks.

  Examples for Snippet usage:
    - Guidance cantrip
    - Hunter's Mark (Damage)
    - Cover (3/4, Half, etc)
    - Barbarian Rage (Damage)
    - Bardic Inspiration

Command Levels
------------------------

There are two levels of commands that are built into Avrae: user level and server level.
Aliases and snippets can be setup at either level. Below is how to look at snippets or aliases at each level.

.. note::
  If a user and a server have aliases with the same name, the user alias will take priority.

**!alias** - Will show user level aliases.

**!servalias** - Will show server level aliases.

**!snippet** - Will show user level snippets

**!servsnippet** - will show server level snippets

.. note::
  To add server-level aliases or snippets, a user must have a role called "Dragonspeaker" or "Server Aliaser".

Help
--------------------

As always you can also come to the Avrae Development Discord for help with aliasing, `here <https://support.avrae.io>`_.
