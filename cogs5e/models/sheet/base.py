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


class Skills:
    class Skill:
        pass

    @classmethod
    def from_dict(cls, d):
        pass

    def to_dict(self):
        pass


class Resistances:
    @classmethod
    def from_dict(cls, d):
        pass

    def to_dict(self):
        pass


class Saves:
    @classmethod
    def from_dict(cls, d):
        pass

    def to_dict(self):
        pass
