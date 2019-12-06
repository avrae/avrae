from cogs5e.models.errors import CounterOutOfBounds, InvalidSpellLevel
from utils.functions import bubble_format


class Spellbook:
    def __init__(self, slots: dict = None, max_slots: dict = None, spells: list = None, dc=None, sab=None,
                 caster_level=0, spell_mod=None):
        if slots is None:
            slots = {}
        if max_slots is None:
            max_slots = {}
        if spells is None:
            spells = []
        self.slots = slots
        self.max_slots = max_slots
        self.spells = spells
        self.dc = dc
        self.sab = sab
        self.caster_level = caster_level
        self.spell_mod = spell_mod

    @classmethod
    def from_dict(cls, d):
        d['spells'] = [SpellbookSpell.from_dict(s) for s in d['spells']]
        return cls(**d)

    def to_dict(self):
        return {"slots": self.slots, "max_slots": self.max_slots, "spells": [s.to_dict() for s in self.spells],
                "dc": self.dc, "sab": self.sab, "caster_level": self.caster_level, "spell_mod": self.spell_mod}

    def __contains__(self, spell_name: str):
        return spell_name.lower() in {s.name.lower() for s in self.spells}

    # ===== display helpers =====
    def slots_str(self, level: int = None):
        """
        :param int level: The level of spell slot to return.
        :returns: A string representing the caster's remaining spell slots.
        """
        out = ''
        if level:
            assert 0 < level < 10
            _max = self.get_max_slots(level)
            remaining = self.get_slots(level)
            out += f"`{level}` {bubble_format(remaining, _max)}\n"
        else:
            for level in range(1, 10):
                _max = self.get_max_slots(level)
                remaining = self.get_slots(level)
                if _max:
                    out += f"`{level}` {bubble_format(remaining, _max)}\n"
        if not out:
            out = "No spell slots."
        return out.strip()

    # ===== utils =====
    def get_slots(self, level):
        """
        Gets the remaining number of slots of a given level. Always returns 1 if level is 0.
        """
        if level == 0:
            return 1
        return self.slots.get(str(level), 0)

    def set_slots(self, level: int, value: int):
        """
        Sets the remaining number of spell slots of a given level.
        """
        if not 0 < level < 10:
            raise InvalidSpellLevel()
        if not 0 <= value <= self.get_max_slots(level):
            raise CounterOutOfBounds()
        self.slots[str(level)] = value

    def reset_slots(self):
        """
        Sets the number of remaining spell slots to the max.
        """
        for level in range(1, 10):
            self.set_slots(level, self.get_max_slots(level))

    def get_max_slots(self, level: int):
        """
        Gets the maximum number of level *level* spell slots available.
        """
        return self.max_slots.get(str(level), 0)

    def use_slot(self, level: int):
        """
        Uses one spell slot of level level. Does nothing if level is 0.
        :raises CounterOutOfBounds if there are no remaining slots of the requested level.
        """
        if level == 0:
            return
        if not 0 < level < 10:
            raise InvalidSpellLevel()

        val = self.get_slots(level) - 1
        if val < 0:
            raise CounterOutOfBounds("You do not have any spell slots of this level remaining.")

        self.set_slots(level, val)

    # ===== cast utils =====
    def cast(self, spell, level):
        """
        Uses the resources to cast *spell* at *level*.

        :type spell: :class:`~cogs5e.models.spell.Spell`
        :type level: int
        """
        self.use_slot(level)

    def can_cast(self, spell, level) -> bool:
        """
        Returns whether the spell can be cast at the given level.

        :type spell: :class:`~cogs5e.models.spell.Spell`
        :type level: int
        """
        return self.get_slots(level) > 0 and spell.name in self

    def remaining_casts_of(self, spell, level):
        """
        Returns a string representing how many cast resources the caster has.

        :type spell: :class:`~cogs5e.models.spell.Spell`
        :type level: int
        """
        return self.slots_str(level)


class SpellbookSpell:
    def __init__(self, name, strict=False, level=None, dc=None, sab=None):
        self.name = name
        self.strict = strict
        self.level = level
        self.dc = dc
        self.sab = sab

    @classmethod
    def from_spell(cls, spell):
        strict = spell.source != 'homebrew'
        return cls(spell.name, strict, spell.level)

    @classmethod
    def from_dict(cls, d):
        return cls(**d)

    def to_dict(self):
        return {"name": self.name, "strict": self.strict, "level": self.level, "dc": self.dc, "sab": self.sab}
