from cogs5e.models.errors import CounterOutOfBounds, InvalidSpellLevel
from utils import constants
from utils.functions import bubble_format


class Spellbook:
    def __init__(
        self,
        slots: dict = None,
        max_slots: dict = None,
        spells: list = None,
        dc=None,
        sab=None,
        caster_level=0,
        spell_mod=None,
        pact_slot_level=None,
        num_pact_slots=None,
        max_pact_slots=None,
    ):
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
        self.pact_slot_level = pact_slot_level
        self.num_pact_slots = num_pact_slots
        self.max_pact_slots = max_pact_slots

    @classmethod
    def from_dict(cls, d):
        d["spells"] = [SpellbookSpell.from_dict(s) for s in d["spells"]]
        return cls(**d)

    def to_dict(self):
        return {
            "slots": self.slots,
            "max_slots": self.max_slots,
            "spells": [s.to_dict() for s in self.spells],
            "dc": self.dc,
            "sab": self.sab,
            "caster_level": self.caster_level,
            "spell_mod": self.spell_mod,
            "pact_slot_level": self.pact_slot_level,
            "num_pact_slots": self.num_pact_slots,
            "max_pact_slots": self.max_pact_slots,
        }

    def __contains__(self, spell_name: str):
        return any(spell_name.lower() == s.name.lower() for s in self.spells)

    # ===== display helpers =====
    def _slots_str_minimal(self, level: int):
        """Returns the slot level string if there are slots of this level, otherwise empty string."""
        if not 0 < level < 10:
            # not InvalidSpellLevel because if we're here, this is an internal error
            raise ValueError(f"Spell level must between 1 and 9 (got {level})")
        _max = self.get_max_slots(level)
        remaining = self.get_slots(level)

        if level == self.pact_slot_level and _max:
            max_non_pact = _max - self.max_pact_slots
            remaining_non_pact = remaining - self.num_pact_slots
            nonpact_slot_bubbles = bubble_format(remaining_non_pact, max_non_pact)
            pact_slot_bubbles = bubble_format(
                self.num_pact_slots,
                self.max_pact_slots,
                chars=constants.COUNTER_BUBBLES["square"],
            )
            return f"`{level}` {nonpact_slot_bubbles}{pact_slot_bubbles}"

        return f"`{level}` {bubble_format(remaining, _max)}" if _max else ""

    def slots_str(self, level: int = None):
        """
        :param int level: The level of spell slot to return.
        :returns: A string representing the caster's remaining spell slots.
        """
        if level is None:
            return self.all_slots_str()
        return self._slots_str_minimal(level) or "No spell slots."

    def all_slots_str(self):
        """Returns a string representing all of the character's spell slots."""
        out = []
        for level in range(1, 10):
            if level_str := self._slots_str_minimal(level):
                out.append(level_str)
        if not out:
            return "No spell slots."
        return "\n".join(out)

    # ===== utils =====
    def get_slots(self, level):
        """
        Gets the remaining number of slots of a given level. Always returns 1 if level is 0.
        """
        if level == 0:
            return 1
        return self.slots.get(str(level), 0)

    def set_slots(self, level: int, value: int, pact=True):
        """
        Sets the remaining number of spell slots (pact+non-pact) of a given level. If *pact* is True (default), will
        also modify *num_pact_slots* if applicable, otherwise will only affect *slots*.
        """
        if not 0 < level < 10:
            raise InvalidSpellLevel()
        lmax = self.get_max_slots(level)
        if value < 0:
            raise CounterOutOfBounds(f"You do not have enough remaining level {level} spell slots.")
        elif value > lmax:
            raise CounterOutOfBounds(f"You may not have this many level {level} spell slots (max {lmax}).")

        delta = value - self.get_slots(level)
        self.slots[str(level)] = value

        if pact and level == self.pact_slot_level and self.max_pact_slots is not None:  # attempt to modify pact first
            self.num_pact_slots = max(min(self.num_pact_slots + delta, self.max_pact_slots), 0)
        elif level == self.pact_slot_level and self.max_pact_slots is not None:  # make sure pact slots are valid
            self.num_pact_slots = max(min(self.num_pact_slots, value), value - (lmax - self.max_pact_slots))

    def reset_pact_slots(self):
        """
        Sets the number of remaining pact slots to the max, leaving non-pact slots untouched.
        """
        if self.pact_slot_level is None:
            return
        # add number of used pact slots to current value
        new_value = (self.max_pact_slots - self.num_pact_slots) + self.get_slots(self.pact_slot_level)
        # overflow sanity check (usually for first rest after v17 to v18 update)
        new_value = min(new_value, self.get_max_slots(self.pact_slot_level))
        self.set_slots(self.pact_slot_level, new_value)
        self.num_pact_slots = self.max_pact_slots

    def reset_slots(self):
        """
        Sets the number of remaining spell slots (including pact slots) to the max.
        """
        for level in range(1, 10):
            self.set_slots(level, self.get_max_slots(level))
        self.num_pact_slots = self.max_pact_slots

    def get_max_slots(self, level: int):
        """
        Gets the maximum number of level *level* spell slots available.
        """
        return self.max_slots.get(str(level), 0)

    def use_slot(self, level: int, pact=True):
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
            raise CounterOutOfBounds(f"You do not have any level {level} spell slots remaining.")

        self.set_slots(level, val, pact=pact)

    def get_spell(self, spell):
        """
        Returns a SpellbookSpell representing the caster's ability to cast this spell, or None if the spell is
        not in the caster's spellbook.

        .. note::
            If the spellcaster has the same spell available multiple times, it will prioritize a prepared version over
            a non-prepared version, otherwise returning arbitrarily.

        :type spell: :class:`~gamedata.spell.Spell`
        :rtype: :class:`~cogs5e.models.sheet.spellcasting.SpellbookSpell` or None
        """
        candidates = [s for s in self.spells if s.name.lower() == spell.name.lower()]
        if not candidates:
            return None
        return next((c for c in candidates if c.prepared), candidates[0])

    # ===== cast utils =====
    def cast(self, spell, level, pact=True):
        """
        Uses the resources to cast *spell* at *level*.

        :type spell: :class:`~cogs5e.models.spell.Spell`
        :type level: int
        :type pact: bool
        """
        self.use_slot(level, pact=pact)

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
    def __init__(
        self,
        name,
        strict=False,
        level: int = None,
        dc: int = None,
        sab: int = None,
        mod: int = None,
        prepared: bool = True,
    ):
        self.name = name
        self.strict = strict
        self.level = level
        self.dc = dc
        self.sab = sab
        self.mod = mod  # spellcasting ability mod
        self.prepared = prepared

    @classmethod
    def from_spell(cls, spell, dc=None, sab=None, mod=None, prepared=True, version="2024"):
        strict = spell.source != "homebrew"
        return cls(spell.name, strict, spell.level, dc, sab, mod, prepared)

    @classmethod
    def from_dict(cls, d):
        return cls(**d)

    def to_dict(self):
        d = {"name": self.name, "strict": self.strict}
        for optional_key in ("level", "dc", "sab", "mod", "prepared"):
            # minor storage optimization: don't store unncessary attributes
            v = getattr(self, optional_key)
            if v is not None:
                d[optional_key] = v
        return d
