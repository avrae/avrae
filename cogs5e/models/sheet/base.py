from utils.constants import STAT_ABBREVIATIONS


class BaseStats:
    def __init__(self, prof_bonus: int, strength: int, dexterity: int, constitution: int, intelligence: int,
                 wisdom: int, charisma: int):
        self.prof_bonus = prof_bonus
        self.strength = strength
        self.dexterity = dexterity
        self.constitution = constitution
        self.intelligence = intelligence
        self.wisdom = wisdom
        self.charisma = charisma

    @classmethod
    def from_dict(cls, d):
        return cls(**d)

    def to_dict(self):
        return {
            "prof_bonus": self.prof_bonus, "strength": self.strength, "dexterity": self.dexterity,
            "constitution": self.constitution, "intelligence": self.intelligence, "wisdom": self.wisdom,
            "charisma": self.charisma
        }

    # ---------- main funcs ----------
    def get_mod(self, stat: str):
        abbr_stat = stat.lower()[:3]
        if abbr_stat not in STAT_ABBREVIATIONS:
            raise ValueError(f"{stat} is not a valid stat.")
        return {
            'str': self.strength // 2 - 5, 'dex': self.dexterity // 2 - 5,
            'con': self.constitution // 2 - 5, 'int': self.intelligence // 2 - 5,
            'wis': self.wisdom // 2 - 5, 'cha': self.charisma // 2 - 5
        }[abbr_stat]


class Levels:
    def __init__(self, classes: dict, total_level: int = None):
        self.total_level = total_level or sum(classes.values())
        self.classes = classes

    @classmethod
    def from_dict(cls, d):
        return cls(**d)

    def to_dict(self):
        return {"total_level": self.total_level, "classes": self.classes}


class Skill:
    def __init__(self, value, prof, bonus):
        # mod = value = base + (pb * prof) + bonus
        self.value = value
        self.prof = prof
        self.bonus = bonus

    @classmethod
    def from_dict(cls, d):
        return cls(**d)

    def to_dict(self):
        return {"value": self.value, "prof": self.prof, "bonus": self.bonus}


class Skills:
    def __init__(self, skills):
        self.skills = skills

    @classmethod
    def from_dict(cls, d):
        skills = {k: Skill.from_dict(v) for k, v in d.items()}
        return cls(skills)

    def to_dict(self):
        return {k: v.to_dict() for k, v in self.skills}


class Saves:
    def __init__(self, saves):
        self.saves = saves

    @classmethod
    def from_dict(cls, d):
        saves = {k: Skill.from_dict(v) for k, v in d.items()}
        return cls(saves)

    def to_dict(self):
        return {k: v.to_dict() for k, v in self.saves}


class Resistances:
    def __init__(self, resist, immune, vuln):
        self.resist = resist
        self.immune = immune
        self.vuln = vuln

    @classmethod
    def from_dict(cls, d):
        return cls(**d)

    def to_dict(self):
        return {"resist": self.resist, "immune": self.immune, "vuln": self.vuln}
