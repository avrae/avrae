from utils.constants import SAVE_NAMES, SKILL_NAMES, STAT_ABBREVIATIONS, STAT_NAMES
from utils.functions import camel_to_title, verbose_stat


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

    def __str__(self):
        return f"**STR**: {self.strength} ({(self.strength - 10) // 2:+}) " \
            f"**DEX**: {self.dexterity} ({(self.dexterity - 10) // 2:+}) " \
            f"**CON**: {self.constitution} ({(self.constitution - 10) // 2:+})\n" \
            f"**INT**: {self.intelligence} ({(self.intelligence - 10) // 2:+}) " \
            f"**WIS**: {self.wisdom} ({(self.wisdom - 10) // 2:+}) " \
            f"**CHA**: {self.charisma} ({(self.charisma - 10) // 2:+})"

    def __getitem__(self, item):  # little bit hacky, but works
        if item not in STAT_NAMES:
            raise ValueError(f"{item} is not a stat.")
        return getattr(self, item)


class Levels:
    def __init__(self, classes: dict, total_level: int = None):
        self.total_level = total_level or sum(classes.values())
        self.classes = classes

    @classmethod
    def from_dict(cls, d):
        return cls(**d)

    def to_dict(self):
        return {"total_level": self.total_level, "classes": self.classes}

    # ---------- main funcs ----------
    def __iter__(self):
        """Yields an iterator of (Class, Level) pairs (e.g. (Bard, 5), (Warlock, 1))
        a character has at least 1 class in."""
        for cls, lvl in self.classes.items():
            if lvl > 0:
                yield cls, lvl

    def get(self, cls_name: str, default=0):
        return self.classes.get(cls_name, default)


class Skill:
    def __init__(self, value, prof=0, bonus=0, adv=None):
        # mod = value = base + (pb * prof) + bonus
        # adv = tribool (False, None, True) = (dis, normal, adv)
        if prof not in (0, 0.5, 1, 2):
            raise ValueError("Prof must be 0, 0.5, 1, or 2.")
        self.value = value
        self.prof = prof
        self.bonus = bonus
        self.adv = adv

    @classmethod
    def from_dict(cls, d):
        return cls(**d)

    def to_dict(self):
        return {"value": self.value, "prof": self.prof, "bonus": self.bonus, "adv": self.adv}

    # ---------- main funcs ----------
    def d20(self, base_adv=None, reroll: int = None, min_val: int = None, base_only=False):
        if base_adv is None:
            adv = self.adv
        elif self.adv is None:
            adv = base_adv
        elif base_adv is self.adv:
            adv = self.adv
        else:
            adv = None

        if adv is False:
            base = f"2d20kl1"
        elif adv is True:
            base = f"2d20kh1"
        else:
            base = f"1d20"

        if reroll:
            base = f"{base}ro{reroll}"

        if min_val:
            base = f"{base}mi{min_val}"

        if base_only:
            return base

        out = f"{base}{self.value:+}"
        return out


class Skills:
    def __init__(self, skills):
        self.skills = skills

    @classmethod
    def from_dict(cls, d):
        if set(d.keys()) != set(SKILL_NAMES):
            raise ValueError(f"Some skills are missing. "
                             f"Difference: {set(d.keys()).symmetric_difference(set(SKILL_NAMES))}")
        skills = {k: Skill.from_dict(v) for k, v in d.items()}
        return cls(skills)

    def to_dict(self):
        return {k: self.skills[k].to_dict() for k in SKILL_NAMES}

    # ---------- main funcs ----------
    def __getattr__(self, item):
        if item not in self.skills:
            raise ValueError(f"{item} is not a skill.")
        return self.skills[item]

    def __getitem__(self, item):
        return self.__getattr__(item)

    def __str__(self):
        out = []
        for skill_name in SKILL_NAMES:
            skill = self.skills[skill_name]
            to_add = False
            modifiers = []

            if skill.prof > 0.5:
                to_add = True
            if skill.prof == 2:
                modifiers.append("expertise")

            if skill.adv is False:
                to_add = True
                modifiers.append("dis")
            if skill.adv is True:
                to_add = True
                modifiers.append("adv")

            modifiers = f" ({', '.join(modifiers)})" if modifiers else ""
            if to_add:
                out.append(f"{camel_to_title(skill_name)} {skill.value:+}{modifiers}")
        return ", ".join(out)


class Saves:
    def __init__(self, saves):
        self.saves = saves

    @classmethod
    def from_dict(cls, d):
        if set(d.keys()) != set(SAVE_NAMES):
            raise ValueError(f"Some saves are missing. "
                             f"Difference: {set(d.keys()).symmetric_difference(set(SAVE_NAMES))}")
        saves = {k: Skill.from_dict(v) for k, v in d.items()}
        return cls(saves)

    def to_dict(self):
        return {k: self.saves[k].to_dict() for k in SAVE_NAMES}

    # ---------- main funcs ----------
    def get(self, base_stat: str):
        stat = base_stat[:3].lower()
        if stat not in STAT_ABBREVIATIONS:
            raise ValueError(f"{base_stat} is not a base stat.")
        return self.saves[f"{verbose_stat(stat).lower()}Save"]

    def __str__(self):
        out = []
        for stat_name, save_key in zip(STAT_NAMES, SAVE_NAMES):
            save = self.saves[save_key]
            to_add = False
            modifiers = []

            if save.prof > 0.5:
                to_add = True
            if save.prof == 2:
                modifiers.append("expertise")

            if save.adv is False:
                to_add = True
                modifiers.append("dis")
            if save.adv is True:
                to_add = True
                modifiers.append("adv")

            modifiers = f" ({', '.join(modifiers)})" if modifiers else ""
            if to_add:
                out.append(f"{stat_name.title()} {save.value:+}{modifiers}")
        return ", ".join(out)


class Resistances:
    def __init__(self, resist: list, immune: list, vuln: list):
        self.resist = resist
        self.immune = immune
        self.vuln = vuln

    @classmethod
    def from_dict(cls, d):
        return cls(**d)

    def to_dict(self):
        return {"resist": self.resist, "immune": self.immune, "vuln": self.vuln}

    # ---------- main funcs ----------
    def __str__(self):
        out = []
        if self.resist:
            out.append(f"**Resistances**: {', '.join(self.resist).title()}")
        if self.immune:
            out.append(f"**Immunities**: {', '.join(self.immune).title()}")
        if self.vuln:
            out.append(f"**Vulnerabilities**: {', '.join(self.vuln).title()}")
        return '\n'.join(out)
