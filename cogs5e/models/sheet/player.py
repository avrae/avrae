from cogs5e.models.errors import CounterOutOfBounds, InvalidArgument, NoReset
from utils.functions import bubble_format
from .attack import AttackList
from .spellcasting import SpellbookSpell


class CharOptions:
    def __init__(self, options=None):
        if options is None:
            options = {}
        self.options = options

    @classmethod
    def from_dict(cls, d):
        return cls(**d)

    def to_dict(self):
        return {"options": self.options}

    # ---------- main funcs ----------
    def get(self, option, default=None):
        return self.options.get(option, default)

    def set(self, option, value):
        if value is None and option in self.options:
            del self.options[option]
        else:
            self.options[option] = value


class ManualOverrides:
    def __init__(self, desc=None, image=None, attacks=None, spells=None):
        if attacks is None:
            attacks = []
        if spells is None:
            spells = []
        self.desc = desc
        self.image = image
        self.attacks = AttackList.from_dict(attacks)
        self.spells = [SpellbookSpell.from_dict(s) for s in spells]

    @classmethod
    def from_dict(cls, d):
        return cls(**d)

    def to_dict(self):
        return {"desc": self.desc, "image": self.image, "attacks": self.attacks.to_dict(),
                "spells": [s.to_dict() for s in self.spells]}


class DeathSaves:
    def __init__(self, successes=0, fails=0):
        self.successes = successes
        self.fails = fails

    @classmethod
    def from_dict(cls, d):
        return cls(**d)

    def to_dict(self):
        return {"successes": self.successes, "fails": self.fails}

    # ---------- main funcs ----------
    def succeed(self, num=1):
        self.successes = min(3, self.successes + num)

    def fail(self, num=1):
        self.fails = min(3, self.fails + num)

    def is_stable(self):
        return self.successes == 3

    def is_dead(self):
        return self.fails == 3

    def reset(self):
        self.successes = 0
        self.fails = 0

    def __str__(self):
        successes = bubble_format(self.successes, 3)
        fails = bubble_format(self.fails, 3, True)
        return f"F {fails} | {successes} S"


class CustomCounter:
    RESET_MAP = {'short': "Short Rest",
                 'long': "Long Rest",
                 'reset': "`!cc reset`",
                 'hp': "Gaining HP"}

    def __init__(self, character, name, value, minv=None, maxv=None, reset=None, display_type=None, live_id=None):
        self._character = character
        self.name = name
        self._value = value
        self.min = minv
        self.max = maxv
        self.reset_on = reset
        self.display_type = display_type
        self.live_id = live_id

        # cached values
        self._max = None
        self._min = None

    @classmethod
    def from_dict(cls, char, d):
        return cls(char, **d)

    def to_dict(self):
        return {"name": self.name, "value": self._value, "minv": self.min, "maxv": self.max, "reset": self.reset_on,
                "display_type": self.display_type, "live_id": self.live_id}

    @classmethod
    def new(cls, character, name, minv=None, maxv=None, reset=None, display_type=None, live_id=None):
        if reset not in ('short', 'long', 'none', None):
            raise InvalidArgument("Invalid reset.")
        if any(c in name for c in ".$"):
            raise InvalidArgument("Invalid character in CC name.")
        if minv is not None and maxv is not None:
            max_value = character.evaluate_math(maxv)
            if max_value < character.evaluate_math(minv):
                raise InvalidArgument("Max value is less than min value.")
            if max_value == 0:
                raise InvalidArgument("Max value cannot be 0.")
        if reset and maxv is None:
            raise InvalidArgument("Reset passed but no maximum passed.")
        if display_type == 'bubble' and (maxv is None or minv is None):
            raise InvalidArgument("Bubble display requires a max and min value.")

        if maxv:
            value = character.evaluate_math(maxv)
        else:
            value = 0
        return cls(character, name.strip(), value, minv, maxv, reset, display_type, live_id)

    # ---------- main funcs ----------
    def get_min(self):
        if self._min is None:
            if self.min is None:
                self._min = -(2 ** 31)
            else:
                self._min = self._character.evaluate_math(self.min)
        return self._min

    def get_max(self):
        if self._max is None:
            if self.max is None:
                self._max = 2 ** 31 - 1
            else:
                self._max = self._character.evaluate_math(self.max)
        return self._max

    @property
    def value(self):
        return self._value

    def set(self, new_value: int, strict=False):
        minv = self.get_min()
        maxv = self.get_max()

        if strict and not minv <= new_value <= maxv:
            raise CounterOutOfBounds()

        new_value = min(max(minv, new_value), maxv)
        self._value = int(new_value)

        if self.live_id:
            self._character.sync_consumable(self)
        return self._value

    def reset(self):
        if self.reset_on == 'none' or self.max is None:
            raise NoReset()
        return self.set(self.get_max())

    def full_str(self):
        _min = self.get_min()
        _max = self.get_max()
        _reset = self.RESET_MAP.get(self.reset_on)

        if self.display_type == 'bubble':
            assert self.max is not None
            val = f"{bubble_format(self.value, _max)}\n"
        else:
            val = f"**Current Value**: {self.value}\n"
            if self.min is not None and self.max is not None:
                val += f"**Range**: {_min} - {_max}\n"
            elif self.min is not None:
                val += f"**Range**: {_min}+\n"
            elif self.max is not None:
                val += f"**Range**: \u2264{_max}\n"
        if _reset:
            val += f"**Resets On**: {_reset}\n"
        return val.strip()

    def __str__(self):
        _max = self.get_max()

        if self.display_type == 'bubble':
            assert self.max is not None
            out = bubble_format(self.value, _max)
        else:
            if self.max is not None:
                out = f"{self.value}/{_max}"
            else:
                out = str(self.value)

        return out
