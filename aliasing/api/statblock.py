class AliasStatBlock:
    """
    A base class representing any creature (player or otherwise) that has stats.

    Generally, these are never directly used - notable subclasses are :class:`~aliasing.api.combat.SimpleCombatant`
    and :class:`~aliasing.api.character.AliasCharacter`.
    """

    def __init__(self, statblock):
        """
        :type statblock: cogs5e.models.sheet.statblock.StatBlock
        """
        self._statblock = statblock
        # memoize some attrs
        self._stats = None
        self._levels = None
        self._attacks = None
        self._skills = None
        self._saves = None
        self._resistances = None
        self._spellbook = None

    @property
    def name(self):
        """
        The name of the creature.

        :rtype: str
        """
        return self._statblock.name

    @property
    def stats(self):
        """
        The stats of the creature.

        :rtype: :class:`~aliasing.api.statblock.AliasBaseStats`
        """
        if self._stats is None:
            self._stats = AliasBaseStats(self._statblock.stats)
        return self._stats

    @property
    def levels(self):
        """
        The levels of the creature.

        :rtype: :class:`~aliasing.api.statblock.AliasLevels`
        """
        if self._levels is None:
            self._levels = AliasLevels(self._statblock.levels)
        return self._levels

    @property
    def attacks(self):
        """
        The attacks of the creature.

        :rtype: :class:`~aliasing.api.statblock.AliasAttackList`
        """
        if self._attacks is None:
            self._attacks = AliasAttackList(self._statblock.attacks, self._statblock)
        return self._attacks

    @property
    def skills(self):
        """
        The skills of the creature.

        :rtype: :class:`~aliasing.api.statblock.AliasSkills`
        """
        if self._skills is None:
            self._skills = AliasSkills(self._statblock.skills)
        return self._skills

    @property
    def saves(self):
        """
        The saves of the creature.

        :rtype: :class:`~aliasing.api.statblock.AliasSaves`
        """
        if self._saves is None:
            self._saves = AliasSaves(self._statblock.saves)
        return self._saves

    @property
    def resistances(self):
        """
        The resistances, immunities, and vulnerabilities of the creature.

        :rtype: :class:`~aliasing.api.statblock.AliasResistances`
        """
        if self._resistances is None:
            self._resistances = AliasResistances(self._statblock.resistances)
        return self._resistances

    @property
    def ac(self):
        """
        The armor class of the creature.

        :rtype: int or None
        """
        return self._statblock.ac

    @property
    def max_hp(self):
        """
        The maximum HP of the creature.

        :rtype: int or None
        """
        return self._statblock.max_hp

    @property
    def hp(self):
        """
        The current HP of the creature.

        :rtype: int or None
        """
        return self._statblock.hp

    @property
    def temp_hp(self):
        """
        The current temp HP of the creature.

        :rtype: int
        """
        return self._statblock.temp_hp

    @property
    def spellbook(self):
        """
        The creature's spellcasting information.

        :rtype: :class:`~aliasing.api.statblock.AliasSpellbook`
        """
        if self._spellbook is None:
            self._spellbook = AliasSpellbook(self._statblock.spellbook)
        return self._spellbook

    # ---- hp ----
    def set_hp(self, new_hp):
        """
        Sets the creature's remaining HP.

        :param int new_hp: The amount of remaining HP (a nonnegative integer).
        """
        return self._statblock.set_hp(int(new_hp))

    def modify_hp(self, amount, ignore_temp=False, overflow=True):
        """
        Modifies the creature's remaining HP by a given amount.

        :param int amount: The amount of HP to add/remove.
        :param bool ignore_temp: If *amount* is negative, whether to damage temp HP first or ignore temp.
        :param bool overflow: If *amount* is positive, whether to allow overhealing or cap at the creature's max HP.
        """
        return self._statblock.modify_hp(int(amount), ignore_temp, overflow)

    def hp_str(self):
        """
        Returns a string describing the creature's current, max, and temp HP.

        :rtype: str
        """
        return self._statblock.hp_str()

    def reset_hp(self):
        """
        Heals a creature to max and removes any temp HP.
        """
        return self._statblock.reset_hp()

    def set_temp_hp(self, new_temp):
        """
        Sets a creature's temp HP.

        :param int new_temp: The new temp HP (a non-negative integer).
        """
        self._statblock.temp_hp = int(new_temp)

    # ---- __dunder__ ----
    def __repr__(self):
        return f"<AliasStatBlock name={self.name}>"


class AliasBaseStats:
    """
    Represents a statblock's 6 base ability scores and proficiency bonus.
    """

    def __init__(self, stats):
        """
        :type stats: cogs5e.models.sheet.base.BaseStats
        """
        self._stats = stats

    @property
    def prof_bonus(self):
        """
        The proficiency bonus.

        :rtype: int
        """
        return self._stats.prof_bonus

    @property
    def strength(self):
        """
        Strength score.

        :rtype: int
        """
        return self._stats.strength

    @property
    def dexterity(self):
        """
        Dexterity score.

        :rtype: int
        """
        return self._stats.dexterity

    @property
    def constitution(self):
        """
        Constitution score.

        :rtype: int
        """
        return self._stats.constitution

    @property
    def intelligence(self):
        """
        Intelligence score.

        :rtype: int
        """
        return self._stats.intelligence

    @property
    def wisdom(self):
        """
        Wisdom score.

        :rtype: int
        """
        return self._stats.wisdom

    @property
    def charisma(self):
        """
        Charisma score.

        :rtype: int
        """
        return self._stats.charisma

    def get_mod(self, stat: str):
        """
        Gets the modifier for a base stat (str, dex, con, etc). Does *not* take skill check bonuses into account.

        For the skill check modifier, use ``StatBlock.skills.strength`` etc.

        :param str stat: The stat to get the modifier for.
        :rtype: int
        """
        return self._stats.get_mod(str(stat))

    def __str__(self):
        return str(self._stats)


class AliasLevels:
    """
    Represents a statblock's class levels.
    """

    def __init__(self, levels):
        """
        :type levels: cogs5e.models.sheet.base.Levels
        """
        self._levels = levels

    @property
    def total_level(self):
        """
        The total level.

        :rtype: int
        """
        return self._levels.total_level

    def get(self, cls_name, default=0):
        """
        Gets the levels in a given class, or *default* if there are none.

        :param str cls_name: The name of the class to get the levels of.
        :param int default: What to return if the statblock does not have levels in the given class.
        :rtype: int
        """
        return self._levels.get(cls_name, default)

    def __iter__(self):
        return iter(self._levels)

    def __str__(self):
        return str(self._levels)


class AliasAttackList:
    """
    A container of a statblock's attacks.
    """

    def __init__(self, attack_list, parent_statblock):
        """
        :type attack_list: cogs5e.models.sheet.attack.AttackList
        :type parent_statblock: cogs5e.models.sheet.statblock.StatBlock
        """
        self._attack_list = attack_list
        self._parent_statblock = parent_statblock

    def __str__(self):
        return self._attack_list.build_str(self._parent_statblock)

    def __iter__(self):
        for atk in self._attack_list:
            yield AliasAttack(atk, self._parent_statblock)

    def __getitem__(self, item):
        return AliasAttack(self._attack_list[item], self._parent_statblock)

    def __len__(self):
        return len(self._attack_list)


class AliasAttack:
    """
    An attack.
    """

    def __init__(self, attack, parent_statblock):
        """
        :type attack: cogs5e.models.sheet.attack.Attack
        :type parent_statblock: cogs5e.models.sheet.statblock.StatBlock
        """
        self._attack = attack
        self._parent_statblock = parent_statblock

    @property
    def name(self):
        """
        The name of the attack.

        :rtype: str
        """
        return self._attack.name

    @property
    def verb(self):
        """
        The custom verb used for this attack, if applicable.

        :rtype: str or None
        """
        return self._attack.verb

    @property
    def proper(self):
        """
        Whether or not this attack is a proper noun.

        :rtype: bool
        """
        return self._attack.proper

    @property
    def raw(self):  # since we don't expose Automation models (yet)
        """
        A dict representing the raw value of this attack.

        :rtype: dict
        """
        return self._attack.to_dict()

    def __str__(self):
        return self._attack.build_str(self._parent_statblock)


class AliasSkill:
    """
    A skill modifier.
    """

    def __init__(self, skill):
        """
        :type skill: cogs5e.models.sheet.base.Skill
        """
        self._skill = skill

    @property
    def value(self):
        """
        The final modifier. Generally, ``value = (base stat mod) + (profBonus) * prof + bonus``.

        :rtype: int
        """
        return self._skill.value

    @property
    def prof(self):
        """
        The proficiency multiplier in this skill. 0 = no proficiency, 0.5 = JoAT, 1 = proficiency, 2 = expertise.

        :rtype: float or int
        """
        return self._skill.prof

    @property
    def bonus(self):
        """
        The miscellaneous bonus to the skill modifier.

        :rtype: int
        """
        return self._skill.bonus

    @property
    def adv(self):
        """
        The guaranteed advantage or disadvantage on this skill modifier. True = adv, False = dis, None = normal.

        :rtype: bool or None
        """
        return self._skill.adv

    def d20(self, base_adv=None, reroll=None, min_val=None, mod_override=None):
        """
        Gets a dice string representing the roll for this skill.

        :param bool base_adv: Whether this roll should be made at adv (True), dis (False), or normally (None).
        :param int reroll: If the roll lands on this number, reroll it once (Halfling Luck).
        :param int min_val: The minimum value of the dice roll (Reliable Talent, Glibness).
        :param int mod_override: Overrides the skill modifier.
        :rtype: str
        """
        return self._skill.d20(base_adv, reroll, min_val, mod_override)

    def __int__(self):
        return int(self._skill)

    def __repr__(self):
        return f"<AliasSkill {self.value:+} prof={self.prof} bonus={self.bonus} adv={self.adv}>"


class AliasSkills:
    """
    An object holding the skill modifiers for all skills.
    """

    def __init__(self, skills):
        """
        :type skills: cogs5e.models.sheet.base.Skills
        """
        self._skills = skills

    def __getattr__(self, item):
        if item not in self._skills.skills:
            raise ValueError(f"{item} is not a skill.")
        return AliasSkill(self._skills.__getattr__(item))

    def __getitem__(self, item):
        return self.__getattr__(item)

    def __str__(self):
        return str(self._skills)

    def __iter__(self):
        """An iterator of (key, Skill)."""
        for key, value in self._skills:
            yield key, AliasSkill(value)


class AliasSaves:
    """
    An objecting holding the modifiers of all saves.
    """

    def __init__(self, saves):
        """
        :type saves: cogs5e.models.sheet.base.Saves
        """
        self._saves = saves

    def get(self, base_stat):
        """
        Gets the save skill for a given stat (str, dex, etc).

        :param str base_stat: The stat to get the save for.
        :rtype: :class:`~aliasing.api.statblock.AliasSkill`
        """
        return AliasSkill(self._saves.get(base_stat))

    def __str__(self):
        return str(self._saves)

    def __iter__(self):
        """An iterator of (key, Skill)."""
        for key, value in self._saves:
            yield key, AliasSkill(value)


class AliasResistances:
    """
    A statblock's resistances, immunities, vulnerabilities, and explicit neural damage types.
    """

    def __init__(self, resistances):
        """
        :type resistances: cogs5e.models.sheet.resistance.Resistances
        """
        self._resistances = resistances

    @property
    def resist(self):
        """
        A list of damage types that the stat block is resistant to.

        :rtype: list[Resistance]
        """
        return self._resistances.resist

    @property
    def vuln(self):
        """
        A list of damage types that the stat block is vulnerable to.

        :rtype: list[Resistance]
        """
        return self._resistances.vuln

    @property
    def immune(self):
        """
        A list of damage types that the stat block is immune to.

        :rtype: list[Resistance]
        """
        return self._resistances.immune

    @property
    def neutral(self):
        """
        A list of damage types that the stat block ignores in damage calculations. (i.e. will not handle resistances/
        vulnerabilities/immunities)

        :rtype: list[Resistance]
        """
        return self._resistances.neutral

    def __str__(self):
        return str(self._resistances)


class AliasSpellbook:
    """
    A statblock's spellcasting information.
    """

    def __init__(self, spellbook):
        """
        :type spellbook: cogs5e.models.sheet.spellcasting.Spellbook
        """
        self._spellbook = spellbook
        self._spells = None

    @property
    def dc(self):
        """
        The spellcasting DC.

        :rtype: int
        """
        return self._spellbook.dc

    @property
    def sab(self):
        """
        The spell attack bonus.

        :rtype: int
        """
        return self._spellbook.sab

    @property
    def caster_level(self):
        """
        The caster's caster level.

        :rtype: int
        """
        return self._spellbook.caster_level

    @property
    def spell_mod(self):
        """
        The spellcasting modifier.

        :rtype: int
        """
        return self._spellbook.spell_mod

    @property
    def spells(self):
        """
        The list of spells in this spellbook.

        :rtype: list[AliasSpellbookSpell]
        """
        if self._spells is None:
            self._spells = [AliasSpellbookSpell(s) for s in self._spellbook.spells]
        return self._spells

    def slots_str(self, level):
        """
        :param int level: The level of spell slot to return.
        :returns str: A string representing the caster's remaining spell slots.
        """
        return self._spellbook.slots_str(int(level))

    def get_max_slots(self, level):
        """
        Gets the maximum number of level *level* spell slots available.

        :param int level: The spell level [1..9].
        :returns int: The maximum number of spell slots.
        """
        return self._spellbook.get_max_slots(int(level))

    def get_slots(self, level):
        """
        Gets the remaining number of slots of a given level. Always returns 1 if level is 0.

        :param int level: The spell level to get the remaining slots of.
        :returns int: The number of slots remaining.
        """
        return self._spellbook.get_slots(int(level))

    def set_slots(self, level, value):
        """
        Sets the remaining number of spell slots of a given level.

        :param int level: The spell level to set [1..9].
        :param int value: The remaining number of slots.
        """
        return self._spellbook.set_slots(int(level), int(value))

    def use_slot(self, level):
        """
        Uses one spell slot of a given level. Equivalent to ``set_slots(level, get_slots(level) - 1)``.

        :param int level: The level of spell slot to use.
        """
        return self._spellbook.use_slot(int(level))

    def reset_slots(self):
        """
        Resets the number of remaining spell slots of all levels to the max.
        """
        return self._spellbook.reset_slots()

    def remaining_casts_of(self, spell, level):
        """
        Gets a string representing the remaining casts of a given spell at a given level.

        :param str spell: The name of the spell (case-sensitive).
        :param int level: The level the spell is being cast at.
        :rtype: str
        """
        the_spell = _SpellProxy(str(spell), int(level))
        return self._spellbook.remaining_casts_of(the_spell, int(level))

    def cast(self, spell, level):
        """
        Uses all resources to cast a given spell at a given level.

        :param str spell: The name of the spell.
        :param int level: The level the spell is being cast at.
        """
        the_spell = _SpellProxy(str(spell), int(level))
        return self._spellbook.cast(the_spell, int(level))

    def can_cast(self, spell, level):
        """
        Returns whether or not the given spell can currently be cast at the given level.

        :param str spell: The name of the spell.
        :param int level: The level the spell is being cast at.
        :rtype: bool
        """
        the_spell = _SpellProxy(str(spell), int(level))
        return self._spellbook.can_cast(the_spell, int(level))

    def __contains__(self, item):
        return item in self._spellbook

    def __repr__(self):
        return "<AliasSpellbook object>"


class AliasSpellbookSpell:
    def __init__(self, spell):
        """
        :type spell: cogs5e.models.sheet.spellcasting.SpellbookSpell
        """
        self._spell = spell

    @property
    def name(self):
        """
        The name of the spell.

        :rtype: str
        """
        return self._spell.name

    @property
    def dc(self):
        """
        The spell's overridden DC. None if this spell uses the default caster DC.

        :rtype: int or None
        """
        return self._spell.dc

    @property
    def sab(self):
        """
        The spell's overridden spell attack bonus. None if this spell uses the default caster spell attack bonus.

        :rtype: int or None
        """
        return self._spell.sab

    @property
    def mod(self):
        """
        The spell's overridden spellcasting modifier. None if this spell uses the default caster spellcasting modifier.

        :rtype: int or None
        """
        return self._spell.mod

    def __str__(self):
        return self.name

    def __repr__(self):
        return f"<AliasSpellbookSpell name={self.name} dc={self.dc} sab={self.sab} mod={self.mod}>"


class _SpellProxy:
    """Duck-typed spell to pass to spellbook."""

    def __init__(self, name, level):
        self.name = name
        self.level = level
