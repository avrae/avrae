from typing import Optional, TYPE_CHECKING

from d20 import roll

import cogs5e.initiative as init
from aliasing.api.functions import SimpleRollResult
from aliasing.api.statblock import AliasStatBlock
from cogs5e.models.errors import InvalidSaveType
from cogs5e.models.sheet.statblock import StatBlock
from utils.argparser import ParsedArguments
from . import validators

if TYPE_CHECKING:
    from ..evaluators import ScriptingEvaluator

MAX_METADATA_SIZE = 100000


# noinspection PyProtectedMember
class SimpleCombat:
    def __init__(self, combat: init.Combat, me: Optional[init.Combatant], interpreter: "ScriptingEvaluator" = None):
        self._combat = combat
        self._interpreter = interpreter

        self.combatants = [SimpleCombatant(c, interpreter=interpreter) for c in combat.get_combatants()]
        self.groups = [SimpleGroup(c, interpreter=interpreter) for c in combat.get_groups()]
        if me:
            self.me = SimpleCombatant(me, interpreter=interpreter, hidestats=False)
        else:
            self.me = None
        self.round_num = self._combat.round_num
        self.turn_num = self._combat.turn_num
        current = self._combat.current_combatant
        if current:
            if current.type == init.CombatantType.GROUP:  # isinstance(current, init.CombatantGroup):
                self.current = SimpleGroup(current, interpreter=interpreter)
            else:
                self.current = SimpleCombatant(current, interpreter=interpreter)
        else:
            self.current = None
        self.name = self._combat.options.name

    @classmethod
    def from_ctx(cls, ctx, interpreter=None):
        try:
            combat = init.Combat.from_ctx_sync(ctx)
        except init.CombatNotFound:
            return None
        return cls(combat, None, interpreter=interpreter)

    # public methods
    def get_combatant(self, name, strict=None):
        """
        Gets a combatant by its name or ID.

        :param str name: The name or id of the combatant or group to get.
        :param strict: Whether combatant name must be a full case insensitive match.
            If this is ``None`` (default), attempts a strict match with fallback to partial match.
            If this is ``False``, it returns the first partial match.
            If this is ``True``, it will only return a strict match.
        :return: The combatant or group or None.
        :rtype: :class:`~aliasing.api.combat.SimpleCombatant` or `~aliasing.api.combat.SimpleGroup`
        """
        name = str(name)
        combatant = self._combat.get_combatant(name, strict)
        if combatant:
            if combatant.type == init.CombatantType.GROUP:
                return SimpleGroup(combatant, interpreter=self._interpreter)
            else:
                return SimpleCombatant(combatant, interpreter=self._interpreter)
        return None

    def get_group(self, name, strict=None):
        """
        Gets a :class:`~aliasing.api.combat.SimpleGroup` that matches on name.

        :param str name: The name of the group to get.
        :param strict: Whether combatant name must be a full case insensitive match.
            If this is ``None`` (default), attempts a strict match with fallback to partial match.
            If this is ``False``, it returns the first partial match.
            If this is ``True``, it will only return a strict match.
        :return: The group or None.
        :rtype: :class:`~aliasing.api.combat.SimpleGroup`
        """
        name = str(name)
        group = self._combat.get_group(name, strict)
        if group:
            return SimpleGroup(group, interpreter=self._interpreter)
        return None

    def set_metadata(self, k: str, v: str):
        """
        Assigns a metadata key to the passed value.
        Maximum size of the metadata is 100k characters, key and item inclusive.

        :param str k: The metadata key to set
        :param str v: The metadata value to set

        >>> set_metadata("Test", dump_json({"Status": ["Mario", 1, 2]}))
        """
        key = str(k)
        value = str(v)
        previous_metadata_size = sum(len(ke) + len(va) for ke, va in self._combat.metadata.items() if ke != key)
        new_metadata_size = len(key) + len(value)
        if previous_metadata_size + new_metadata_size > MAX_METADATA_SIZE:
            raise ValueError("Combat metadata is too large")
        self._combat.metadata[key] = value

    def get_metadata(self, k: str, default=None) -> str:
        """
        Gets a metadata value for the passed key or returns *default* if the name is not set.

        :param str k: The metadata key to get
        :param default: What to return if the name is not set.

        >>> get_metadata("Test")
        '{"Status": ["Mario", 1, 2]}'
        """
        return self._combat.metadata.get(str(k), default)

    def delete_metadata(self, k: str) -> Optional[str]:
        """
        Removes a key from the metadata.

        :param str k: The metadata key to remove
        :return: The removed value or ``None`` if the key is not found.
        :rtype: str or None

        >>> delete_metadata("Test")
        '{"Status": ["Mario", 1, 2]}'
        """
        return self._combat.metadata.pop(str(k), None)

    def set_round(self, round_num: int):
        """
        Sets the current round.
        Setting the round will not tick any events with durations.

        :param int round_num: the new round number
        """
        if not isinstance(round_num, int):
            raise ValueError("Round_num must be an integer.")
        self._combat.round_num = round_num

    def end_round(self):
        """
        Moves initiative to just before the next round (no active combatant or group).
        Ending the round will not tick any events with durations.
        """
        self._combat.end_round()

    # private functions
    def func_set_character(self, character):
        me = next(
            (c for c in self._combat.get_combatants() if getattr(c, "character_id", None) == character.upstream), None
        )
        if not me:
            return
        me._character = character  # set combatant character instance
        self.me = SimpleCombatant(me, interpreter=self._interpreter, hidestats=False)

    async def func_commit(self, ctx):
        await self._combat.commit(ctx)

    def __str__(self):
        return str(self._combat)

    def __repr__(self):
        return f"<{self.__class__.__name__}>"


# noinspection PyProtectedMember
class SimpleCombatant(AliasStatBlock):
    """
    Represents a combatant in combat.
    """

    def __init__(self, combatant: init.Combatant, interpreter: "ScriptingEvaluator", hidestats: bool = True):
        super().__init__(combatant)
        self._combatant = combatant
        self._hidden = hidestats and self._combatant.is_private
        self._interpreter = interpreter
        self.type = "combatant"

        self.initmod = int(self._combatant.init_skill)
        self.init = self._combatant.init
        self._update_effects()
        # Type-specific Properties
        self._race = None
        self._monster_name = None

        if combatant.type == init.CombatantType.MONSTER:
            self._monster_name = combatant.monster_name
        elif combatant.type == init.CombatantType.PLAYER:
            self._race = combatant.character.race

    @property
    def id(self):
        """
        The combatant's unique identifier.

        :rtype: str
        """
        return self._combatant.id

    @property
    def note(self):
        """
        The note on the combatant. ``None`` if not set.

        :rtype: str or None
        """
        return self._combatant.notes

    @property
    def controller(self):
        """
        The ID of the combatant's controller.

        :rtype: int
        """
        return self._combatant.controller_id

    @property
    def group(self):
        """
        The name of the group the combatant is in, or ``None`` if the combatant is not in a group.

        :rtype: str or None
        """
        group = self._combatant.get_group()
        return group.name if group else None

    @property
    def race(self):
        """
        The race of the combatant. Will return None for monsters or combatants with no race.

        :rtype: str or None
        """
        return self._race

    @property
    def monster_name(self):
        """
        The monster name of the combatant. Will return None for players.

        :rtype: str or None
        """
        return self._monster_name

    @property
    def is_hidden(self):
        """
        Whether the HP, AC, Resists, etc are hidden.

        :rtype: bool
        """
        return bool(self._hidden)

    def save(self, ability: str, adv: bool = None):
        """
        Rolls a combatant's saving throw.

        :param str ability: The type of save ("str", "dexterity", etc).
        :param bool adv: Whether to roll the save with advantage. Rolls with advantage if ``True``, disadvantage if ``False``, or normally if ``None``.
        :returns: A SimpleRollResult describing the rolled save.
        :rtype: :class:`~aliasing.api.functions.SimpleRollResult`
        """  # noqa: E501
        try:
            save = self._combatant.saves.get(str(ability))
        except ValueError:
            raise InvalidSaveType

        sb = self._combatant.active_effects(mapper=lambda effect: effect.effects.save_bonus, default=[])
        saveroll = save.d20(base_adv=adv)
        if sb:
            saveroll = f'{saveroll}+{"+".join(sb)}'

        save_roll = roll(saveroll)
        return SimpleRollResult(save_roll)

    def damage(self, dice_str, crit=False, d=None, c=None, critdice=0, overheal=False):
        """
        Does damage to a combatant, and returns the rolled result and total, accounting for resistances.

        :param str dice_str: The damage to do (e.g. ``"1d6[acid]"``).
        :param bool crit: Whether or not the damage should be rolled as a crit.
        :param str d: Any additional damage to add (equivalent of -d).
        :param str c: Any additional damage to add to crits (equivalent of -c).
        :param int critdice: How many extra weapon dice to roll on a crit (in addition to normal dice).
        :param bool overheal: Whether or not to allow this damage to exceed a target's HP max.
        :return: Dictionary representing the results of the Damage Automation.
        :rtype: dict
        """
        # this has to be here to avoid circular imports
        from cogs5e.models.automation import AutomationContext, AutomationTarget, Damage

        dice_str, critdice = str(dice_str), int(critdice)
        if d is not None:
            d = str(d)
        if c is not None:
            c = str(c)

        class _SimpleAutomationContext(AutomationContext):
            def __init__(self, caster, target, args, combat, crit=False):
                super().__init__(None, None, caster, [target], args, combat)
                self.in_crit = crit
                self.target = AutomationTarget(self, target)

        args = ParsedArguments.from_dict({"critdice": [critdice]})
        if d:
            args["d"] = d
        if c:
            args["c"] = c
        damage = Damage(dice_str, overheal=overheal)
        autoctx = _SimpleAutomationContext(StatBlock("generic"), self._combatant, args, self._combatant.combat, crit)

        result = damage.run(autoctx)
        roll_for = "Damage" if not result.in_crit else "Damage (CRIT!)"
        return {
            "damage": f"**{roll_for}**: {result.damage_roll.result}",
            "total": result.damage,
            "roll": SimpleRollResult(result.damage_roll),
        }

    def set_ac(self, ac: int):
        """
        Sets the combatant's armor class.

        :param int ac: The new AC.
        """
        if not isinstance(ac, int) and ac is not None:
            raise ValueError("AC must be an integer or None.")
        self._combatant.ac = ac

    def set_maxhp(self, maxhp: int):
        """
        Sets the combatant's max HP.

        :param int maxhp: The new max HP.
        """
        if not isinstance(maxhp, int) and maxhp is not None:
            raise ValueError("Max HP must be an integer or None.")
        self._combatant.max_hp = maxhp

    def set_init(self, init: int):
        """
        Sets the combatant's initiative roll.

        :param int init: The new initiative.
        """
        if not isinstance(init, int):
            raise ValueError("Initiative must be an integer.")
        self._combatant.init = init
        self._combatant.combat.sort_combatants()

    def set_name(self, name: str):
        """
        Sets the combatant's name.

        :param str name: The new name.
        """
        if not name:
            raise ValueError("Combatants must have a name.")
        self._combatant.name = str(name)

    def set_group(self, group):
        """
        Sets the combatant's group

        :param str group: The name of the group. None to remove from group.
        :return: The combatant's new group, or None if the combatant was removed from a group.
        :rtype: :class:`~aliasing.api.combat.SimpleGroup` or None
        """
        if group is not None:
            group = str(group)

        group = self._combatant.set_group(group_name=group)
        if group is None:
            return None

        return SimpleGroup(group, interpreter=self._interpreter)

    def set_note(self, note: str):
        """
        Sets the combatant's note.

        :param str note: The new note.
        """
        if note is not None:
            note = str(note)
        self._combatant.notes = note

    def get_effect(self, name: str, strict: bool = False):
        """
        Gets a SimpleEffect, fuzzy searching (partial match) for the first match or an exact match.

        :param str name: The name of the effect to get.
        :param bool strict: Whether effect name must be an exact match.
            If this is ``False``, it returns the first partial match.
            If this is ``True``, it will only return a strict match.
        :return: The effect.
        :rtype: :class:`~aliasing.api.combat.SimpleEffect`
        """
        name = str(name)
        effect = self._combatant.get_effect(name, strict)
        if effect:
            return SimpleEffect(effect)
        return None

    def add_effect(
        self,
        name: str,
        args: str = None,
        duration: int | None = None,
        concentration: bool = False,
        parent: "SimpleEffect" = None,
        end: bool = False,
        desc: str = None,
        passive_effects: dict = None,
        attacks: list[dict] = None,
        buttons: list[dict] = None,
        tick_on_combatant_id: str = None,
    ):
        """
        Adds an effect to the combatant. Returns the added effect.

        .. note::

            It is recommended to pass all arguments other than *name* to this method as keyword arguments (i.e.
            ``add_effect("On Fire", duration=10)``). This is not strictly enforced for backwards-compatibility.

        .. warning::

            The *args* argument is deprecated as of v4.1.0. Use *passive_effects* instead.

        :param str name: The name of the effect to add.
        :param str args: The effect arguments to add (same syntax as `!init effect <https://avrae.io/commands#init-effect>`_).
        :param int duration: The duration of the effect, in rounds. Pass ``None`` for indefinite.
        :param bool concentration: Whether the effect requires concentration.
        :param parent: The parent of the effect.
        :type parent: :class:`~aliasing.api.combat.SimpleEffect`
        :param bool end: Whether the effect ends on the end of turn.
        :param str desc: A description of the effect.
        :param passive_effects: The passive effects this effect should grant. See :ref:`ieffectargs`.
        :param attacks: The attacks granted by this effect. See :ref:`ieffectargs`.
        :param buttons: The buttons granted by this effect. See :ref:`ieffectargs`.
        :param tick_on_combatant_id: The ID of the combatant whose turn the effect duration ticks on (defaults to the combatant who the effect is on).
        :rtype: :class:`~aliasing.api.combat.SimpleEffect`
        """  # noqa: E501
        # validate types
        name = str(name)
        if args is not None:
            args = str(args)
            self._interpreter.warn_deprecated(
                "SimpleCombatant.add_effect#args",
                since="v4.1.0",
                replacement="SimpleCombatant.add_effect#passive_effects",
            )
        if duration is not None:
            duration = int(duration)
        if parent is not None and not isinstance(parent, SimpleEffect):
            raise ValueError("The parent of a SimpleEffect must be a SimpleEffect.")
        if desc is not None:
            desc = str(desc)
        if tick_on_combatant_id is not None:
            tick_on_combatant_id = str(tick_on_combatant_id)

        # parse v4.1 models (passive, attacks, buttons)
        parsed_passive = parsed_attacks = parsed_buttons = None
        if passive_effects:
            unsafeified_passive = validators.unsafeify(passive_effects, self._interpreter)
            normalized_passive = validators.PassiveEffects.parse_obj(unsafeified_passive).dict(exclude_none=True)
            parsed_passive = init.effects.InitPassiveEffect.from_dict(normalized_passive)
        if attacks:
            normalized_attacks = [
                validators.AttackInteraction.parse_obj(a) for a in validators.unsafeify(attacks, self._interpreter)
            ]
            parsed_attacks = [
                init.effects.AttackInteraction.from_dict(a.dict(exclude_none=True)) for a in normalized_attacks
            ]
        if buttons:
            normalized_buttons = [
                validators.ButtonInteraction.parse_obj(b) for b in validators.unsafeify(buttons, self._interpreter)
            ]
            parsed_buttons = [
                init.effects.ButtonInteraction.from_dict(
                    {**b.dict(exclude_none=True), "id": init.utils.create_button_interaction_id()}
                )
                for b in normalized_buttons
            ]

        # add effect
        existing = self._combatant.get_effect(name, True)
        if existing:
            existing.remove()
        effect_obj = init.InitiativeEffect.new(
            combat=self._combatant.combat,
            combatant=self._combatant,
            name=name,
            effect_args=args,
            duration=duration,
            end_on_turn_end=end,
            concentration=concentration,
            desc=desc,
            passive_effects=parsed_passive,
            attacks=parsed_attacks,
            buttons=parsed_buttons,
            tick_on_combatant_id=tick_on_combatant_id,
        )
        if parent:
            effect_obj.set_parent(parent._effect)
        self._combatant.add_effect(effect_obj)
        self._update_effects()

        return SimpleEffect(effect_obj)

    def remove_effect(self, name: str, strict: bool = False):
        """
        Removes an effect from the combatant, fuzzy searching on name or an exact match. If not found, does nothing.

        :param str name: The name of the effect to remove.
        :param bool strict: Whether effect name must be an exact match.
            If this is ``False``, it returns the first partial match.
            If this is ``True``, it will only return a strict match.
        """
        name = str(name)
        effect = self._combatant.get_effect(name, strict)
        if effect:
            effect.remove()
            self._update_effects()

    def __str__(self):
        return str(self._combatant)

    # === utility ====
    def _update_effects(self):
        self.effects = [SimpleEffect(e) for e in self._combatant.get_effects()]


class SimpleGroup:
    def __init__(self, group: init.CombatantGroup, interpreter: "ScriptingEvaluator"):
        self._group = group
        self._interpreter = interpreter
        self.type = "group"
        self.combatants = [SimpleCombatant(c, interpreter=interpreter) for c in self._group.get_combatants()]
        self.init = self._group.init

    @property
    def name(self):
        """
        The name of the group.

        :rtype: str
        """
        return self._group.name

    @property
    def id(self):
        """
        The group's unique identifier.

        :rtype: str
        """
        return self._group.id

    def get_combatant(self, name, strict=None):
        """
        Gets a :class:`~aliasing.api.combat.SimpleCombatant` from the group.

         :param str name: The name of the combatant to get.
         :param strict: Whether combatant name must be a full case insensitive match.
             If this is ``None`` (default), attempts a strict match with fallback to partial match.
             If this is ``False``, it returns the first partial match.
             If this is ``True``, it will only return a strict match.
         :return: The combatant or None.
         :rtype: :class:`~aliasing.api.combat.SimpleCombatant`
        """
        name = str(name)
        combatant = None

        if strict is not False:
            combatant = next((c for c in self.combatants if name.lower() == c.name.lower()), None)
        if not combatant and not strict:
            combatant = next((c for c in self.combatants if name.lower() in c.name.lower()), None)
        return combatant

    def set_init(self, init: int):
        """
        Sets the group's initiative roll.

        :param int init: The new initiative.
        """
        if not isinstance(init, int):
            raise ValueError("Initiative must be an integer.")
        self._group.init = init
        self._group.combat.sort_combatants()

    def __str__(self):
        return str(self._group)

    def __repr__(self):
        return f"<{self.__class__.__name__} combatants={self.combatants!r}>"


class SimpleEffect:
    def __init__(self, effect: init.InitiativeEffect):
        self._effect = effect

        self.name = self._effect.name
        self.duration = self._effect.duration
        self.remaining = self._effect.remaining
        self.effect = self._effect.effects.to_dict()
        self.attacks = [i.to_dict() for i in self._effect.attacks]
        self.buttons = [i.to_dict() for i in self._effect.buttons]
        self.conc = self._effect.concentration
        self.desc = self._effect.desc
        self.ticks_on_end = self._effect.end_on_turn_end
        self.combatant_name = self._effect.combatant.name
        self._parent = None
        self._children = None

    @property
    def parent(self):
        """
        Gets the parent effect of this effect, or ``None`` if this effect has no parent.

        :rtype: :class:`~aliasing.api.combat.SimpleEffect` or None
        """
        if self._parent is None:
            the_parent = self._effect.parent
            if the_parent is not None:
                self._parent = SimpleEffect(self._effect.get_parent_effect())
        return self._parent

    @property
    def children(self):
        """
        Gets the child effects of this effect.

        :rtype: list of :class:`~aliasing.api.combat.SimpleEffect`
        """
        if self._children is None:
            self._children = [SimpleEffect(e) for e in self._effect.get_children_effects()]
        return self._children

    def set_parent(self, parent):
        """
        Sets the parent effect of this effect.

        :param parent: The parent.
        :type parent: :class:`~aliasing.api.combat.SimpleEffect`
        """
        if not isinstance(parent, SimpleEffect):
            raise TypeError(f"Parent effect must be a SimpleEffect, not {type(parent).__name__}")
        self._effect.set_parent(parent._effect)

    def __str__(self):
        return str(self._effect)

    def __repr__(self):
        return f"<{self.__class__.__name__} name={self.name!r} duration={self.duration!r} remaining={self.remaining!r}>"

    def __eq__(self, other):
        return isinstance(other, SimpleEffect) and self._effect is other._effect
