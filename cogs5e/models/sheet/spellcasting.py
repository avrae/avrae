class Spellbook:
    def __init__(self, slots: dict, max_slots: dict, spells: list, dc=None, sab=None, caster_level=0, spell_mod=None):
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

    def get_slots(self, level):
        if level == 0:
            return 1
        return self.slots.get(str(level), 0)

    def set_slots(self, level, value):
        self.slots[str(level)] = value

    def reset_slots(self):
        for level in range(1, 10):
            self.set_slots(level, self.get_max_slots(level))

    def get_max_slots(self, level):
        return self.max_slots.get(str(level), 0)


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


class Spellcaster:
    def __init__(self, spellbook=None):
        if spellbook is None:
            spellbook = Spellbook({}, {}, [])
        self._spellbook = spellbook

    @property
    def spellbook(self):
        return self._spellbook

    def can_cast(self, spell, level) -> bool:
        """
        Checks whether a combatant can cast a certain spell at a certain level.
        :param spell: The spell to check.
        :param level: The level to cast it at.
        :return: Whether the combatant can cast the spell.
        """
        return spell.name in self._spellbook

    def cast(self, spell, level):
        """
        Casts a spell at a certain level, using the necessary resources.
        :param spell: The spell
        :param level: The level
        :return: None
        """
        pass

    def remaining_casts_of(self, spell, level):
        """
        Gets the string representing how many more times this combatant can cast this spell.
        :param spell: The spell
        :param level: The level
        """
        return "Slots are not tracked for this caster."

    def get_name(self):
        """
        Hm.
        :return: The name of the caster.
        """
        return "Unnamed"

    def pb_from_level(self):
        """
        Gets the proficiency bonus of the caster, given their level.
        Not quite foolproof.
        :return: The caster's probable PB.
        """
        return (self._spellbook.caster_level + 7) // 4
