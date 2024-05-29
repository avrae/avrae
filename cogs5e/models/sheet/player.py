import collections

import d20

from cogs5e.models.errors import CounterOutOfBounds, InvalidArgument, NoReset
from utils import constants
from utils.functions import bubble_format
from .attack import AttackList
from .spellcasting import SpellbookSpell


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
        return {
            "desc": self.desc,
            "image": self.image,
            "attacks": self.attacks.to_dict(),
            "spells": [s.to_dict() for s in self.spells],
        }


class DeathSaves:
    def __init__(self, character, successes=0, fails=0):
        self._character = character
        self.successes = successes
        self.fails = fails

    @classmethod
    def from_dict(cls, character, d):
        return cls(character, **d)

    def to_dict(self):
        return {"successes": self.successes, "fails": self.fails}

    # ---------- main funcs ----------
    def succeed(self, num=1):
        self.successes = min(3, self.successes + num)
        if num:
            self._character.sync_death_saves()

    def fail(self, num=1):
        self.fails = min(3, self.fails + num)
        if num:
            self._character.sync_death_saves()

    def is_stable(self):
        return self.successes == 3

    def is_dead(self):
        return self.fails == 3

    def reset(self):
        did_change = self.successes or self.fails
        self.successes = 0
        self.fails = 0
        if did_change:
            self._character.sync_death_saves()

    def __str__(self):
        successes = bubble_format(self.successes, 3)
        fails = bubble_format(self.fails, 3, True)
        return f"F {fails} | {successes} S"


class CustomCounter:
    RESET_MAP = {"short": "Short Rest", "long": "Long Rest", "reset": "`!cc reset`", "hp": "Gaining HP"}

    def __init__(
        self,
        character,
        name,
        value,
        minv=None,
        maxv=None,
        reset=None,
        display_type=None,
        live_id=None,
        reset_to=None,
        reset_by=None,
        title=None,
        desc=None,
        ddb_source_feature_type=None,
        ddb_source_feature_id=None,
    ):
        self._character = character
        self.name = name

        self.title = title
        self.desc = desc

        self._value = value
        self.min = minv
        self.max = maxv
        self.reset_on = reset
        self.reset_to = reset_to
        self.reset_by = reset_by
        self.display_type = display_type

        self.live_id = live_id
        self.ddb_source_feature_type = ddb_source_feature_type
        self.ddb_source_feature_id = ddb_source_feature_id

        # cached values
        self._max_value = None
        self._min_value = None

    @classmethod
    def from_dict(cls, char, d):
        return cls(char, **d)

    def to_dict(self):
        return {
            "name": self.name,
            "value": self._value,
            "minv": self.min,
            "maxv": self.max,
            "reset": self.reset_on,
            "display_type": self.display_type,
            "live_id": self.live_id,
            "reset_to": self.reset_to,
            "reset_by": self.reset_by,
            "title": self.title,
            "desc": self.desc,
            "ddb_source_feature_type": self.ddb_source_feature_type,
            "ddb_source_feature_id": self.ddb_source_feature_id,
        }

    @classmethod
    def new(
        cls,
        character,
        name,
        minv=None,
        maxv=None,
        reset=None,
        display_type=None,
        live_id=None,
        reset_to=None,
        reset_by=None,
        title=None,
        desc=None,
        initial_value=None,
    ):
        if reset not in ("short", "long", "none", None):
            raise InvalidArgument("Invalid reset.")
        if any(c in name for c in ".$"):
            raise InvalidArgument("Invalid character in CC name.")
        if display_type in constants.COUNTER_BUBBLES and (maxv is None or minv is None):
            raise InvalidArgument(f"{display_type.title()} display requires a max and min value.")

        # sanity checks
        if reset not in ("none", None) and (maxv is None and reset_to is None and reset_by is None):
            raise InvalidArgument("Reset passed but no valid reset value (`max`, `resetto`, `resetby`) passed.")
        if reset_to is not None and reset_by is not None:
            raise InvalidArgument("Both `resetto` and `resetby` arguments found.")
        if not name.strip():
            raise InvalidArgument("The name of the counter can not be empty.")

        min_value = None
        if minv is not None:
            min_value = character.evaluate_math(minv)
            if display_type in constants.COUNTER_BUBBLES and (min_value < 0):
                raise InvalidArgument(f"{display_type.title()} display requires a min value of >= 0.")

        max_value = None
        if maxv is not None:
            max_value = character.evaluate_math(maxv)
            if min_value is not None and max_value < min_value:
                raise InvalidArgument("Max value is less than min value.")

        reset_to_value = None
        if reset_to is not None:
            reset_to_value = character.evaluate_math(reset_to)
            if min_value is not None and reset_to_value < min_value:
                raise InvalidArgument("Reset to value is less than min value.")
            if max_value is not None and reset_to_value > max_value:
                raise InvalidArgument(f"Reset to value {reset_to_value} is greater than max value {max_value}.")

        if reset_by is not None:
            evaluated_str = character.evaluate_annostr(str(reset_by))

            try:
                d20.parse(evaluated_str)
            except d20.RollSyntaxError:
                raise InvalidArgument(
                    f"`{evaluated_str}` (`resetby`) cannot be interpreted as a number or dice string."
                )

        # set initial value if not already set
        if initial_value is None:
            initial_value = max(0, min_value or 0)
            if reset_to_value is not None:
                initial_value = reset_to_value
            elif max_value is not None:
                initial_value = max_value
        else:
            initial_value = character.evaluate_math(initial_value)
            # clamp initial value to min and max
            if min_value is not None:
                initial_value = max(initial_value, min_value)
            if max_value is not None:
                initial_value = min(initial_value, max_value)

        # length checks
        if desc and len(desc) > 1024:
            raise InvalidArgument("Description must be less than 1024 characters.")

        if title and len(title) >= 256:
            raise InvalidArgument("Title must be less than 256 characters.")

        if len(name) > 256:
            raise InvalidArgument("Name must be less than 256 characters.")

        return cls(
            character,
            name.strip(),
            initial_value,
            minv,
            maxv,
            reset,
            display_type,
            live_id,
            reset_to,
            reset_by,
            title,
            desc,
        )

    # ---------- main funcs ----------
    def get_min(self):
        if self._min_value is None:
            if self.min is None:
                self._min_value = -(2**31)
            else:
                self._min_value = self._character.evaluate_math(self.min)
        return self._min_value

    def get_max(self):
        if self._max_value is None:
            if self.max is None:
                self._max_value = 2**31 - 1
            else:
                self._max_value = self._character.evaluate_math(self.max)
        return self._max_value

    def get_reset_to(self):
        if self.reset_to is None:
            return None
        return self._character.evaluate_math(self.reset_to)

    def get_reset_by(self):
        if self.reset_by is None:
            return None
        return self._character.evaluate_annostr(self.reset_by)

    @property
    def value(self):
        return self._value

    def set(self, new_value: int, strict=False):
        minv = self.get_min()
        maxv = self.get_max()

        if strict:
            if new_value < minv:
                raise CounterOutOfBounds(f"You do not have enough remaining uses of {self.name}.")
            elif new_value > maxv:
                raise CounterOutOfBounds(f"{self.name} cannot be set to {new_value} (max {maxv}).")

        new_value = int(min(max(minv, new_value), maxv))
        old_value = self._value
        self._value = new_value

        if self.live_id and new_value != old_value:
            self._character.sync_consumable(self)
        return self._value

    def reset(self):
        """
        Resets the counter to its target value.

        :returns CustomCounterResetResult: (new_value: int, old_value: int, target_value: int, delta: str)
        """
        if self.reset_on == "none":
            raise NoReset()

        old_value = self.value

        # reset to: fixed value
        if self.reset_to is not None:
            target_value = self.get_reset_to()
            new_value = self.set(target_value)
            delta = f"{new_value - old_value:+}"

        # reset by: modify current value
        elif self.reset_by is not None:
            roll_result = d20.roll(self.get_reset_by())
            target_value = old_value + roll_result.total
            new_value = self.set(target_value)
            delta = f"+{roll_result.result}"

        # go to max
        elif self.max is not None:
            target_value = self.get_max()
            new_value = self.set(target_value)
            delta = f"{new_value - old_value:+}"

        # no reset
        else:
            raise NoReset()

        return CustomCounterResetResult(
            new_value=new_value, old_value=old_value, target_value=target_value, delta=delta
        )

    def full_str(self):
        _min = self.get_min()
        _max = self.get_max()
        _reset = self.RESET_MAP.get(self.reset_on)

        if self.display_type in constants.COUNTER_BUBBLES:
            assert self.max is not None
            val = f"{bubble_format(self.value, _max, chars=constants.COUNTER_BUBBLES[self.display_type])}\n"
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
        if self.reset_to is not None:
            val += f"**Resets To**: {self.get_reset_to()}"
        if self.reset_by is not None:
            val += f"**On Reset**: +{self.reset_by}"
        return val.strip()

    def __str__(self):
        _max = self.get_max()

        if self.display_type in constants.COUNTER_BUBBLES:
            assert self.max is not None
            out = bubble_format(self.value, _max, chars=constants.COUNTER_BUBBLES[self.display_type])
        else:
            if self.max is not None:
                out = f"{self.value}/{_max}"
            else:
                out = str(self.value)

        return out

    def __repr__(self):
        return f"<{type(self).__name__} name={self.name!r} __str__={self!s}>"


CustomCounterResetResult = collections.namedtuple(
    "CustomCounterResetResult", ["new_value", "old_value", "target_value", "delta"]
)
