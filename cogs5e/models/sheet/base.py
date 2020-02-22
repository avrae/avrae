from utils.constants import SAVE_NAMES, SKILL_MAP, SKILL_NAMES, STAT_ABBREVIATIONS, STAT_NAMES
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
    @classmethod
    def default(cls):
        return cls(0, 10, 10, 10, 10, 10, 10)

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
    def __init__(self, classes: dict = None, total_level: int = None):
        if classes is None:
            classes = {}
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
    def __init__(self, value, prof: float = 0, bonus: int = 0, adv=None):
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
        out = {"value": self.value}
        if self.prof != 0:
            out['prof'] = self.prof
        if self.bonus != 0:
            out['bonus'] = self.bonus
        if self.adv is not None:
            out['adv'] = self.adv
        return out

    # ---------- main funcs ----------
    def d20(self, base_adv=None, reroll: int = None, min_val: int = None, mod_override=None):
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

        if mod_override is None:
            out = f"{base}{self.value:+}"
        else:
            out = f"{base}{mod_override:+}"
        return out

    def __int__(self):
        return self.value


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
    @classmethod
    def default(cls, base_stats: BaseStats = None):
        """Returns a skills object with skills set to default values, based on stats."""
        if base_stats is None:
            base_stats = BaseStats.default()
        skills = {}
        for skill in SKILL_NAMES:
            skills[skill] = Skill(base_stats.get_mod(SKILL_MAP[skill]))
        return cls(skills)

    def update(self, explicit_skills: dict):
        """
        Updates skills with an explicit dictionary of modifiers or Skills.
        All ints provided are assumed to have prof=1.
        """
        for skill, mod in explicit_skills.items():
            if skill not in self.skills:
                raise ValueError(f"{skill} is not a skill.")
            if isinstance(mod, int):
                self.skills[skill].value = mod
                self.skills[skill].prof = 1
            else:
                self.skills[skill] = mod

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

    def __iter__(self):
        for key, value in self.skills.items():
            yield key, value


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

    @classmethod
    def default(cls, base_stats: BaseStats = None):
        """Returns a saves object with saves set to default values, based on stats."""
        if base_stats is None:
            base_stats = BaseStats.default()
        saves = {}
        for save in SAVE_NAMES:
            saves[save] = Skill(base_stats.get_mod(SKILL_MAP[save]))
        return cls(saves)

    def update(self, explicit_saves: dict):
        """Updates saves with an explicit dictionary of modifiers. All provided are assumed to have prof=1."""
        for save, mod in explicit_saves.items():
            if save not in self.saves:
                raise ValueError(f"{save} is not a save.")
            self.saves[save].value = mod
            self.saves[save].prof = 1

    def __getitem__(self, item):
        return self.saves[item]

    def __str__(self):
        out = []
        for stat_name, save_key in zip(STAT_NAMES, SAVE_NAMES):
            save = self.saves[save_key]
            to_add = False
            modifiers = []

            if save.prof > 0.5 or save.bonus:
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

    def __iter__(self):
        for key, value in self.saves.items():
            yield key, value


class Resistances:
    def __init__(self, resist=None, immune=None, vuln=None, neutral=None):
        """
        :type resist: list[Resistance]
        :type immune: list[Resistance]
        :type vuln: list[Resistance]
        :type neutral: list[Resistance]
        """
        if neutral is None:
            neutral = []
        if vuln is None:
            vuln = []
        if immune is None:
            immune = []
        if resist is None:
            resist = []
        self.resist = resist
        self.immune = immune
        self.vuln = vuln
        self.neutral = neutral

    @classmethod
    def from_dict(cls, d):
        return cls(**{k: [Resistance.from_dict(v) for v in vs] for k, vs in d.items()})

    def to_dict(self):
        return {
            "resist": [t.to_dict() for t in self.resist],
            "immune": [t.to_dict() for t in self.immune],
            "vuln": [t.to_dict() for t in self.vuln],
            "neutral": [t.to_dict() for t in self.neutral]
        }

    def copy(self):
        return Resistances(self.resist.copy(), self.immune.copy(), self.vuln.copy(), self.neutral.copy())

    # ---------- main funcs ----------
    def __getitem__(self, item):
        if item == 'resist':
            return self.resist
        elif item == 'vuln':
            return self.vuln
        elif item == 'immune':
            return self.immune
        elif item == 'neutral':
            return self.neutral
        else:
            raise ValueError(f"{item} is not a resistance type.")

    def __str__(self):
        out = []
        if self.resist:
            out.append(f"**Resistances**: {', '.join([str(r) for r in self.resist])}")
        if self.immune:
            out.append(f"**Immunities**: {', '.join([str(r) for r in self.immune])}")
        if self.vuln:
            out.append(f"**Vulnerabilities**: {', '.join([str(r) for r in self.vuln])}")
        return '\n'.join(out)


class Resistance:
    """
    Represents a conditional resistance to a damage type.

    Only applied to a type token set T if :math:`dtype \in T \land \lnot (unless \cap T) \land only \subset T`.

    Note: transforms all damage types given to lowercase.
    """

    def __init__(self, dtype, unless=None, only=None):
        """
        :type dtype: str
        :type unless: set[str] or list[str]
        :type only: set[str] or list[str]
        """
        if unless is None:
            unless = set()
        else:
            unless = set(t.lower() for t in unless)
        if only is None:
            only = set()
        else:
            only = set(t.lower() for t in only)
        self.dtype = dtype.lower()
        self.unless = unless
        self.only = only

    @classmethod
    def from_dict(cls, d):
        if isinstance(d, str):
            return cls(d)
        return cls(**d)

    def to_dict(self):
        out = {"dtype": self.dtype}
        if self.unless:
            out['unless'] = list(self.unless)
        if self.only:
            out['only'] = list(self.only)
        return out

    def copy(self):
        return Resistance(self.dtype, self.unless.copy(), self.only.copy())

    # ---------- main funcs ----------
    def applies_to(self, tokens):
        """
        Note that tokens should be a set of lowercase strings.

        :type tokens: set[str]
        :rtype: bool
        """

        return self.dtype in tokens and not (self.unless & tokens) and self.only.issubset(tokens)

    def __str__(self):
        unlesses = ', '.join([f"non{u}" for u in self.unless])
        onlys = ' '.join(self.only)
        return f"{unlesses} {onlys} {self.dtype}".strip()
