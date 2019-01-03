class Spellcasting:
    def __init__(self, spells=None, dc=0, sab=0, casterLevel=0):
        if spells is None:
            spells = []
        self.spells = spells
        self.lower_spells = [s.lower() for s in spells]
        self.dc = dc
        self.sab = sab
        self.casterLevel = casterLevel

    @classmethod
    def from_dict(cls, spelldict):
        return cls(spelldict.get('spells', []), spelldict.get('dc', 0), spelldict.get('attackBonus', 0),
                   spelldict.get('casterLevel', 0))

    def to_dict(self):
        return {'spells': self.spells, 'dc': self.dc, 'attackBonus': self.sab, 'casterLevel': self.casterLevel}


class Spellcaster:
    def __init__(self, spellcasting=None):
        if spellcasting is None:
            spellcasting = Spellcasting()
        self._spellcasting = spellcasting

    @property
    def spellcasting(self):
        return self._spellcasting

    def can_cast(self, spell, level) -> bool:
        """
        Checks whether a combatant can cast a certain spell at a certain level.
        :param spell: The spell to check.
        :param level: The level to cast it at.
        :return: Whether the combatant can cast the spell.
        """
        return spell.name.lower() in [s.lower() for s in self.spellcasting.spells]

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
        return (self.spellcasting.casterLevel + 7) // 4
