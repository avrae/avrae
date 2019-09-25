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

    # ===== utils =====
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
