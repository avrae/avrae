from cogs5e.models.sheet import AttackList, BaseStats, Levels, Resistances, Saves, Skills, Spellbook


class StatBlock:
    """
    A StatBlock is the fundamental blob of stats that all actors in 5e have. Any actor-agnostic function (e.g. cast,
    attack, automation) should try to use as much data from a statblock as possible, as opposed to class-specific
    attributes, and any actor (Character, Monster, Combatant) should subclass this.

    This replaces the Spellcaster model.
    """

    def __init__(self, name: str, stats: BaseStats = None, levels: Levels = None, attacks: AttackList = None,
                 skills: Skills = None, saves: Saves = None, resistances: Resistances = None,
                 spellbook: Spellbook = None,
                 ac: int = None, max_hp: int = None, hp: int = None, temp_hp: int = 0):
        if stats is None:
            stats = BaseStats.default()
        if levels is None:
            levels = Levels()
        if attacks is None:
            attacks = AttackList()
        if skills is None:
            skills = Skills.default(stats)
        if saves is None:
            saves = Saves.default(stats)
        if resistances is None:
            resistances = Resistances()
        if spellbook is None:
            spellbook = Spellbook()
        if hp is None:
            hp = max_hp

        # ===== static =====
        # all actors have a name
        self._name = name
        # ability scores
        self._stats = stats
        # at least a total level
        self._levels = levels
        # attacks - list of automation actions
        self._attacks = attacks
        # skill profs/saving throws
        self._skills = skills
        self._saves = saves
        # defensive resistances
        self._resistances = resistances

        # ===== dynamic =====
        # hp/ac
        self._ac = ac
        self._max_hp = max_hp
        self._hp = hp
        self._temp_hp = temp_hp

        # spellbook
        self._spellbook = spellbook

    # guaranteed properties
    @property
    def name(self):
        return self._name

    @property
    def stats(self):
        return self._stats

    @property
    def levels(self):
        return self._levels

    @property
    def attacks(self):
        return self._attacks

    @property
    def skills(self):
        return self._skills

    @property
    def saves(self):
        return self._saves

    @property
    def resistances(self):
        return self._resistances

    @property
    def ac(self):
        return self._ac

    @property
    def max_hp(self):
        return self._max_hp

    @property
    def hp(self):
        return self._hp

    @property
    def temp_hp(self):
        return self._temp_hp

    @property
    def spellbook(self):
        return self._spellbook

    # must implement serializer/deserializer
    @classmethod
    def from_dict(cls, d):
        raise NotImplemented

    def to_dict(self):
        raise NotImplemented
