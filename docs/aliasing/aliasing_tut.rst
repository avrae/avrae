Aliasing Tutorials
====================================

Here are a few tutorials for aliases that were created by the Avrae Development Discord.
These should take you step by step through two example aliases.
Thanks to @Croebh#5603 and @silverbass#2407 for writing these, @Ydomat#2886 for converting them to this format, and @mobius#1442 for updating them!

Half-Orc Relentless Endurance Tutorial
--------------------------------------
*By @silverbass#2407, rewritten in Drac2 by @mobius#1442*

.. code-block:: text

  !alias orc-relentless

This sets the alias name. If creating this alias in the Avrae workshop, you'll leave this line out.

.. code-block:: text

  embed

This is the base Avrae command, an embed, which makes the pretty text box. Check out ``!help embed`` for more details.

.. code-block:: text

  <drac2>
  
This specifies the start of a code block that will contain all the logic for the alias.   

.. code-block:: text

  #Define variables for later use
  cc = "Relentless Endurance"
  desc = "When you are reduced to 0 hit points but not killed outright, you can drop to 1 hit point instead."
  rest = "You can’t use this feature again until you finish a long rest."
  hasHP = "You have not been reduced to 0 hit points."
  noCC = "You do not have this ability."
	
This defines some string variables that the alias will use in various places. Defining them as variables allows us to use the same strings in multiple places more easily, and makes the code more legible. This line: ``#Define variables for later use`` is a comment. Anything starting with a ``#`` is ignored when the alias runs, and can be used to make your alias code more readable and easier to follow

.. code-block:: text

  ch=character()

This alias will be accessing the active character several times, so this defines a variable to store it for easier access.

.. code-block:: text

  #Create the counter if it should exist but doesn't already
  if ch.race.lower() == "half-orc":
      ch.create_cc_nx(cc, 0, 1, "long", "bubble", None, None, cc, desc+" "+rest) 

The alias uses a custom counter to track the use of this ability. If the character was imported from Beyond, it should create the custom counter automatically. In case the character doesn't have the custom counter, for whatever reason, this code checks if the character's race is Half-Orc and creates it.

``>>> if ch.race.lower() == "half-orc":``

This is a simple if-statement. We check if the character's race is Half-Orc. The ``lower()`` after the race makes it lower-case. We do this because string comparisons are case-sensitive, and making it all lower-case means we don't have to check for Half-Orc, Half-orc, and half-orc individually. Note the ``:``. Forgetting it is a common error when using if blocks. The code inside the block will only execute if this condition is true.

``...   ch.create_cc_nx(cc, 0, 1, "long", "bubble", None, None, cc, desc+" "+rest)``

This code will run only if the if statement is true. That is, if the character's race is half-orc. Pay attention to the indentation shown in the code block above; this is another common error when writing if-blocks. Any code to be executed inside the block must be indented, and must all have the same indentation. Tabs or spaces will work, but you can't mix-and match them. Each line in the block must have have the same amount and type of leading white space.

So what does this line do? It has a lot of parts, so let's look at them in-order:
``ch.create_cc_nx`` This will create a custom counter on the character (``ch``) if it doesn't already exist. 
``cc`` This defines the name of the counter. In this case, it uses one of the variables declared earlier, so the counter will be ``Relentless Endurance``
``0, 1`` The next two arguments define the minimum and maximum values of the CC. Since this can only ever be used once at a time, this counter can only go between 0 (used) and 1 (available)
``"long"`` Next we define how the counter resets. We're specifying that it should reset on a Long Rest.
``"bubble"`` This specifies how the counter should be presented. Bubble gives a depiction of the counter that is more visual and aesthetically pleasing
``None, None`` These next two are Reset To and Reset By, respectively. They are optional arguments for more advanced custom counters, and aren't needed for this one.
``cc`` The next argumet is the Title of the counter that will be seen when setting or viewing the counter. We're just setting it to the same thing as its title.
``desc+" "+rest`` Finally, this is the counter's description. We're using two of the previously-defined variables, joined with a space between them.

.. code-block:: text

  #Logic of the alias. Check for all the necessary conditions
  succ = "tries to use"
  if ch.cc_exists(cc) and ch.get_cc(cc) and not ch.hp: 
      succ = "uses"
      D = desc
      ch.mod_cc(cc, -1)
      ch.set_hp(1)
	  
Another if-block, this one a little more complex than the last. We're checking more things here, and then executing more code if it meets all the conditions. Let's break it down.

``succ = "tries to use"`` We're starting with this variable and giving it a default value. We'll change it later if the alias succeeds.

``>>> if ch.cc_exists(cc) and ch.get_cc(cc) and not ch.hp:``

This if-statement checks if all of the trigger conditions are valid. The ``and`` combining each statement means that all of the following conditions must be met.
``ch.cc_exists(cc)`` This checks if this character (``ch``) have a custom counter (``cc_exists``) called "Relentless Endurance" (``(cc)``)
``ch.get_cc(cc)`` This gets the value of the counter, which will be 0 (used) or 1 (not used). If-checks treat zero as False, and non-zero as True. So, if the counter is used, the if-check will fail here.
``not ch.hp`` Checks the character's hp. As before, zero hit points will be considered False, and non-zero is True. The ``not`` before hand will reverse that. That means that if the character has any HP left, the if-check will fail.

If all the conditions are met, the alias will execute the code inside the block. Note that each of these lines has the same indentation. This block will do most of the mechanics work the alias is meant for. Going line-by-line:

``...     succ = "uses"`` This is the success case that will override this variable to indicate a successful use instead of a failed attempt.
``...     D = desc`` This just sets one variable to another. The alias will use ``D`` later when showing the result to the player
``...     ch.mod_cc(cc, -1)`` This will modify (``mod_cc``) the value of the counter (``cc``) by ``-1``, reducing it from 1 to 0 and marking it as used
``...     ch.set_hp(1)`` This sets the character's hitpoints to 1.

.. code-block:: text
	  
  elif ch.hp:
      D = hasHP
  elif ch.cc_exists(cc):
      D = rest
  else:
      D = noCC

And this introduces a little more complexity to if-blocks! The previous if-check defined the conditions for the ability succeeding. If one or more of those conditions failed, that block would be skipped and these conditions will be checked, in order, until one succeeds. If the initial ``if`` and all of the ``elif`` conditions fail, the ``else`` will run. 

After this whole ``if ... elif ... else`` block is finished, ``D`` will contain the body text of the embed, and will be one of the 4 response strings that were defined above:

1) it works (desc)
2) you have more than 0 hp (hasHP)
3) you already used the feature (rest)
4) you don't have the counter in the first place (noCC)

.. code-block:: text

  T = f"{name} {succ} {cc}!"
  F = f"{cc}|{ch.cc_str(cc) if ch.cc_exists(cc) else '*None*'}"

Setting some more variables that will be used in the embed. T will be used in the title of the embed, indicating either success or failure to the player. F will be the contents of a Field that will include the value of the counter in the embed (or ``*None*`` if the character doesn't have the counter). They use fstrings, or formatted strings, to streamline the code a bit.

.. code-block:: text

  </drac2>

This closes off the code block and everything else will be arguments to the embed command.

.. code-block:: text

  -title "{{T}}" 
  -desc "{{D}}" 
  -f "{{F}}"  

This will send the defined variables to the embed to be displayed. 

.. code-block:: text

  -color <color> 
  -thumb <image>

This makes it look pretty, setting the embed color and the character's image (if any) as a thumbnail

The end result is:

.. code-block:: text

  !alias orc-relentless embed 
  <drac2>
  #Define variables for later use
  cc = "Relentless Endurance"
  desc = "When you are reduced to 0 hit points but not killed outright, you can drop to 1 hit point instead."
  rest = "You can’t use this feature again until you finish a long rest."
  hasHP = "You have not been reduced to 0 hit points."
  noCC = "You do not have this ability."
  ch=character()

  #Create the counter if it should exist but doesn't already
  if ch.race.lower() == "half-orc":
      ch.create_cc_nx(cc, 0, 1, "long", "bubble", None, None, cc, desc+" "+rest) 

  #Logic of the alias. Check for all the necessary conditions
  succ = "tries to use"
  if ch.cc_exists(cc) and ch.get_cc(cc) and not ch.hp: 
      succ = "uses"
      D = desc
      ch.mod_cc(cc, -1)
      ch.set_hp(1)    
  elif ch.hp:
      D = hasHP
  elif ch.cc_exists(cc):
      D = rest
  else:
      D = noCC

  #Prepare the output 
  T = f"{name} {succ} {cc}!"
  F = f"{cc}|{ch.cc_str(cc) if ch.cc_exists(cc) else '*None*'}"
  </drac2>
  -title "{{T}}" 
  -desc "{{D}}" 
  -f "{{F}}"  
  -color <color> 
  -thumb <image>


Insult Tutorial
-------------------------------------
*By @Croebh#5603 with minor drac2 updates by @mobius#1442*

.. code-block:: text

  !servalias insult embed

This creates a servalias named insult, calling the command embed.

.. code-block:: text

  <drac2>

This specifies the start of a code block.  
  
.. code-block:: text

  G = get_gvar("68c31679-634d-46de-999b-4e20b1f8b172")

This sets a local variable, G to the contents of the gvar with the ID 68c31679-634d-46de-999b-4e20b1f8b172.
The get_gvar() function grabs the content of the Gvar as plain text.

.. code-block:: text

  L = [x.split(",") for x in G.split("\n\n")]

This sets a local variable, L to a list comprehension.
What that is doing is breaking down the variable G into a list of lists.

``G.split("\n\n")``

So, this is splitting text everytime there is two line breaks. In this case, it ends up being in three parts.

``x.split(",") for x in``

This part is saying for each part of the split we did above, call that part x, then split THAT part on every comma.
So L ends up being something like ``[["Words","Stuff"],["Other","Words","More!"],["More","Words"]]``

.. code-block:: text

  I = [x.pop(roll(f'1d{len(x)}-1')).title() for x in L]

This sets another local variable, I, to another list comprehension, this time iterating on the variable L.

``x.pop(roll(f'1d{len(x)}-1')).title()``

Okay, a little more complicated. We're going to start in the middle.

``f'1d{len(x)}-1'``

So, this is an f-string, or formatted strings. It allows us to run code in the middle of string, in this case
``{len(x)}``, which will be the length of x (which is the current part of L that we're looking at.).
So in our example, say we're looking at the first part of L, which is ``["words","stuff"]``.
The length of this is 2, so it will return the string, ``1d2-1``. The -1 is important because lists are 0-indexed,
that is, the first item in the list has an index of 0 (as opposed to 1).

``roll()``

This rolls the returned string, which as we determined above, is 1d2-1. Lets say it returns 1.

``x.pop()``

What this does is pop the item at the given index out of the list. This removes the item from the list, and returns it.
This removes the chance of that particular item being chosen again. With our result of 1, this will return the second
item (because its index-0), which is ``stuff``. This will make x be ``["words"]`` now.

``.title()``

This just capitalizes the first character of each word in the string. Now it will return ``Words``

Now, iterating over this list could make I ``["Words","More!","Words"]``, and those would be removed from L,
so L is now ``[["stuff"],["Other","Words"],["More"]]``

.. code-block:: text

  aL = L[0] + L[1]

This sets the variable aL to the combination of the first results of L, so ``["stuff"]`` and ``["Other","Words"]``,
making aL ``["stuff","Other","Words"]``, as they were added together. This doesn't remove those two lists from L

.. code-block:: text

  add = [aL.pop(roll(f'1d{len(aL)-1}')).title() for x in range(int("&1&".strip("&")))]

Another fun one. This sets the variable ``add`` to another list comprehension, this time on a varible list.

``range(int("&1&".strip("&")))``

``&1&`` is a placeholder that gets replaced by the first argument given to the alias.
So with ``!insult 3``, ``&1&`` would return ``3``. However, with no args given, it doesn't get replaced,
and stays as ``&1&``.

``.strip('&')``

So, this strips the '&' character from either side of the string. This lets us have a default of "1" when no arguments
given (because "&1&" with the "&"'s removed is "1")

``int()``

this converts the string to a integer. This will error if the first arg is anything other than a number
(like if anyone were to ``!insult silverbass``)

``range()``

This creates a list of numbers. In this case, because only one argument is given to it, it creates a list of numbers
from 0 to the number given, not including that number. So with an argument of 1, it will make a list ``[0]``, but with an
argument of 3, it will return ``[0,1,2]``

``aL.pop(roll(f'1d{len(aL)-1}')).title()``

More fun, but its basically the exact same as the last time. A formatted string, this time calling the length of the
aL list as opposed to the current iteration. A roll of that string, and then a pop out of aL, returning and removing
the given index, then capitalizing it.

For this example, lets say the user did ``!insult 2``. So the range will return ``[0,1]``, making it do the
function twice. The length of aL the first time is 3, so it will roll 1d3-1, let's say it returns 0.
This will get popped out of aL as "Stuff"

The second time it runs, the length is 2 (because we just removed one result), so it will roll 1d2-1.
This time lets say we got 1, so the second time it will return "Words".

So add is now ``["Stuff", "Words"]``

.. code-block:: text

  I = [I[0], I[1]] + add + [I[2]]

This overwrites the variable I with a new list.

``[I[0], I[1]]``

So this will be the first two items in I, ``"Words" and "More!"``, making it ``["Words","More!"]``.

``add`` is just the entire add variable, ``["Stuff", "Words"]``

And finally, ``[I[2]]`` is the third (and final) item in I, ``"Words"``

Combining them all together, the variable I is now, ``["Words","More!","Stuff", "Words","Words"]``

.. code-block:: text

  I = " ".join(I)

This joins the contents of the variable I, putting space (" ") between each item. So in this case, I now contains
``"Words More! Stuff Words Words"``

.. code-block:: text

  </drac2>

This closes off the code block and everything else will be arguments to the embed command.

.. code-block:: text

  -title "You {{I}}!"

This adds a -title to the embed the alias starts with. The contents of this title will be ``"You Words More! Stuff Words Words!"``

.. code-block:: text

  -thumb <image> -color <color>

This just sets the thumbnail and color of the embed to those that are set on your character.

The end result is:

.. code-block:: text

  !servalias insult embed
  <drac2>
  G = get_gvar("68c31679-634d-46de-999b-4e20b1f8b172")
  L = [x.split(",") for x in G.split("\n\n")]
  I = [x.pop(roll(f'1d{len(x)}-1')).title() for x in L]
  aL = L[0] + L[1]
  add = [aL.pop(roll(f'1d{len(aL)-1}')).title() for x in range(int("&1&".strip("&")))]
  I = [I[0], I[1]] + add + [I[2]]
  I = " ".join(I)
  </drac2>
  -title "You {{I}}!"
  -thumb <image> -color <color>  