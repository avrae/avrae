import random

from cogs5e.models.sheet.attack import AttackList
from cogs5e.models.sheet.base import BaseStats, Levels, Saves, Skills
from cogs5e.models.sheet.resistance import Resistances
from cogs5e.models.sheet.spellcasting import Spellbook
from utils.constants import STAT_NAMES

DESERIALIZE_MAP = {
    "stats": BaseStats,
    "levels": Levels,
    "attacks": AttackList,
    "skills": Skills,
    "saves": Saves,
    "resistances": Resistances,
    "spellbook": Spellbook,
}


class StatBlock:
    """
    A StatBlock is the fundamental blob of stats that all actors in 5e have. Any actor-agnostic function (e.g. cast,
    attack, automation) should try to use as much data from a statblock as possible, as opposed to class-specific
    attributes, and any actor (Character, Monster, Combatant) should subclass this.

    This replaces the Spellcaster model.
    """

    def __init__(
        self,
        name: str,
        stats: BaseStats = None,
        levels: Levels = None,
        attacks: AttackList = None,
        skills: Skills = None,
        saves: Saves = None,
        resistances: Resistances = None,
        spellbook: Spellbook = None,
        ac: int = None,
        max_hp: int = None,
        hp: int = None,
        temp_hp: int = 0,
        creature_type: str = None,
    ):
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
        # assigned by combatant type
        self._creature_type = creature_type

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

    @hp.setter
    def hp(self, value):
        self._hp = max(0, value)

    @property
    def temp_hp(self):
        return self._temp_hp

    @temp_hp.setter
    def temp_hp(self, value):
        self._temp_hp = max(0, value)  # 0 ≤ temp_hp

    @property
    def spellbook(self):
        return self._spellbook

    @property
    def creature_type(self):
        return self._creature_type

    # ===== UTILS =====
    # ----- Display -----
    def get_title_name(self):
        return self._name

    def get_color(self):
        return random.randint(0, 0xFFFFFF)

    # ----- HP -----
    def hp_str(self):
        out = f"{self.hp}/{self.max_hp}"
        if self.temp_hp:
            out += f" ({self.temp_hp} temp)"
        return out

    def modify_hp(self, value, ignore_temp=False, overflow=True):
        """Modifies the actor's hit points. If ignore_temp is True, will deal damage to raw HP, ignoring temp."""
        if value < 0 and not ignore_temp:
            thp = self.temp_hp
            self.temp_hp += value
            value += min(thp, -value)  # how much did the THP absorb?

        if self.hp is None:
            return f"Dealt {-value} damage!"

        if overflow:
            self.hp = self.hp + value
        elif self.max_hp is not None:
            self.hp = min(self.hp + value, self.max_hp)
        else:
            self.hp = self.hp + value
        return self.hp_str()

    def set_hp(self, new_hp):  # set hp before temp hp
        self.hp = new_hp

    def reset_hp(self):
        """Resets the actor's HP to max and THP to 0."""
        self._temp_hp = 0
        self.hp = self.max_hp

    # ===== SCRIPTING =====
    def get_scope_locals(self):
        out = {}
        if self.spellbook.spell_mod is not None:
            spell_mod = self.spellbook.spell_mod
        elif self.spellbook.sab is not None:
            spell_mod = self.spellbook.sab - self.stats.prof_bonus
        else:
            spell_mod = None
        out.update({
            "name": self.name,
            "armor": self.ac,
            "hp": self.max_hp,
            "level": self.levels.total_level,
            "proficiencyBonus": self.stats.prof_bonus,
            "spell": spell_mod,
        })
        for cls, lvl in self.levels:
            out[f"{cls.replace(' ', '')}Level"] = lvl
        for stat in STAT_NAMES:
            out[stat] = self.stats[stat]
            out[f"{stat}Mod"] = self.stats.get_mod(stat)
            out[f"{stat}Save"] = self.saves.get(stat).value
        return out

    # ===== SERIALIZATION =====
    # must implement deserializer
    @classmethod
    def from_dict(cls, *args, **kwargs):
        raise NotImplementedError

    def to_dict(self):
        return {
            "name": self._name,
            "stats": self._stats.to_dict(),
            "levels": self._levels.to_dict(),
            "attacks": self._attacks.to_dict(),
            "skills": self._skills.to_dict(),
            "resistances": self._resistances.to_dict(),
            "saves": self._saves.to_dict(),
            "ac": self._ac,
            "max_hp": self._max_hp,
            "hp": self._hp,
            "temp_hp": self._temp_hp,
            "spellbook": self._spellbook.to_dict(),
            "creature_type": self._creature_type,
        }
