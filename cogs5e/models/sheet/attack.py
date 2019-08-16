class Attack:
    """
    A simple attack model. Does not support full automation (TODO).
    """

    def __init__(self, name, bonus: int = None, damage: str = None, details: str = None, bonus_calc: str = None):
        self.name = name
        self.bonus = bonus
        self.damage = damage
        self.details = details
        self.bonus_calc = bonus_calc

    @classmethod
    def from_dict(cls, d):
        return cls(**d)

    @classmethod
    def from_old(cls, d):
        if 'attackBonus' in d and d['attackBonus']:
            bonus = int(d['attackBonus'])
        else:
            bonus = None
        damage = d.get('damage')
        details = d.get('details')
        return cls(d['name'], bonus, damage, details)

    def to_dict(self):
        return {"name": self.name, "bonus": self.bonus, "damage": self.damage, "details": self.details,
                "bonus_calc": self.bonus_calc}

    # ---------- main funcs ----------
    @classmethod
    def new(cls, character, name, bonus_calc: str = None, damage: str = None, details: str = None):
        """Creates a new attack for a character."""
        if bonus_calc:
            bonus = character.evaluate_cvar(bonus_calc)
        else:
            bonus = None
        return cls(name, bonus, damage, details, bonus_calc)

    def to_old(self):
        bonus = None
        if self.bonus is not None:
            bonus = str(self.bonus)
        elif self.bonus_calc is not None:
            bonus = self.bonus_calc
        return {"name": self.name, "attackBonus": bonus, "damage": self.damage, "details": self.details}

    def __str__(self):
        if self.bonus is not None:
            return f"**{self.name}**: {self.bonus:+} to hit, {self.damage or 'no'} damage."
        elif self.bonus_calc:
            return f"**{self.name}**: {self.bonus_calc} to hit, {self.damage or 'no'} damage."
        return f"**{self.name}**: {self.damage or 'no'} damage."
