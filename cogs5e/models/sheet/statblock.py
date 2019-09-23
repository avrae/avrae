from cogs5e.models.errors import InvalidSpellLevel, CounterOutOfBounds
from cogs5e.models.sheet import AttackList, BaseStats, Levels, Resistances, Saves, Skills, Spellbook

DESERIALIZE_MAP = {
    "stats": BaseStats, "levels": Levels, "attacks": AttackList, "skills": Skills, "saves": Saves,
    "resistances": Resistances, "spellbook": Spellbook
}


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

    @temp_hp.setter
    def temp_hp(self, value):
        self._temp_hp = max(0, value)  # 0 ≤ temp_hp

    @property
    def spellbook(self):
        return self._spellbook

    # ===== UTILS =====
    # ----- Display -----
    def get_title_name(self):
        return self._name

    # ----- HP -----
    def hp_str(self):
        out = f"{self.hp}/{self.max_hp}"
        if self.temp_hp:
            out += f' (+{self.temp_hp} temp)'
        return out

    def modify_hp(self, value, ignore_temp=False, overflow=True):
        """Modifies the actor's hit points. If ignore_temp is True, will deal damage to raw HP, ignoring temp."""
        if value < 0 and not ignore_temp:
            thp = self.temp_hp
            self.temp_hp += value
            value += min(thp, -value)  # how much did the THP absorb?
        if overflow:
            self._hp = self._hp + value
        else:
            self._hp = min(self._hp + value, self.max_hp)

    def set_hp(self, new_hp):  # set hp before temp hp
        self._hp = new_hp

    def reset_hp(self):
        """Resets the actor's HP to max and THP to 0."""
        self._temp_hp = 0
        self._hp = self.max_hp

    # ----- SLOTS -----
    def slots_str(self, level: int = None):
        """
        :param level: The level of spell slot to return.
        :returns A string representing the caster's remaining spell slots.
        """
        out = ''
        if level:
            assert 0 < level < 10
            _max = self._spellbook.get_max_slots(level)
            remaining = self._spellbook.get_slots(level)
            numEmpty = _max - remaining
            filled = '\u25c9' * remaining
            empty = '\u3007' * numEmpty
            out += f"`{level}` {filled}{empty}\n"
        else:
            for level in range(1, 10):
                _max = self._spellbook.get_max_slots(level)
                remaining = self._spellbook.get_slots(level)
                if _max:
                    numEmpty = _max - remaining
                    filled = '\u25c9' * remaining
                    empty = '\u3007' * numEmpty
                    out += f"`{level}` {filled}{empty}\n"
        if not out:
            out = "No spell slots."
        return out.strip()

    def set_remaining_slots(self, level: int, value: int):
        """
        Sets the actor's remaining spell slots of level level.
        :param level - The spell level.
        :param value - The number of remaining spell slots.
        """
        if not 0 < level < 10:
            raise InvalidSpellLevel()
        if not 0 <= value <= self.spellbook.get_max_slots(level):
            raise CounterOutOfBounds()
        self.spellbook.set_slots(level, value)

    def use_slot(self, level: int):
        """
        Uses one spell slot of level level.
        :raises CounterOutOfBounds if there are no remaining slots of the requested level.
        """
        if level == 0:
            return
        if not 0 < level < 10:
            raise InvalidSpellLevel()

        val = self.spellbook.get_slots(level) - 1
        if val < 0:
            raise CounterOutOfBounds("You do not have any spell slots of this level remaining.")

        self.set_remaining_slots(level, val)

    def reset_spellslots(self):
        """Resets all spellslots to their max value."""
        self.spellbook.reset_slots()

    def can_cast(self, spell, level) -> bool:
        return self.spellbook.get_slots(level) > 0 and spell.name in self.spellbook

    def cast(self, spell, level):
        self.use_slot(level)

    def remaining_casts_of(self, spell, level):
        return self.slots_str(level)

    # ===== SERIALIZATION =====
    # must implement deserializer
    @classmethod
    def from_dict(cls, *args, **kwargs):
        raise NotImplemented

    def to_dict(self):
        return {
            "name": self._name, "stats": self._stats.to_dict(), "levels": self._levels.to_dict(),
            "attacks": self._attacks.to_dict(), "skills": self._skills.to_dict(),
            "resistances": self._resistances.to_dict(), "saves": self._saves.to_dict(), "ac": self._ac,
            "max_hp": self._max_hp, "hp": self._hp, "temp_hp": self._temp_hp, "spellbook": self._spellbook.to_dict()
        }
