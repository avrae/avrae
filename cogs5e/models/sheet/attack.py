class Attack:
    def __init__(self, name, bonus: int = None, damage: str = None, details: str = None, bonus_calc: str = None):
        self.name = name
        self.bonus = bonus
        self.damage = damage
        self.details = details
        self.bonus_calc = bonus_calc

    @classmethod
    def from_dict(cls, d):
        return cls(**d)

    def to_dict(self):
        return {"name": self.name, "bonus": self.bonus, "damage": self.damage, "details": self.details,
                "bonus_calc": self.bonus_calc}

    # ---------- main funcs ----------
    @classmethod
    def new(cls, character, name, bonus_calc: str = None, damage: str = None, details: str = None):
        bonus = character.evaluate_cvar(bonus_calc)
        return cls(name, bonus, damage, details, bonus_calc)

    def to_old(self):
        return {"name": self.name, "attackBonus": self.bonus, "damage": self.damage, "details": self.details}

    def __str__(self):
        if self.bonus:
            return f"**{self.name}**: {self.bonus:+} to hit, {self.damage or 'no'} damage."
        return f"**{self.name}**: {self.damage or 'no'} damage."
