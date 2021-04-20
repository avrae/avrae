from cogs5e.models.errors import CounterOutOfBounds, InvalidSpellLevel
from utils.functions import bubble_format


class Spellbook:
    def __init__(self, slots: dict = None, max_slots: dict = None, spells: list = None, dc=None, sab=None,
                 caster_level=0, spell_mod=None,
                 pact_slot_level=None, num_pact_slots=None, max_pact_slots=None):
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
        d['spells'] = [SpellbookSpell.from_dict(s) for s in d['spells']]
        return cls(**d)

    def to_dict(self):
        return {
            "slots": self.slots, "max_slots": self.max_slots, "spells": [s.to_dict() for s in self.spells],
            "dc": self.dc, "sab": self.sab, "caster_level": self.caster_level, "spell_mod": self.spell_mod,
            "pact_slot_level": self.pact_slot_level, "num_pact_slots": self.num_pact_slots,
            "max_pact_slots": self.max_pact_slots
        }

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

    def set_slots(self, level: int, value: int, pact=True):
        """
        Sets the remaining number of spell slots (pact+non-pact) of a given level. If *pact* is True (default), will
        also modify *num_pact_slots* if applicable, otherwise will only affect *slots*.
        """
        if not 0 < level < 10:
            raise InvalidSpellLevel()
        lmax = self.get_max_slots(level)
        if not 0 <= value <= lmax:
            raise CounterOutOfBounds()

        l = str(level)
        delta = value - self.get_slots(level)
        self.slots[l] = value

        if pact and level == self.pact_slot_level and self.max_pact_slots is not None:  # attempt to modify pact first
            self.num_pact_slots = max(min(self.num_pact_slots + delta, self.max_pact_slots), 0)
        elif level == self.pact_slot_level and self.max_pact_slots is not None:  # make sure pact slots are valid
            self.num_pact_slots = max(min(self.num_pact_slots, value), value - (lmax - self.max_pact_slots))

    def reset_slots(self, is_short_rest=False):
        """
        Sets the number of remaining spell slots to the max. If *is_short_rest* and there are pact slots, will
        reset the pact slots.
        """
        if is_short_rest and self.pact_slot_level is not None:
            # add number of used pact slots to current value
            new_value = (self.max_pact_slots - self.num_pact_slots) + self.get_slots(self.pact_slot_level)
            self.set_slots(self.pact_slot_level, new_value)
            self.num_pact_slots = self.max_pact_slots
        else:
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
            raise CounterOutOfBounds("You do not have any spell slots of this level remaining.")

        self.set_slots(level, val, pact=pact)

    def get_spell(self, spell):
        """
        Returns a SpellbookSpell representing the caster's ability to cast this spell, or None if the spell is
        not in the caster's spellbook.

        :type spell: :class:`~cogs5e.models.spell.Spell`
        :rtype: :class:`~cogs5e.models.sheet.spellcasting.SpellbookSpell` or None
        """
        return next((s for s in self.spells if s.name.lower() == spell.name.lower()), None)

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
    def __init__(self, name, strict=False, level: int = None, dc: int = None, sab: int = None, mod: int = None):
        self.name = name
        self.strict = strict
        self.level = level
        self.dc = dc
        self.sab = sab
        self.mod = mod  # spellcasting ability mod

    @classmethod
    def from_spell(cls, spell, dc=None, sab=None, mod=None):
        strict = spell.source != 'homebrew'
        return cls(spell.name, strict, spell.level, dc, sab, mod)

    @classmethod
    def from_dict(cls, d):
        return cls(**d)

    def to_dict(self):
        d = {"name": self.name, "strict": self.strict}
        for optional_key in ("level", "dc", "sab", "mod"):
            # minor storage optimization: don't store unncessary attributes
            v = getattr(self, optional_key)
            if v is not None:
                d[optional_key] = v
        return d
