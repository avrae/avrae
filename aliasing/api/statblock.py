class AliasStatBlock:
    """
    A simplified wrapper around StatBlock used as a base class for statblocks in aliases.
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
        return self._statblock.name

    @property
    def stats(self):
        if self._stats is None:
            self._stats = AliasBaseStats(self._statblock.stats)
        return self._stats

    @property
    def levels(self):
        if self._levels is None:
            self._levels = AliasLevels(self._statblock.levels)
        return self._levels

    @property
    def attacks(self):  # todo
        return

    @property
    def skills(self):
        if self._skills is None:
            self._skills = AliasSkills(self._statblock.skills)
        return self._skills

    @property
    def saves(self):
        if self._saves is None:
            self._saves = AliasSaves(self._statblock.saves)
        return self._saves

    @property
    def resistances(self):
        if self._resistances is None:
            self._resistances = AliasResistances(self._statblock.resistances)
        return self._resistances

    @property
    def ac(self):
        return self._statblock.ac

    @property
    def max_hp(self):
        return self._statblock.max_hp

    @property
    def hp(self):
        return self._statblock.hp

    @property
    def temp_hp(self):
        return self._statblock.temp_hp

    @property
    def spellbook(self):
        if self._spellbook is None:
            self._spellbook = AliasSpellbook(self._statblock.spellbook)
        return self._spellbook


class AliasBaseStats:
    def __init__(self, stats):
        """
        :type stats: cogs5e.models.sheet.base.BaseStats
        """
        self._stats = stats

    @property
    def prof_bonus(self):
        return self._stats.prof_bonus

    @property
    def strength(self):
        return self._stats.strength

    @property
    def dexterity(self):
        return self._stats.dexterity

    @property
    def constitution(self):
        return self._stats.constitution

    @property
    def intelligence(self):
        return self._stats.intelligence

    @property
    def wisdom(self):
        return self._stats.wisdom

    @property
    def charisma(self):
        return self._stats.charisma

    def get_mod(self, stat: str):
        """
        Gets the modifier for a base stat (str, dex, con, etc). Does *not* take skill check bonuses into account.

        For the skill check modifier, use ``StatBlock.skills.strength`` etc.

        :rtype: int
        """
        return self._stats.get_mod(str(stat))

    def __str__(self):
        return str(self._stats)


class AliasLevels:
    def __init__(self, levels):
        """
        :type levels: cogs5e.models.sheet.base.Levels
        """
        self._levels = levels

    @property
    def total_level(self):
        return self._levels.total_level

    def get(self, cls_name, default=0):
        """
        Gets the levels in a given class, or the default if there are none.

        :param str cls_name: The name of the class to get the levels of.
        :param default: What to return if the statblock does not have levels in the given class.
        """
        return self._levels.get(cls_name, default)

    def __iter__(self):
        return iter(self._levels)

    def __str__(self):
        return str(self._levels)


class AliasSkill:
    def __init__(self, skill):
        """
        :type skill: cogs5e.models.sheet.base.Skill
        """
        self._skill = skill

    @property
    def value(self):
        return self._skill.value

    @property
    def prof(self):
        return self._skill.prof

    @property
    def bonus(self):
        return self._skill.bonus

    @property
    def adv(self):
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
        return self._skill.d20(bool(base_adv), reroll, min_val, mod_override)

    def __int__(self):
        return int(self._skill)

    def __repr__(self):
        return f"<Skill {self.value:+} prof={self.prof} bonus={self.bonus} adv={self.adv}>"


class AliasSkills:
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
    def __init__(self, saves):
        """
        :type skills: cogs5e.models.sheet.base.Saves
        """
        self._saves = saves

    def get(self, base_stat):
        """
        Gets the save skill for a given stat (str, dex, etc).

        :param str base_stat: The stat to get the save for.
        :rtype: AliasSkill
        """
        return AliasSkill(self._saves.get(base_stat))

    def __str__(self):
        return str(self._saves)

    def __iter__(self):
        """An iterator of (key, Skill)."""
        for key, value in self._saves:
            yield key, AliasSkill(value)


class AliasResistances:
    def __init__(self, resistances):
        """
        :type resistances: cogs5e.models.sheet.resistance.Resistances
        """
        self._resistances = resistances

    @property
    def resist(self):
        return self._resistances.resist  # todo?

    @property
    def vuln(self):
        return self._resistances.vuln

    @property
    def immune(self):
        return self._resistances.immune

    @property
    def neutral(self):
        return self._resistances.neutral

    def __str__(self):
        return str(self._resistances)


class AliasSpellbook:  # todo
    pass
