Aliasing Tutorials
====================================

Here are a few tutorials for aliases that were created by the Avrae Development Discord.
These should take you step by step through two example aliases.
Thanks to @Croebh#5603 and @silverbass#2407 for writing these, and to @Ydomat#2886 for converting them to this format!

Half-Orc Relentless Endurance Tutorial
--------------------------------------
*By @silverbass#2407.*

.. code-block:: text

  !alias orc-relentless

This sets the alias name.

.. code-block:: text

  embed

This is the base Avrae command, an embed, which makes the pretty text box. Check out ``!help embed`` for more details.

.. code-block:: text

  {{cc="Relentless Endurance"}}

This creates a variable for name of the custom counter, which you do need to make before using it.

.. code-block:: text

  {{v=cc_exists(cc) and get_cc(cc) and not get_hp()}}

This checks if the trigger conditions are valid: do you have a counter for this? is it used? are you at 0 hp?

.. code-block:: text

  -title "{{f"{name} {'uses' if v else 'tries to use'} {cc}!"}}"

This sets the title of the embed, to either success or fail, depending on the v variable from above.
I use fstrings, or formatted strings, to streamline the code a bit.

.. code-block:: text

  -desc "{{"When you are reduced to 0 hit points but not killed outright, you can drop to 1 hit point instead." if v else "You have more than 0 hit points." if get_hp() else "You can’t use this feature again until you finish a Long Rest." if cc_exists(cc) else "You do not have this ability."}}"

This sets the body text of the embed, and shows the 4 cases:
1) it works,
2) you have more than 0 hp,
3) you already used the feature,
4) you don't have the counter in the first place.

.. code-block:: text

  {{mod_cc(cc, -1) if v else ""}}

This decrements the counter, but only if you have it. It checks this to prevent errors.

.. code-block:: text

  -f "{{f"{cc}|{cc_str(cc) if cc_exists(cc) else '*None*'}"}}"

This displays the counter, or None if you don't have it. It's displayed in the embed as a field.
Again, using an fstring for streamlined code.

.. code-block:: text

  {{set_hp(1) if v and not get_hp() else ""}}

This sets your hit points to 1, but only if you have 0 right now.

.. code-block:: text

  -color <color> -thumb <image>

This makes it look pretty.

The end result is:

.. code-block:: text

  !alias orc-relentless embed {{cc="Relentless Endurance"}} {{v=cc_exists(cc) and get_cc(cc) and not get_hp()}} -title "{{f"{name} {'uses' if v else 'tries to use'} {cc}!"}}" -desc "{{"When you are reduced to 0 hit points but not killed outright, you can drop to 1 hit point instead." if v else "You have more than 0 hit points." if get_hp() else "You can’t use this feature again until you finish a Long Rest." if cc_exists(cc) else "You do not have this ability."}}" {{mod_cc(cc, -1) if v else ""}} -f "{{f"{cc}|{cc_str(cc) if cc_exists(cc) else '*None*'}"}}" {{set_hp(1) if v and not get_hp() else ""}}


Insult Tutorial
-------------------------------------
*By @Croebh#5603*

.. code-block:: text

  !servalias insult embed

This creates a servalias named insult, calling the command embed.

.. code-block:: text

  {{ G = get_gvar("68c31679-634d-46de-999b-4e20b1f8b172") }}

This sets a local variable, G to the contents of the gvar with the ID 68c31679-634d-46de-999b-4e20b1f8b172.
The get_gvar() function grabs the content of the Gvar as plain text.

.. code-block:: text

  {{ L = [x.split(",") for x in G.split("\n\n")] }}

This sets a local variable, L to a list comprehension.
What that is doing is breaking down the variable G into a list of lists.

``G.split("\n\n")``

So, this is splitting text everytime there is two line breaks. In this case, it ends up being in three parts.

``x.split(",") for x in``

This part is saying for each part of the split we did above, call that part x, then split THAT part on every comma.
So L ends up being something like ``[["Words","Stuff"],["Other","Words","More!"],["More","Words"]]``

.. code-block:: text

  {{ I = [x.pop(roll(f'1d{len(x)}-1')).title() for x in L] }}

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

  {{ aL = L[0] + L[1] }}

This sets the variable aL to the combination of the first results of L, so ``["stuff"]`` and ``["Other","Words"]``,
making aL ``["stuff","Other","Words"]``, as they were added together. This doesn't remove those two lists from L

.. code-block:: text

  {{ add = [aL.pop(roll(f'1d{len(aL)-1}')).title() for x in range(int("&1&".strip("&")))]}}

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

  {{ I = [I[0], I[1]] + add + [I[2]] }}

This overwrites the variable I with a new list.

``[I[0], I[1]]``

So this will be the first two items in I, ``"Words" and "More!"``, making it ``["Words","More!"]``.

``add`` is just the entire add variable, ``["Stuff", "Words"]``

And finally, ``[I[2]]`` is the third (and final) item in I, ``"Words"``

Combining them all together, the variable I is now, ``["Words","More!","Stuff", "Words","Words"]``

.. code-block:: text

  -title "You {{" ".join(I)}}!"

So, this adds a -title to the embed the command starts with. The contents of this title is ``"You {{" ".join(I)}}!"``

``{{" ".join(I)}}``

This joins the contents of the variable I, putting space (" ") between each item. So in this case, it would return
``"Words More! Stuff Words Words"``

Putting that together with the text outside the code, the title will be ``"You Words More! Stuff Words Words!"``

.. code-block:: text

  -thumb <image> -color <color>

This just sets the thumbnail and color of the embed to those that are set on your character.

The end result is:

.. code-block:: text

  !servalias insult embed
  {{ G = get_gvar("68c31679-634d-46de-999b-4e20b1f8b172") }}
  {{ L = [x.split(",") for x in G.split("\n\n")] }}
  {{ I = [x.pop(roll(f'1d{len(x)}-1')).title() for x in L] }}
  {{ aL = L[0] + L[1] }}
  {{ add = [aL.pop(roll(f'1d{len(aL)-1}')).title() for x in range(int("&1&".strip("&")))]}}
  {{ I = [I[0], I[1]] + add + [I[2]] }}
  -title "You {{" ".join(I)}}!"
  -thumb <image> -color <color>
