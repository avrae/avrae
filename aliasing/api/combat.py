from typing import Optional

from d20 import roll

from aliasing.api.functions import SimpleRollResult
from aliasing.api.statblock import AliasStatBlock
from cogs5e.models.errors import InvalidSaveType
from cogs5e.models.initiative import Combat, CombatNotFound, Combatant, CombatantGroup, CombatantType, Effect
from cogs5e.models.sheet.statblock import StatBlock
from utils.argparser import ParsedArguments

MAX_METADATA_SIZE = 100000


# noinspection PyProtectedMember
class SimpleCombat:
    def __init__(self, combat, me):
        self._combat: Combat = combat

        self.combatants = [SimpleCombatant(c) for c in combat.get_combatants()]
        self.groups = [SimpleGroup(c) for c in combat.get_groups()]
        if me:
            self.me = SimpleCombatant(me, False)
        else:
            self.me = None
        self.round_num = self._combat.round_num
        self.turn_num = self._combat.turn_num
        current = self._combat.current_combatant
        if current:
            if isinstance(current, CombatantGroup):
                self.current = SimpleGroup(current)
            else:
                self.current = SimpleCombatant(current)
        else:
            self.current = None
        self.name = self._combat.options.get('name')

    @classmethod
    def from_ctx(cls, ctx):
        try:
            combat = Combat.from_ctx_sync(ctx)
        except CombatNotFound:
            return None
        return cls(combat, None)

    # public methods
    def get_combatant(self, name):
        """
        Gets a :class:`~aliasing.api.combat.SimpleCombatant`, fuzzy searching (partial match) on name.

        :param str name: The name of the combatant to get.
        :return: The combatant.
        :rtype: :class:`~aliasing.api.combat.SimpleCombatant`
        """
        name = str(name)
        combatant = self._combat.get_combatant(name, False)
        if combatant:
            return SimpleCombatant(combatant)
        return None

    def get_group(self, name):
        """
        Gets a :class:`~aliasing.api.combat.SimpleGroup`, fuzzy searching (partial match) on name.

        :param str name: The name of the group to get.
        :return: The group.
        :rtype: :class:`~aliasing.api.combat.SimpleGroup`
        """
        name = str(name)
        group = self._combat.get_group(name, strict=False)
        if group:
            return SimpleGroup(group)
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
        previous_metadata_size = sum(len(ke) + len(va) for ke, va in self._combat._metadata.items() if ke != key)
        new_metadata_size = len(key) + len(value)
        if previous_metadata_size + new_metadata_size > MAX_METADATA_SIZE:
            raise ValueError("Combat metadata is too large")
        self._combat._metadata[key] = value

    def get_metadata(self, k: str, default=None) -> str:
        """
        Gets a metadata value for the passed key or returns *default* if the name is not set.

        :param str k: The metadata key to get
        :param default: What to return if the name is not set.

        >>> get_metadata("Test")
        '{"Status": ["Mario", 1, 2]}'
        """
        return self._combat._metadata.get(str(k), default)

    def delete_metadata(self, k: str) -> Optional[str]:
        """
        Removes a key from the metadata.

        :param str k: The metadata key to remove
        :return: The removed value or ``None`` if the key is not found.
        :rtype: str or None

        >>> delete_metadata("Test")
        '{"Status": ["Mario", 1, 2]}'
        """
        return self._combat._metadata.pop(str(k), None)

    # private functions
    def func_set_character(self, character):
        me = next((c for c in self._combat.get_combatants() if getattr(c, 'character_id', None) == character.upstream),
                  None)
        if not me:
            return
        me._character = character  # set combatant character instance
        self.me = SimpleCombatant(me, False)

    async def func_commit(self):
        await self._combat.commit()

    def __str__(self):
        return str(self._combat)

    def __repr__(self):
        return f"<{self.__class__.__name__}>"


# noinspection PyProtectedMember
class SimpleCombatant(AliasStatBlock):
    """
    Represents a combatant in combat.
    """

    def __init__(self, combatant: Combatant, hidestats=True):
        super().__init__(combatant)
        self._combatant = combatant
        self._hidden = hidestats and self._combatant.is_private
        self.type = "combatant"

        self.initmod = int(self._combatant.init_skill)
        self.init = self._combatant.init
        self._update_effects()
        # Type-specific Properties
        self._race = None
        self._monster_name = None

        if combatant.type == CombatantType.MONSTER:
            self._creature_type = combatant._creature_type
            self._monster_name = combatant.monster_name
        elif combatant.type == CombatantType.PLAYER:
            self._race = combatant.character.race
        # deprecated drac 2.1
        self.resists = self.resistances  # use .resistances instead
        self.level = self._combatant.spellbook.caster_level  # use .spellbook.caster_level or .levels.total_level instead

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
        return int(self._combatant.controller)

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
    def creature_type(self):
        """
        The creature type of the combatant. Will return None for players or combatants with no creature type.

        :rtype: str or None
        """
        return self._creature_type

    @property
    def monster_name(self):
        """
        The monster name of the combatant. Will return None for players.

        :rtype: str or None
        """
        return self._monster_name

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

        sb = self._combatant.active_effects('sb')
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
        from cogs5e.models.automation import AutomationContext, AutomationTarget, \
            Damage  # this has to be here to avoid circular imports

        dice_str, critdice = str(dice_str), int(critdice)
        if d is not None:
            d = str(d)
        if c is not None:
            c = str(c)

        class _SimpleAutomationContext(AutomationContext):
            def __init__(self, caster, target, args, combat, crit=False):
                super(_SimpleAutomationContext, self).__init__(None, None, caster, [target], args, combat)
                self.in_crit = crit
                self.target = AutomationTarget(target)

        args = ParsedArguments.from_dict({
            'critdice': [critdice],
            'resist': self._combatant.resistances['resist'],
            'immune': self._combatant.resistances['immune'],
            'vuln': self._combatant.resistances['vuln']
        })
        if d:
            args['d'] = d
        if c:
            args['c'] = c
        damage = Damage(dice_str, overheal=overheal)
        autoctx = _SimpleAutomationContext(StatBlock("generic"), self._combatant, args, self._combatant.combat, crit)

        result = damage.run(autoctx)
        roll_for = "Damage" if not result.in_crit else "Damage (CRIT!)"
        return {'damage': f"**{roll_for}**: {result.damage_roll.result}", 'total': result.damage,
                'roll': SimpleRollResult(result.damage_roll)}

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

        return SimpleGroup(group)

    def set_note(self, note: str):
        """
        Sets the combatant's note.

        :param str note: The new note.
        """
        if note is not None:
            note = str(note)
        self._combatant.notes = note

    def get_effect(self, name: str):
        """
        Gets a SimpleEffect, fuzzy searching (partial match) for a match.

        :param str name: The name of the effect to get.
        :return: The effect.
        :rtype: :class:`~aliasing.api.combat.SimpleEffect`
        """
        name = str(name)
        effect = self._combatant.get_effect(name, False)
        if effect:
            return SimpleEffect(effect)
        return None

    def add_effect(self, name: str, args: str, duration: int = -1, concentration: bool = False, parent=None,
                   end: bool = False, desc: str = None):
        """
        Adds an effect to the combatant.

        :param str name: The name of the effect to add.
        :param str args: The effect arguments to add (same syntax as [!init effect](https://avrae.io/commands#init-effect)).
        :param int duration: The duration of the effect, in rounds.
        :param bool concentration: Whether the effect requires concentration.
        :param parent: The parent of the effect.
        :type parent: :class:`~aliasing.api.combat.SimpleEffect`
        :param bool end: Whether the effect ticks on the end of turn.
        :param str desc: A description of the effect.
        """  # noqa: E501
        name, args, duration = str(name), str(args), int(duration)
        if desc is not None:
            desc = str(desc)

        existing = self._combatant.get_effect(name, True)
        if existing:
            existing.remove()
        effectObj = Effect.new(self._combatant.combat, self._combatant, duration=duration, name=name, effect_args=args,
                               concentration=concentration, tick_on_end=end, desc=desc)
        if parent:
            effectObj.set_parent(parent._effect)
        self._combatant.add_effect(effectObj)
        self._update_effects()

    def remove_effect(self, name: str):
        """
        Removes an effect from the combatant, fuzzy searching on name. If not found, does nothing.

        :param str name: The name of the effect to remove.
        """
        name = str(name)
        effect = self._combatant.get_effect(name, strict=False)
        if effect:
            effect.remove()
            self._update_effects()

    def __str__(self):
        return str(self._combatant)

    # === utility ====
    def _update_effects(self):
        self.effects = [SimpleEffect(e) for e in self._combatant.get_effects()]

    # === deprecated ===
    @property
    def temphp(self):  # deprecated - use temp_hp instead
        """
        .. deprecated:: 2.5.0
            Use ``SimpleCombatant.temp_hp`` instead.

        How many temporary hit points the combatant has.

        :rtype: int
        """
        return self.temp_hp

    @property
    def maxhp(self):  # deprecated - use max_hp instead
        """
        .. deprecated:: 2.5.0
            Use ``SimpleCombatant.max_hp`` instead.

        The combatant's maximum hit points. ``None`` if not set.

        :rtype: Optional[int]
        """
        return self.max_hp

    def mod_hp(self, mod: int, overheal: bool = False):  # deprecated - use modify_hp instead
        """
        .. deprecated:: 2.5.0
            Use ``SimpleCombatant.modify_hp()`` instead.

        Modifies a combatant's remaining hit points by a value.

        :param int mod: The amount of HP to add.
        :param bool overheal: Whether to allow exceeding max HP.
        """
        self.modify_hp(mod, overflow=overheal)

    def set_thp(self, thp: int):  # deprecated - use set_temp_hp
        """
        .. deprecated:: 2.5.0
            Use ``SimpleCombatant.set_temp_hp()`` instead.

        Sets the combatant's temp HP.

        :param int thp: The new temp HP.
        """
        self.set_temp_hp(thp)

    def wouldhit(self, to_hit: int):
        """
        .. deprecated:: 1.1.5
            Use ``to_hit >= combatant.ac`` instead.

        Checks if a roll would hit this combatant.

        :param int to_hit: The rolled total.
        :return: Whether the total would hit.
        :rtype: bool
        """
        if self._combatant.ac:
            return to_hit >= self._combatant.ac
        return None


class SimpleGroup:
    def __init__(self, group: CombatantGroup):
        self._group = group
        self.type = "group"
        self.combatants = [SimpleCombatant(c) for c in self._group.get_combatants()]

    @property
    def name(self):
        """
        The name of the group.

        :rtype: str
        """
        return self._group.name

    def get_combatant(self, name):
        """
        Gets a :class:`~aliasing.api.combat.SimpleCombatant`, fuzzy searching (partial match) on name.

        :param str name: The name of the combatant to get.
        :return: The combatant.
        :rtype: :class:`~aliasing.api.combat.SimpleCombatant`
        """
        name = str(name)
        combatant = next((c for c in self.combatants if name.lower() in c.name.lower()), None)
        if combatant:
            return combatant
        return None

    def __str__(self):
        return str(self._group)

    def __repr__(self):
        return f"<{self.__class__.__name__} combatants={self.combatants!r}>"


class SimpleEffect:
    def __init__(self, effect: Effect):
        self._effect = effect

        self.name = self._effect.name
        self.duration = self._effect.duration
        self.remaining = self._effect.remaining
        self.effect = self._effect.effect
        self.conc = self._effect.concentration
        self.desc = self._effect.desc
        self.ticks_on_end = self._effect.ticks_on_end
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
        self._effect.set_parent(parent._effect)

    def __str__(self):
        return str(self._effect)

    def __repr__(self):
        return f"<{self.__class__.__name__} name={self.name!r} duration={self.duration!r} remaining={self.remaining!r}>"

    def __eq__(self, other):
        return isinstance(other, SimpleEffect) and self._effect is other._effect
