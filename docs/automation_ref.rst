Automation Reference
====================

This page details the structure of Avrae's Automation system, the backbone behind custom spells and attacks.

Basic Structure
---------------
An automation run is made up of a list of *effects* (AKA *automation node*), each of which may have additional *effects*
that it runs under certain conditions. This recursive structure is called the *automation tree*.

**Glossary**

.. data:: automation engine

    The Automation Engine is the code responsible for reading the automation tree and executing it against the current
    game state. It handles rolling the dice, checking against your targets' armor classes, modifying hit points, and
    other game mechanics.

.. data:: automation tree
          automation

    The automation tree (sometimes just called "automation") is the program that the Automation Engine runs. It's made
    up of multiple nodes that all link together to make an attack, action, spell, or more.

.. data:: effect
          node

    A single step of automation - usually, this is a D&D game mechanic like :ref:`rolling to hit<Attack>`,
    :ref:`making a saving throw<Save>`, or :ref:`dealing damage<Damage>`, but this can also be used in more programmatic
    ways to help set up other nodes.

Runtime Variables
-----------------

All Automation runs provide the following variables:

- ``caster`` (:class:`~aliasing.api.statblock.AliasStatBlock`) The character, combatant, or monster who is running the
  automation.
- ``targets`` (list of :class:`~aliasing.api.statblock.AliasStatBlock`, :class:`str`, or None) A list of combatants
  targeted by this automation (i.e. the ``-t`` argument).
- ``spell_attack_bonus`` (:class:`int` or None) - The attack bonus for the spell, or the caster's default attack bonus.
- ``spell_dc`` (:class:`int` or None) - The DC for the spell, or the caster's default DC.
- ``spell_level`` (:class:`int` or None) - The level used to cast the spell, or None
- ``choice`` (:class:`str`) - The input provided by the ``-choice`` argument, always lowercase. If the arg was not used, it will be an empty string.

Additionally, runs triggered by an initiative effect (such as automation provided in a :ref:`ButtonInteraction`) provide
the following variables:

- ``ieffect`` (:class:`~aliasing.api.combat.SimpleEffect`) The initiative effect responsible for providing the
  automation.

Target
------
.. code-block:: typescript

    {
        type: "target";
        target: "all" | "each" | int | "self" | "parent" | "children";
        effects: Effect[];
        sortBy?: "hp_asc" | "hp_desc";
        self_target?: boolean;
    }

A Target effect should only show up as a top-level effect.
It designates what creatures to affect.

.. class:: Target

    .. attribute:: target

        - ``"all"`` or ``"each"`` (actions only): Affects each of the given (by the ``-t`` argument) targets.
        - ``int`` (actions only): Affects the Nth target (1-indexed).
        - ``"self"``: Affects the caster, or the actor the triggering effect is on if run from an IEffect button.
        - ``"parent"`` (IEffect buttons only): If the triggering effect has a parent effect, affects the actor the
          parent effect is on.
        - ``"children"`` (IEffect buttons only): If the triggering effect has any children effects, affects each actor a
          child effect is on.

    .. attribute:: effects

        A list of effects that each targeted creature will be subject to.

    .. attribute:: sortBy

        *optional* - Whether to sort the target list. If not given, targets are processed in the order the ``-t``
        arguments are seen. This does not affect ``self`` targets.

        - ``hp_asc``: Sorts the targets in order of remaining hit points ascending (lowest HP first, None last).
        - ``hp_desc``: Sorts the targets in order of remaining hit points descending (highest HP first, None last).

**Variables**

- ``target`` (:class:`~aliasing.api.statblock.AliasStatBlock`) The current target.
- ``targetIteration`` (:class:`int`) If running multiple iterations (i.e. ``-rr``), the current iteration (1-indexed).
- ``targetIterations`` (:class:`int`) The total number of iterations. Minimum 1, maximum 25.
- ``targetIndex`` (:class:`int`) The index of the target in the list of targets processed by this effect
  (0-indexed - first target = ``0``, second = ``1``, etc.). Self targets, nth-targets, and parent targets will always
  be ``0``.
- ``targetNumber`` (:class:`int`) Same as ``targetIndex``, but 1-indexed (equivalent to ``targetIndex + 1``).

.. _Attack:

Attack
------
.. code-block:: typescript

    {
        type: "attack";
        hit: Effect[];
        miss: Effect[];
        attackBonus?: IntExpression;
        adv?: IntExpression;
    }

An Attack effect makes an attack roll against a targeted creature.
It must be inside a Target effect.

.. class:: Attack:

    .. attribute:: hit

        A list of effects to execute on a hit.

    .. attribute:: miss

        A list of effects to execute on a miss.

    .. attribute:: attackBonus

        *optional* - An IntExpression that details what attack bonus to use (defaults to caster's spell attack mod).

    .. attribute:: adv

        *optional* - An IntExpression that details whether the attack has inherent advantage or not. ``0`` for flat,
        ``1`` for Advantage, ``2`` for Elven Accuracy, ``-1`` for Disadvantage (Default is flat).

**Variables**

- ``lastAttackDidHit`` (:class:`bool`) Whether the attack hit.
- ``lastAttackDidCrit`` (:class:`bool`) If the attack hit, whether it crit.
- ``lastAttackRollTotal`` (:class:`int`) The result of the last to-hit roll (0 if no roll was made).
- ``lastAttackNaturalRoll`` (:class:`int`) The natural roll of the last to-hit roll (e.g. `10` in `1d20 (10) + 5 = 15`;
  0 if no roll was made).
- ``lastAttackHadAdvantage`` (:class:`int`) The advantage type of the last to-hit roll. ``0`` for flat, ``1`` for;
  Advantage, ``2`` for Elven Accuracy, ``-1`` for Disadvantage

.. _Save:

Save
----
.. code-block:: typescript

    {
        type: "save";
        stat: "str" | "dex" | "con" | "int" | "wis" | "cha";
        fail: Effect[];
        success: Effect[];
        dc?: IntExpression;
        adv?: -1 | 0 | 1;
    }

A Save effect forces a targeted creature to make a saving throw.
It must be inside a Target effect.

.. class:: Save

    .. attribute:: stat

        The type of saving throw.

    .. attribute:: fail

        A list of effects to execute on a failed save.

    .. attribute:: success

        A list of effects to execute on a successful save.

    .. attribute:: dc

        *optional* - An IntExpression that details what DC to use (defaults to caster's spell DC).

    .. attribute:: adv

        *optional, default 0* - Whether the saving throw should have advantage by default (``-1`` = disadvantage,
        ``1`` = advantage, ``0`` = no advantage).

**Variables**

- ``lastSaveDidPass`` (:class:`bool`) Whether the target passed the save.
- ``lastSaveDC`` (:class:`int`) The DC of the last save roll.
- ``lastSaveRollTotal`` (:class:`int`) The result of the last save roll (0 if no roll was made).
- ``lastSaveNaturalRoll`` (:class:`int`) The natural roll of the last save roll (e.g. ``10`` in ``1d20 (10) + 5 = 15``;
  0 if no roll was made).
- ``lastSaveAbility`` (:class:`str`) The title-case full name of the ability the save was made with (e.g.
  ``"Strength"``, ``"Wisdom"``, etc).

.. _Damage:

Damage
------
.. code-block:: typescript

    {
        type: "damage";
        damage: AnnotatedString;
        overheal?: boolean;
        higher?: {int: string};
        cantripScale?: boolean;
        fixedValue?: boolean;
    }

Deals damage to or heals a targeted creature. It must be inside a Target effect.

.. note::

    This node can also be used to heal a target; simply use negative damage to supply healing.

.. class:: Damage

    .. attribute:: damage

        How much damage to deal.

    .. attribute:: overheal

        .. versionadded:: 1.4.1

        *optional* - Whether this damage should allow a target to exceed its hit point maximum.

    .. attribute:: higher

        *optional* - How much to add to the damage when a spell is cast at a certain level.

    .. attribute:: cantripScale

        *optional* - Whether this roll should scale like a cantrip.

    .. attribute:: fixedValue

        *optional* - If ``true``, won't add any bonuses to damage from ``-d`` arguments or damage bonus effects.

**Variables**

- ``lastDamage`` (:class:`int`) The amount of damage dealt.

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

.. class:: TempHP

    .. attribute:: amount

        How much temp HP the target should have.

    .. attribute:: higher

        *optional* - How much to add to the THP when a spell is cast at a certain level.

    .. attribute:: cantripScale

        *optional* - Whether this roll should scale like a cantrip.

**Variables**

- ``lastTempHp`` (:class:`int`) The amount of temp HP granted.

IEffect
-------
.. code-block:: typescript

    {
        type: "ieffect2";
        name: AnnotatedString;
        duration?: int | IntExpression;
        effects?: PassiveEffects;
        attacks?: AttackInteraction[];
        buttons?: ButtonInteraction[];
        end?: boolean;
        conc?: boolean;
        desc?: AnnotatedString;
        stacking?: boolean;
        save_as?: string;
        parent?: string;
        target_self?: boolean;
        tick_on_caster?: boolean;
    }

Adds an InitTracker Effect to a targeted creature, if the automation target is in combat.
It must be inside a Target effect.

.. note::

    If the targeted creature is not in combat, this will display the effects of the initiative effect but not save
    it on the creature.

.. class:: IEffect

    .. attribute:: name

        The name of the effect to add. Annotations will show as *Variable* in the attack string.

    .. attribute:: duration

        *optional, default infinite* - The duration of the effect, in rounds of combat. If this is negative, creates an
        effect with infinite duration.

        .. note::

            **Wait, how do durations actually work?**

            Durations use a "tick" system, and ``duration`` is actually a measure of how many "ticks" an effect sticks
            around for. By default, each effect "ticks" once at the beginning of its combatant's turn.

            By using ``end`` and ``tick_on_caster``, you can control how the duration ticks in order to create effects
            that last until the end of your next turn, end of the caster's next turn, etc.

    .. attribute:: effects

        *optional, default no effects* - The effects to add. See :ref:`passiveeffects`.

    .. attribute:: attacks

        *optional, default no attacks* - The attacks granted by this effect. See :ref:`attackinteraction`.

    .. attribute:: buttons

        *optional, default no buttons* - The buttons granted by this effect. See :ref:`buttoninteraction`.

    .. attribute:: end

        *optional, default false* - Whether the effect timer should tick on the end of the turn, rather than start.

    .. attribute:: conc

        *optional, default false* - Whether the effect requires concentration.

    .. attribute:: desc

        *optional* - The description of the effect (displays on combatant's turn).

    .. attribute:: stacking

        *optional, default false* - If true and another effect with the same name is found on the target, instead of
        overwriting, add a child effect with name ``{name} x{count}`` and no description, duration, concentration,
        attacks, or buttons.

    .. attribute:: save_as

        *optional, default None* - If supplied, saves an :class:`IEffectMetaVar` to the automation runtime, which can be
        used in another IEffect's ``parent`` key to set its parent to this effect. Must be a valid identifier.

    .. attribute:: parent

        *optional, default None* - If supplied, sets the created effect's parent to the given effect. This must be the
        name of an existing :class:`IEffectMetaVar`.

        If ``parent`` is supplied but the parent effect does not exist, will not set a parent.

        If ``conc`` is true, the given parent effect will take priority over the concentration effect.

        If ``stacking`` is true and a valid stack parent exists, the stack parent will take priority over the given
        parent.

    .. attribute:: target_self

        *optional, default false* - If true, the effect will be applied to the caster of the action, rather than the
        target.

    .. attribute:: tick_on_caster

        *optional, default false* - If true, the effect's duration will be dependent on the caster of the action, rather
        than the target. For example, a ``tick_on_caster`` effect with a duration of 1 will last until the start of the
        *caster's* next turn, rather than the *target's*.

        If the caster is not in combat, this has no effect.

**Variables**

- ``(supplied save_as)`` (:class:`IEffectMetaVar` or ``None``) A reference to the effect that was added to the target.
  Use this in another IEffect's ``parent`` key to set that IEffect's parent to the given one.

.. _passiveeffects:

PassiveEffects
^^^^^^^^^^^^^^

.. code-block:: typescript

    {
        attack_advantage: IntExpression;
        to_hit_bonus: AnnotatedString;
        damage_bonus: AnnotatedString;
        magical_damage: IntExpression;
        silvered_damage: IntExpression;
        resistances: AnnotatedString[];
        immunities: AnnotatedString[];
        vulnerabilities: AnnotatedString[];
        ignored_resistances: AnnotatedString[];
        ac_value: IntExpression;
        ac_bonus: IntExpression;
        max_hp_value: IntExpression;
        max_hp_bonus: IntExpression;
        save_bonus: AnnotatedString;
        save_adv: AnnotatedString[];
        save_dis: AnnotatedString[];
        check_bonus: AnnotatedString;
        check_adv: AnnotatedString[];
        check_dis: AnnotatedString[];
        dc_bonus: IntExpression;
    }

Used to specify the passive effects granted by an initiative effect.

.. class:: PassiveEffects

    .. attribute:: attack_advantage

        *optional, default no advantage* - Whether this effect gives the combatant advantage on all attacks.
        -1 for dis, 1 for adv, 2 for elven accuracy.

    .. attribute:: to_hit_bonus

        *optional* - A bonus that this effect grants to all of the combatant's to-hit rolls.

    .. attribute:: damage_bonus

        *optional* - A bonus that this effect grants to all of the combatant's damage rolls.

    .. attribute:: magical_damage

        *optional, default false* - Whether this effect makes all of the combatant's attacks do magical damage.
        0 for false, anything else for true.

    .. attribute:: silvered_damage

        *optional, default false* - Whether this effect makes all of the combatant's attacks do silvered damage.
        0 for false, anything else for true.

    .. attribute:: resistances

        *optional* - A list of damage types and optionally modifiers (e.g. "fire", "nonmagical slashing") that the
        combatant should be resistant to while this effect is active.

    .. attribute:: immunities

        *optional* - A list of damage types and optionally modifiers (e.g. "fire", "nonmagical slashing") that the
        combatant should be immune to while this effect is active.

    .. attribute:: vulnerabilities

        *optional* - A list of damage types and optionally modifiers (e.g. "fire", "nonmagical slashing") that the
        combatant should be vulnerable to while this effect is active.

    .. attribute:: ignored_resistances

        *optional* - A list of damage types and optionally modifiers (e.g. "fire", "nonmagical slashing") that the
        combatant should *not* be resistant, immune, or vulnerable to while this effect is active.

    .. attribute:: ac_value

        *optional* - A value to set the combatant's armor class to while this effect is active.

        .. note::
            If both ``ac_value`` and ``ac_bonus`` are specified, the resulting value will be equal to
            ``ac_value + ac_bonus``.

            If multiple effects specify ``ac_value``, the highest value will be used.

    .. attribute:: ac_bonus

        *optional* - A bonus added to the combatant's armor class while this effect is active.

    .. attribute:: max_hp_value

        *optional* - A value to set the combatant's maximum hit points to while this effect is active.

        .. note::
            If both ``max_hp_value`` and ``max_hp_bonus`` are specified, the resulting value will be equal to
            ``max_hp_value + max_hp_bonus``.

            If multiple effects specify ``max_hp_value``, the highest value will be used.

    .. attribute:: max_hp_bonus

        *optional* - A bonus added to the combatant's maximum hit points while this effect is active.

    .. attribute:: save_bonus

        *optional* - A bonus that this effect grants to all of the combatant's saving throws.

    .. attribute:: save_adv

        *optional* - A list of stat names (e.g. ``strength``) that the combatant should have advantage on for their
        respective saving throws while this effect is active. Use ``all`` as a stat name to specify all stats.

    .. attribute:: save_dis

        *optional* - A list of stat names (e.g. ``strength``) that the combatant should have disadvantage on for their
        respective saving throws while this effect is active. Use ``all`` as a stat name to specify all stats.

    .. attribute:: check_bonus

        *optional* - A bonus that this effect grants to all of the combatant's skill checks.

    .. attribute:: check_adv

        *optional* - A list of skill names (e.g. ``sleightOfHand``, ``strength``) that the combatant should have
        advantage on for ability checks for while this effect is active. If a base ability is given, the advantage
        will apply to all skills based on that ability (e.g. ``strength`` gives advantage on ``athletics`` checks).
        Use ``all`` as a stat name to specify all skills.

    .. attribute:: check_dis

        *optional* - A list of skill names (e.g. ``sleightOfHand``, ``strength``) that the combatant should have
        disadvantage on for ability checks for while this effect is active. If a base ability is given, the disadvantage
        will apply to all skills based on that ability (e.g. ``strength`` gives disadvantage on ``athletics`` checks).
        Use ``all`` as a stat name to specify all skills.

    .. attribute:: dc_bonus

        *optional* - A bonus added to the all of the combatant's save DCs while this effect is active.

.. _attackinteraction:

AttackInteraction
^^^^^^^^^^^^^^^^^

.. code-block:: typescript

    {
        attack: Attack;
        defaultDC?: IntExpression;
        defaultAttackBonus?: IntExpression;
        defaultCastingMod?: IntExpression;
    }

Used to specify an attack granted by an initiative effect: some automation that appears in the combatant's
``!action list`` and can be run with a command.

.. class:: AttackInteraction

    .. attribute:: attack

        The Attack model is any valid individual entity as exported by the attack editor on the Avrae Dashboard.
        See :ref:`attack-structure`.

    .. attribute:: defaultDC

        *optional* - The default saving throw DC to use when running the automation. If not provided, defaults to the
        targeted combatant's default spellcasting DC (or any DC specified in the automation). Use this if the effect's
        DC depends on the original caster's DC, rather than the target's DC.

    .. attribute:: defaultAttackBonus

        *optional* - The default attack bonus to use when running the automation. If not provided, defaults to the
        targeted combatant's default attack bonus (or any attack bonus specified in the automation). Use this if the
        effect's attack bonus depends on the original caster's attack bonus, rather than the target's attack bonus.

    .. attribute:: defaultCastingMod

        *optional* - The default spellcasting modifier to use when running the automation. If not provided, defaults to
        the targeted combatant's default spellcasting modifier. Use this if the effect's spellcasting modifier depends
        on the original caster's spellcasting modifier, rather than the target's spellcasting modifier.

.. _buttoninteraction:

ButtonInteraction
^^^^^^^^^^^^^^^^^

.. code-block:: typescript

    {
        automation: Effect[];
        label: AnnotatedString;
        verb?: AnnotatedString;
        style?: IntExpression;
        defaultDC?: IntExpression;
        defaultAttackBonus?: IntExpression;
        defaultCastingMod?: IntExpression;
    }

Used to specify a button that will appear on the targeted combatant's turn and execute some automation when pressed.

.. note::

    Any initiative effects applying an offensive effect to the caster will not be considered when a ButtonInteraction
    is run, to prevent scenarios where an effect granting a damage bonus to the caster increases the damage done by
    a damage over time effect and other similar scenarios.

    You may think of this as a ButtonInteraction's caster being a temporary actor without any active initiative effects.

.. class:: ButtonInteraction

    .. attribute:: automation

        The automation to run when this button is pressed.

    .. attribute:: label

        The label displayed on the button.

    .. attribute:: verb

        *optional, default "uses {label}"* - The verb to use for the displayed output when the button is pressed (e.g.
        "is on fire" would display "NAME is on fire!").

    .. attribute:: style

        *optional, default blurple* - The color of the button (1 = blurple, 2 = grey, 3 = green, 4 = red).

    .. attribute:: defaultDC

        *optional* - The default saving throw DC to use when running the automation. If not provided, defaults to the
        targeted combatant's default spellcasting DC (or any DC specified in the automation). Use this if the effect's
        DC depends on the original caster's DC, rather than the target's DC.

    .. attribute:: defaultAttackBonus

        *optional* - The default attack bonus to use when running the automation. If not provided, defaults to the
        targeted combatant's default attack bonus (or any attack bonus specified in the automation). Use this if the
        effect's attack bonus depends on the original caster's attack bonus, rather than the target's attack bonus.

    .. attribute:: defaultCastingMod

        *optional* - The default spellcasting modifier to use when running the automation. If not provided, defaults to
        the targeted combatant's default spellcasting modifier. Use this if the effect's spellcasting modifier depends
        on the original caster's spellcasting modifier, rather than the target's spellcasting modifier.

Remove IEffect
--------------
.. versionadded:: 4.0.0


.. code-block:: typescript

    {
        type: "remove_ieffect";
        removeParent?: "always" | "if_no_children";
    }

Removes the initiative effect that triggered this automation.
Only works when run in execution triggered by an initiative effect, such as a ButtonInteraction
(see :ref:`buttoninteraction`).

.. class:: RemoveIEffect

    .. attribute:: removeParent

        *optional, default null* - If the removed effect has a parent, whether to remove the parent.

        - ``null`` (default) - Do not remove the parent effect.
        - ``"always"`` - If the removed effect has a parent, remove it too.
        - ``"if_no_children"`` - If the removed effect has a parent and its only remaining child was the removed effect,
          remove it too.

**Variables**

No variables are exposed.

Roll
----
.. code-block:: typescript

    {
        type: "roll";
        dice: AnnotatedString;
        name: string;
        higher?: {int: string};
        cantripScale?: boolean;
        hidden?: boolean;
        displayName?: string;
        fixedValue?: boolean;
    }

Rolls some dice and saves the result in a variable. Displays the roll and its name in a Meta field, unless
``hidden`` is ``true``.

.. class:: Roll

    .. attribute:: dice

        An AnnotatedString detailing what dice to roll.

    .. attribute:: name

        The variable name to save the result as.

    .. attribute:: higher

        *optional* - How much to add to the roll when a spell is cast at a certain level.

    .. attribute:: cantripScale

        *optional* - Whether this roll should scale like a cantrip.

    .. attribute:: hidden

        *optional* - If ``true``, won't display the roll in the Meta field, or apply any bonuses from the ``-d``
        argument.

    .. attribute:: displayName

        The name to display in the Meta field. If left blank, it will use the saved name.

    .. attribute:: fixedValue

        *optional* - If ``true``, won't add any bonuses to damage from ``-d`` arguments or damage bonus effects.


**Variables**

- ``(supplied name)`` (:class:`RollEffectMetaVar`) The result of the roll.
    - You can use this in an AnnotatedString to retrieve the simplified result of the roll. Using this variable in an
      AnnotatedString will always return a string that itself can be rolled.
    - You can use this in an IntExpression to retrieve the roll total.
    - You can compare this variable against a number to determine if the total of the roll equals that number.
- ``lastRoll`` (:class:`int`) The integer total of the roll.

Text
----
.. code-block:: typescript

    {
        type: "text";
        text: AnnotatedString | AbilityReference;
        title: string
    }

Outputs a short amount of text in the resulting embed.

.. class:: Text

    .. attribute:: text

        Either:

        - An AnnotatedString (the text to display).
        - An AbilityReference (see :ref:`AbilityReference`). Displays the ability's description in whole.

    .. attribute:: title

        *optional* - Allows you to set the name of the field. Defaults to "Effect"

.. _set-variable:


Set Variable
------------
.. versionadded:: 2.7.0

.. code-block:: typescript

    {
        type: "variable";
        name: string;
        value: IntExpression;
        higher?: {int: IntExpression};
        onError?: IntExpression;
    }

Saves the result of an ``IntExpression`` to a variable without displaying anything.

.. class:: SetVariable

    .. attribute:: name

        The name of the variable to save.

    .. attribute:: value

        The value to set the variable to.

    .. attribute:: higher

        *optional* - What to set the variable to instead when a spell is cast at a higher level.

    .. attribute:: onError

        *optional* - If provided, what to set the variable to if the normal value would throw an error.

Condition (Branch)
------------------
.. versionadded:: 2.7.0

.. code-block:: typescript

    {
        type: "condition";
        condition: IntExpression;
        onTrue: Effect[];
        onFalse: Effect[];
        errorBehaviour?: "true" | "false" | "both" | "neither" | "raise";
    }

Run certain effects if a certain condition is met, or other effects otherwise. AKA "branch" or "if-else".

.. class:: Condition

    .. attribute:: condition

        The condition to check.

    .. attribute:: onTrue

        The effects to run if ``condition`` is ``True`` or any non-zero value.

    .. attribute:: onFalse

        The effects to run if ``condition`` is ``False`` or ``0``.

    .. attribute:: errorBehaviour

        *optional* - How to behave if the condition raises an error:

        - ``"true"``: Run the ``onTrue`` effects.
        - ``"false"``: Run the ``onFalse`` effects. (*default*)
        - ``"both"``: Run both the ``onTrue`` and ``onFalse`` effects, in that order.
        - ``"neither"``: Skip this effect.
        - ``"raise"``: Raise the error and halt execution.

Use Counter
-----------
.. versionadded:: 2.10.0

.. code-block:: typescript

    {
        type: "counter";
        counter: string | SpellSlotReference | AbilityReference;
        amount: IntExpression;
        allowOverflow?: boolean;
        errorBehaviour?: "warn" | "raise" | "ignore";
        fixedValue?: boolean;
    }

Uses a number of charges of the given counter, and displays the remaining amount and delta.

.. note::
    Regardless of the current target, this effect will always use the *caster's* counter/spell slots!

.. class:: UseCounter

    .. attribute:: counter

        The name of the counter to use (case-sensitive, full match only), or a reference to a spell slot
        (see :ref:`SpellSlotReference`).

    .. attribute:: amount

        The number of charges to use. If negative, will add charges instead of using them.

    .. attribute:: allowOverflow

        *optional, default False* - If False, attempting to overflow/underflow a counter (i.e. use more charges than
        available or add charges exceeding max) will error instead of clipping to bounds.

    .. attribute:: errorBehaviour

        *optional, default "warn"* - How to behave if modifying the counter raises an error:

        - ``"warn"``: Automation will continue to run, and any errors will appear in the output. (*default*)
        - ``"raise"``: Raise the error and halt execution.
        - ``"ignore"``: All errors are silently consumed.

        Some, but not all, possible error conditions are:

        - The target does not have counters (e.g. they are a monster)
        - The counter does not exist
        - ``allowOverflow`` is false and the new value is out of bounds

    .. attribute:: fixedValue

        *optional* - If ``true``, won't take into account ``-amt`` arguments.

**Variables**

- ``lastCounterName`` (:class:`str`) The name of the last used counter. If it was a spell slot, the level of the slot (safe to cast to int, i.e. ``int(lastCounterName)``). (``None`` on error).
- ``lastCounterRemaining`` (:class:`int`) The remaining charges of the last used counter (0 on error).
- ``lastCounterUsedAmount`` (:class:`int`) The amount of the counter successfully used.
- ``lastCounterRequestedAmount`` (:class:`int`) The amount of the counter requested to be used (i.e. the amount
  specified by automation or requested by ``-amt``, regardless of the presence of the ``-i`` arg).

.. _SpellSlotReference:

SpellSlotReference
^^^^^^^^^^^^^^^^^^

.. code-block:: typescript

    {
        slot: number | IntExpression;
    }

.. class:: SpellSlotReference

    .. attribute:: slot

        The level of the spell slot to reference (``[1..9]``).

.. _AbilityReference:

AbilityReference
^^^^^^^^^^^^^^^^

.. code-block:: typescript

    {
        id: number;
        typeId: number;
    }

In most cases, an ``AbilityReference`` should not be constructed manually; use the Automation editor to select an
ability instead. A list of valid abilities can be retrieved from the API at ``/gamedata/limiteduse``.

.. note::
    The Automation Engine will make a best effort at discovering the appropriate counter to use for the
    given ability - in most cases this won't affect the chosen counter, but in some cases, it may
    lead to some unexpected behaviour. Some examples of counter discovery include:

    - Choosing ``Channel Divinity (Paladin)`` may discover a counter granted by the Cleric's Channel Divinity feature
    - Choosing ``Breath Weapon (Gold)`` may discover a counter for a breath weapon of a different color
    - Choosing ``Sorcery Points (Sorcerer)`` may discover a counter granted by the Metamagic Adept feat

.. class:: AbilityReference

    .. attribute:: id

        The ID of the ability referenced.

    .. attribute:: typeId

        The DDB entity type ID of the ability referenced.

Cast Spell
----------
.. versionadded:: 2.11.0

.. code-block:: typescript

    {
        type: "spell";
        id: int;
        level?: int;
        dc?: IntExpression;
        attackBonus?: IntExpression;
        castingMod?: IntExpression;
        parent?: string;
    }

Executes the given spell's automation as if it were immediately cast. Does not use a spell
slot to cast the spell. Can only be used at the root of automation. Cannot be used inside a spell's automation.

This is usually used in features that cast spells using alternate resources (i.e. Use Counter, Cast Spell).

.. class:: CastSpell

    .. attribute:: id

        The DDB entity id of the spell to cast. Use the Automation Editor to select a spell or the
        ``/gamedata/spells`` API endpoint to retrieve a list of valid spell IDs.

    .. attribute:: level

        *optional* - The (slot) level to cast the spell at.

    .. attribute:: dc

        *optional* - The saving throw DC to use when casting the spell. If not provided, defaults to the caster's
        default spellcasting DC (or any DC specified in the spell automation).

    .. attribute:: attackBonus

        *optional* - The spell attack bonus to use when casting the spell. If not provided, defaults to the caster's
        default spell attack bonus (or any attack bonus specified in the spell automation).

    .. attribute:: castingMod

        *optional* - The spellcasting modifier to use when casting the spell. If not provided, defaults to the caster's
        default spellcasting modifier.

    .. attribute:: parent

        *optional, default None* - If supplied, sets the spells created effect's parent to the given effect. This must be the
        name of an existing :class:`IEffectMetaVar`. Useful for handling concentration.

**Variables**

No variables are exposed.

Ability Check
-------------
.. versionadded:: 4.0.0

.. code-block:: typescript

    {
        type: "check";
        ability: string | string[];
        contestAbility?: string | string[];
        dc?: IntExpression;
        success?: Effect[];
        fail?: Effect[];
        contestTie?: "fail" | "success" | "neither";
        adv?: -1 | 0 | 1;
    }

An Ability Check effect forces a targeted creature to make an ability check, optionally as a contest against the caster.
It must be inside a Target effect.

.. class:: Check

    .. attribute:: ability

        The ability to make a check for. Must be one of or a list of the following:

        .. code-block:: text

            "acrobatics"
            "animalHandling"
            "arcana"
            "athletics"
            "deception"
            "history"
            "initiative"
            "insight"
            "intimidation"
            "investigation"
            "medicine"
            "nature"
            "perception"
            "performance"
            "persuasion"
            "religion"
            "sleightOfHand"
            "stealth"
            "survival"
            "strength"
            "dexterity"
            "constitution"
            "intelligence"
            "wisdom"
            "charisma"

        If multiple skills are specified, uses the highest modifier of all the specified skills.

    .. attribute:: contestAbility

        *optional* - Which ability of the caster's to make a contest against.
        Must be one of or a list of the valid skills listed above.
        If multiple skills are specified, uses the highest modifier of all the specified skills.

        Mutually exclusive with ``dc``.

    .. attribute:: dc

        *optional* - An IntExpression that specifies the check's DC. If neither ``dc`` nor ``contestAbility`` is given,
        the check will not run either the ``fail`` or ``success`` nodes.

        Mutually exclusive with ``contestAbility``.

    .. attribute:: success

        *optional* - A list of effects to execute on a successful check or if the **target** wins the contest.
        Requires the *contestAbility* or *dc* attribute to be set.

    .. attribute:: fail

        *optional* - A list of effects to execute on a failed check or if the **target** loses the contest.
        Requires the *contestAbility* or *dc* attribute to be set.

    .. attribute:: contestTie

        *optional, default success* - Which list of effects to run if the ability contest results in a tie.

    .. attribute:: adv

        *optional, default 0* - Whether the check should have advantage by default (``-1`` = disadvantage,
        ``1`` = advantage, ``0`` = no advantage).

**Variables**

- ``lastCheckRollTotal`` (:class:`int`) The result of the last check roll (0 if no roll was made).
- ``lastCheckNaturalRoll`` (:class:`int`) The natural roll of the last check roll (e.g. ``10`` in
  ``1d20 (10) + 5 = 15``; 0 if no roll was made).
- ``lastCheckAbility`` (:class:`str`) The title-case full name of the rolled skill (e.g. ``"Animal Handling"``,
  ``"Arcana"``).
- ``lastCheckDidPass`` (:class:`bool` or ``None``) If a DC was given, whether the target succeeded the check.
  If a contest was specified, whether the target won the contest.
  ``None`` if no or contest given.
- ``lastCheckDC`` (:class:`int` or ``None``) If a DC was given, the DC of the last save roll. ``None`` if no DC given.

*Contest Variables*

- ``lastContestRollTotal`` (:class:`int` or ``None``) The result of the caster's contest roll; ``None`` if no contest
  was made.
- ``lastContestNaturalRoll`` (:class:`int` or ``None``) The natural roll of the caster's contest roll (e.g. ``10`` in
  ``1d20 (10) + 5 = 15``; ``None`` if no contest was made).
- ``lastContestAbility`` (:class:`str` or ``None``) The title-case full name of the skill the caster rolled
  (e.g. ``"Animal Handling"``, ``"Arcana"``). ``None`` if no contest was made.
- ``lastContestDidTie`` (:class:`bool`) Whether a ability contest resulted in a tie.

AnnotatedString
---------------
An AnnotatedString is a string that can access saved variables.
To access a variable, surround the name in brackets (e.g. ``{damage}``).
Available variables include:

- implicit variables from Effects (see relevant effect for a list of variables it provides)
- any defined in a ``Roll`` or ``Set Variable`` effect
- all variables from the :ref:`cvar-table`

This will replace the bracketed portion with the value of the meta variable.

To perform math inside an AnnotatedString, surround the formula with two curly braces
(e.g. ``{{floor(dexterityMod+spell)}}``).

IntExpression
-------------
An IntExpression is similar to an AnnotatedString in its ability to use variables and functions. However, it has the
following differences:

- Curly braces around the expression are not required
- An IntExpression can only contain one expression
- The result of an IntExpression must be an integer.

These are valid IntExpressions:

- ``8 + proficiencyBonus + dexterityMod``
- ``12``
- ``floor(level / 2)``

These are *not* valid IntExpressions:

- ``1d8``
- ``DC {8 + proficiencyBonus + dexterityMod}``


Examples
--------

Attack
^^^^^^

A normal attack:

.. code-block:: json

    [
      {
        "type": "target",
        "target": "each",
        "effects": [
          {
            "type": "attack",
            "attackBonus": "dexterityMod + proficiencyBonus",
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

Save
^^^^

A spell that requires a Dexterity save for half damage:

.. code-block:: json

    [
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
      },
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
        ]
      },
      {
        "type": "text",
        "text": "Each creature in a 20-foot radius must make a Dexterity saving throw. A target takes 8d6 fire damage on a failed save, or half as much damage on a successful one."
      }
    ]

Attack & Save
^^^^^^^^^^^^^

An attack from a poisoned blade:

.. code-block:: json

    [
      {
        "type": "target",
        "target": "each",
        "effects": [
          {
            "type": "attack",
            "attackBonus": "strengthMod + proficiencyBonus",
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

Draining Attack
^^^^^^^^^^^^^^^

An attack that heals the caster for half the amount of damage dealt:

.. code-block:: json

    [
      {
        "type": "variable",
        "name": "lastDamage",
        "value": "0"
      },
      {
        "type": "target",
        "target": "each",
        "effects": [
          {
            "type": "attack",
            "attackBonus": "charismaMod + proficiencyBonus",
            "hit": [
              {
                "type": "damage",
                "damage": "3d6[necrotic]"
              }
            ],
            "miss": []
          }
        ]
      },
      {
        "type": "target",
        "target": "self",
        "effects": [
          {
            "type": "damage",
            "damage": "-{lastDamage}/2 [heal]"
          }
        ]
      },
      {
        "type": "text",
        "text": "On a hit, the target takes 3d6 necrotic damage, and you regain hit points equal to half the amount of necrotic damage dealt."
      }
    ]

Target Health-Based
^^^^^^^^^^^^^^^^^^^

A spell that does different amounts of damage based on whether or not the target is damaged:

.. code-block:: json

    [
      {
        "type": "target",
        "target": "each",
        "effects": [
          {
            "type": "save",
            "stat": "wis",
            "fail": [
              {
                "type": "condition",
                "condition": "target.hp < target.max_hp",
                "onTrue": [
                  {
                    "type": "damage",
                    "damage": "1d8 [necrotic]"
                  }
                ],
                "onFalse": [
                  {
                    "type": "damage",
                    "damage": "1d4 [necrotic]"
                  }
                ],
                "errorBehaviour": "both"
              }
            ],
            "success": []
          }
        ]
      },
      {
        "type": "text",
        "text": "The target must succeed on a Wisdom saving throw or take 1d4 necrotic damage. If the target is missing any of its hit points, it instead takes 1d8 necrotic damage."
      }
    ]

Area Vampiric Drain
^^^^^^^^^^^^^^^^^^^

An effect that heals the caster for the total damage dealt to all targets:

.. code-block:: json

    [
      {
        "type": "variable",
        "name": "totalDamage",
        "value": "0"
      },
      {
        "type": "target",
        "target": "each",
        "effects": [
          {
            "type": "damage",
            "damage": "1d6 [necrotic]"
          },
          {
            "type": "variable",
            "name": "totalDamage",
            "value": "totalDamage + lastDamage"
          }
        ]
      },
      {
        "type": "target",
        "target": "self",
        "effects": [
          {
            "type": "damage",
            "damage": "-{totalDamage} [heal]"
          }
        ]
      },
      {
        "type": "text",
        "text": "Each creature within 10 feet of you takes 1d6 necrotic damage. You regain hit points equal to the sum of the necrotic damage dealt."
      }
    ]

Damage Over Time Effect
^^^^^^^^^^^^^^^^^^^^^^^

An effect that lights the target on fire, adding two buttons on their turn to take the fire damage and douse themselves.

.. code-block::

    [
      {
        "type": "target",
        "target": "each",
        "effects": [
          {
            "type": "ieffect2",
            "name": "Burning",
            "buttons": [
              {
                "label": "Burning",
                "verb": "is on fire",
                "style": "4",
                "automation": [
                  {
                    "type": "target",
                    "target": "self",
                    "effects": [
                      {
                        "type": "damage",
                        "damage": "1d6 [fire]"
                      }
                    ]
                  },
                  {
                    "type": "text",
                    "text": "At the start of each of the target's turns, the target takes 1d6 fire damage."
                  }
                ]
              },
              {
                "label": "Douse",
                "verb": "puts themself out",
                "automation": [
                  {
                    "type": "remove_ieffect"
                  },
                  {
                    "type": "text",
                    "text": "The target can use an action to put themselves out."
                  }
                ]
              }
            ]
          }
        ]
      }
    ]


.. _attack-structure:

Custom Attack Structure
-----------------------

.. code-block:: typescript

    {
        _v: 2;
        name: string;
        automation: Effect[];
        verb?: string;
        proper?: boolean;
        criton?: number;
        phrase?: string;
        thumb?: string;
        extra_crit_damage?: string;
        activation_type?: number;
    }

In order to use Automation, it needs to be contained within a custom attack or spell. We recommend building these on
the `Avrae Dashboard <https://avrae.io/dashboard/characters>`_, but if you wish to write a custom attack by hand, the
structure is documented here.

Hand-written custom attacks may be written in JSON or YAML and imported using the ``!a import`` command.

.. class:: AttackModel

    .. attribute:: _v

        This must always be set to ``2``.

    .. attribute:: name

        The name of the attack.

    .. attribute:: automation

        The automation of the attack: a list of effects (documented above).

    .. attribute:: verb

        *optional, default "attacks with"* - The verb to use in attack title displays.

    .. attribute:: proper

        *optional, default false* - Whether or not the attack's name is a proper noun. Affects title displays.

    .. attribute:: criton

        *optional* - The natural roll (or higher) this attack should crit on. For example, ``criton: 18`` would cause
        this attack to crit on a natural roll of 18, 19, or 20.

    .. attribute:: phrase

        *optional* - A short snippet of flavor text to display when this attack is used.

    .. attribute:: thumb

        *optional* - A URL to an image to display in a thumbnail when this attack is used.

    .. attribute:: extra_crit_damage

        *optional* - How much extra damage to deal when this attack crits, in addition to normal crit rules such as
        doubling damage dice. For example, if this attack normally deals 1d6 damage with ``extra_crit_damage: "1d8"``,
        it will deal 2d6 + 1d8 damage on a crit.

    .. attribute:: activation_type

        *optional* - What action type to display this attack as in an action list (such as ``!a list``).

        .. code-block:: text

            ACTION = 1
            NO_ACTION = 2
            BONUS_ACTION = 3
            REACTION = 4
            MINUTE = 6
            HOUR = 7
            SPECIAL = 8
            LEGENDARY = 9
            MYTHIC = 10
            LAIR = 11

.. _class_feature_dc_impl:

Specifying Class Feature DC Bonuses
----------------------------------------
.. versionadded:: 4.1.0

Many official class automations let you specify a DC bonus that is added to the class feature's DC. For example, to add a bonus to all of your Fighter's Battlemaster Maneuvers, you can set a ``FighterDCBonus`` cvar and add it to the DC of all of your maneuvers.

For more details on using this, see :any:`class_feature_dc`

To account for this in your automations, use the :ref:`set-variable` node, with a value of ``XDCBonus`` and an onError of 0.

.. code-block::

    {
      "type": "variable",
      "name": "BloodHunterDCBonus",
      "value": "BloodHunterDCBonus",
      "onError": "0"
    }

Then, when you set your save DC's in that automation, add ``+XDCBonus`` to the DC total.

.. code-block::

    {
        "type": "save",
        "stat": "str",
        "dc": "8+proficiencyBonus+intelligenceMod+BloodHunterDCBonus",
        "fail": [],
        "success": []
    }
