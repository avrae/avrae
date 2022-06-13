from typing import Any, Optional, TYPE_CHECKING

import math

from cogs5e.models.errors import InvalidArgument
from cogs5e.models.sheet.resistance import Resistance
from utils.argparser import argparse
from utils.constants import STAT_ABBREVIATIONS
from utils.functions import verbose_stat
from .types import ExplorerType
from .utils import create_effect_id

# exploration types are only defined when type checking
from ..models.embeds import EmbedWithColor

_ExploreT = Any
_ExplorerT = Any
if TYPE_CHECKING:
    from .explore import Explore
    from .explorer import Explorer

    _ExploreT = Explore
    _ExplorerT = Explorer


class EffectReference:
    def __init__(self, explorer_id, effect_id):
        self.explorer_id = explorer_id
        self.effect_id = effect_id

    @classmethod
    def from_effect(cls, effect):
        return cls(effect.explorer.id, effect.id)

    @classmethod
    def from_dict(cls, d):
        return cls(d["explorer_id"], d["effect_id"])

    def to_dict(self):
        return {"explorer_id": self.explorer_id, "effect_id": self.effect_id}


class Effect:
    def __init__(
        self,
        exploration: Optional[_ExploreT],
        explorer: Optional[_ExplorerT],
        id: str,
        name: str,
        duration: int,
        remaining: int,
        effect: dict,
        concentration: bool = False,
        children: list = None,
        parent: EffectReference = None,
        tonend: bool = True,
        desc: str = None,
    ):
        if children is None:
            children = []
        self.exploration = exploration
        self.explorer = explorer
        self.id = id
        self.name = name
        self.duration = duration
        self.remaining = remaining
        self._effect = effect
        self.concentration = bool(concentration)
        self.children = children
        self.parent = parent
        self.ticks_on_end = bool(tonend)
        self.desc = desc

    @classmethod
    def new(
        cls,
        exploration,
        explorer,
        name,
        duration,
        effect_args,
        concentration: bool = False,
        character=None,
        tick_on_end=False,
        desc: str = None,
    ):
        if isinstance(effect_args, str):
            if (explorer and explorer.type == ExplorerType.PLAYER) or character:
                effect_args = argparse(effect_args, explorer.character or character)
            else:
                effect_args = argparse(effect_args)

        effect_dict = {}
        for arg in effect_args:
            arg_arg = None
            if arg in LIST_ARGS:
                arg_arg = effect_args.get(arg, [])
            elif arg in VALID_ARGS:
                arg_arg = effect_args.last(arg)

            if arg in SPECIAL_ARGS:
                effect_dict[arg] = SPECIAL_ARGS[arg][0](arg_arg, name)
            elif arg_arg is not None:
                effect_dict[arg] = arg_arg

        try:
            duration = int(duration)
        except (ValueError, TypeError):
            raise InvalidArgument("Effect duration must be an integer.")

        id = create_effect_id()

        return cls(
            exploration,
            explorer,
            id,
            name,
            duration,
            duration,
            effect_dict,
            concentration=concentration,
            tonend=tick_on_end,
            desc=desc,
        )

    @classmethod
    def from_dict(cls, raw, exploration, explorer):
        children = [EffectReference.from_dict(r) for r in raw.pop("children")]
        parent = raw.pop("parent")
        if parent:
            parent = EffectReference.from_dict(parent)
        return cls(exploration, explorer, children=children, parent=parent, **raw)

    def to_dict(self):
        children = [ref.to_dict() for ref in self.children]
        parent = self.parent.to_dict() if self.parent else None
        return {
            "id": self.id,
            "name": self.name,
            "duration": self.duration,
            "remaining": self.remaining,
            "effect": self.effect,
            "concentration": self.concentration,
            "children": children,
            "parent": parent,
            "tonend": self.ticks_on_end,
            "desc": self.desc,
        }

    def set_parent(self, parent):
        """Sets the parent of an effect."""
        self.parent = EffectReference.from_effect(parent)
        parent.children.append(EffectReference.from_effect(self))
        return self

    @property
    def effect(self):
        return self._effect

    # --- stringification ---
    def __str__(self):
        return self.get_str(duration=True, parenthetical=True, concentration=True, description=True)

    def get_short_str(self):
        """Gets a short string describing the effect (for display in init summary)"""
        return self.get_str(duration=True, parenthetical=False, concentration=False, description=False)

    def get_str(self, duration=True, parenthetical=True, concentration=True, description=True):
        """More customizable as to what actually shows."""
        out = [self.name]
        if duration:
            the_duration = self._duration_str()
            if the_duration:
                out.append(the_duration)
        if parenthetical:
            out.append(self._parenthetical_str())
        if concentration and self.concentration:
            out.append("<C>")
        if description and self.desc:
            out.append(f"\n - {self.desc}")
        return " ".join(out).strip()

    def _duration_cmp(self):
        """
        Returns a tuple of (remaining_rounds, has_ticked_this_round, turn_index, end?).
        Find the minimal of all of these in the effect parent hierarchy to find the effect that will end first.
        """
        remaining = self.remaining if self.remaining >= 0 else float("inf")
        if self.explorer is None or self.exploration is None:
            return remaining, 0, 0, 1 if self.ticks_on_end else 0
        has_ticked_this_round = 1
        return remaining, int(has_ticked_this_round), 0, 1 if self.ticks_on_end else 0

    def _duration_str(self):
        """Gets a string describing this effect's duration."""
        # find minimum duration in parent hierarchy
        min_duration = self._duration_cmp()
        parent = self.get_parent_effect()
        seen_parents = {self.id}
        while parent is not None and parent.id not in seen_parents:
            seen_parents.add(parent.id)
            min_duration = min(min_duration, parent._duration_cmp())
            parent = parent.get_parent_effect()

        # unpack and build string
        remaining, _, index, ticks_on_end = min_duration
        if math.isinf(remaining):
            return ""
        elif remaining > 5_256_000:  # years
            divisor, unit = 5256000, "year"
        elif remaining > 438_000:  # months
            divisor, unit = 438000, "month"
        elif remaining > 100_800:  # weeks
            divisor, unit = 100800, "week"
        elif remaining > 14_400:  # days
            divisor, unit = 14400, "day"
        elif remaining > 600:  # hours
            divisor, unit = 600, "hour"
        elif remaining > 10:  # minutes
            divisor, unit = 10, "minute"
        else:  # rounds
            divisor, unit = 1, "round"

        rounded = round(remaining / divisor, 1) if divisor > 1 else remaining
        return f"[{rounded} {unit}s]"

    def _parenthetical_str(self):
        """Gets the descriptive text inside parentheses."""
        text = []
        if self.effect:
            text.append(self._effect_str())
        if parent := self.get_parent_effect():
            text.append(f"Parent: {parent.name}")  # name of parent effect
        if text:
            return f"({'; '.join(text)})"
        return ""

    def _effect_str(self):
        out = []
        for k, v in self.effect.items():
            if k in SPECIAL_ARGS:
                out.append(f"{VALID_ARGS.get(k)}: {SPECIAL_ARGS[k][1](v)}")
            elif isinstance(v, list):
                out.append(f"{VALID_ARGS.get(k)}: {', '.join(v)}")
            else:
                out.append(f"{VALID_ARGS.get(k)}: {v}")
        return "; ".join(out)

    # --- hooks ---
    def on_round(self, num_rounds=1):
        """
        Reduces the round counter if applicable, and removes itself if at 0.
        """
        message_str = ""
        if self.remaining >= 0 and not self.ticks_on_end:
            if self.remaining - num_rounds <= 0:
                if self.name.lower() == "lantern":
                    message_str = "lantern winks out!"
                elif self.name.lower() == "torch":
                    message_str = "torch burns out!"
                self.remove()
            self.remaining -= num_rounds
        return message_str

    def on_round_end(self, num_rounds=1):
        """
        Reduces the round counter if applicable, and removes itself if at 0.
        """

        if self.remaining >= 0 and self.ticks_on_end:
            if self.remaining - num_rounds <= 0:
                self.remove()
            self.remaining -= num_rounds

    # parenting
    def get_parent_effect(self) -> Optional["Effect"]:
        if self.parent:
            return self._effect_from_reference(self.parent)
        return None

    def get_children_effects(self):
        """Returns an iterator of Effects of this Effect's children."""
        for e in self.children.copy():
            child = self._effect_from_reference(e)
            if child:
                yield child
            else:
                self.children.remove(e)  # effect was removed elsewhere; disown it

    def _effect_from_reference(self, e: EffectReference):
        if self.exploration is None:
            return None
        explorer = self.exploration.explorer_by_id(e.explorer_id)
        if explorer is None:
            return None
        effect = explorer.effect_by_id(e.effect_id)
        if effect is None:
            return None
        return effect

    # misc
    def remove(self, removed=None):
        if removed is None:
            removed = [self]
        for effect in self.get_children_effects():
            if effect not in removed:  # no infinite recursion please
                removed.append(effect)
                effect.remove(removed)
        if self.explorer is not None:
            self.explorer.remove_effect(self)


# ---- attack ieffect ----
def parse_attack_arg(arg, name):
    data = arg.split("|")
    if not len(data) == 3:
        raise InvalidArgument("`attack` arg must be formatted `HIT|DAMAGE|TEXT`")
    return {"name": name, "attackBonus": data[0] or None, "damage": data[1] or None, "details": data[2] or None}


def parse_attack_str(atk):
    try:
        return f"{int(atk['attackBonus']):+}|{atk['damage']}"
    except (TypeError, ValueError):
        return f"{atk['attackBonus']}|{atk['damage']}"


# ---- resistance ieffect ----
def parse_resist_arg(arg, _):
    return [Resistance.from_dict(r).to_dict() for r in arg]


def parse_resist_str(resist_list):
    return ", ".join([str(Resistance.from_dict(r)) for r in resist_list])


# ---- sadv/sdis ieffect ----
def parse_stat_choice(args, _):
    for i, arg in enumerate(args):
        if arg == "True":  # hack: sadv/sdis on their own should be equivalent to -sadv/sdis all
            args[i] = arg = "all"
        else:
            args[i] = arg = arg[:3].lower()  # only check first three arg characters against STAT_ABBREVIATIONS
        if arg not in STAT_ABBREVIATIONS and arg != "all":
            raise InvalidArgument(f"{arg} is not a valid stat")
    return args


def parse_stat_str(stat_list):
    if "all" in stat_list:
        return "All"
    return ", ".join(verbose_stat(s) for s in stat_list)


# ==== effect defs ====
LIST_ARGS = ("resist", "immune", "vuln", "neutral", "sadv", "sdis")
SPECIAL_ARGS = {  # 2-tuple of effect, str
    "attack": (parse_attack_arg, parse_attack_str),
    "resist": (parse_resist_arg, parse_resist_str),
    "sadv": (parse_stat_choice, parse_stat_str),
    "sdis": (parse_stat_choice, parse_stat_str),
}
VALID_ARGS = {
    "d": "Damage Bonus",
    "ac": "AC",
    "attack": "Attack",
    "maxhp": "Max HP",
    "cb": "Check Bonus",
    "magical": "Magical Damage",
    "silvered": "Silvered Damage",
    "b": "Attack Bonus",
    "adv": "Attack Advantage",
    "dis": "Attack Disadvantage",
    "sb": "Save Bonus",
    "sadv": "Save Advantage",
    "sdis": "Save Disadvantage",
    "resist": "Resistance",
    "immune": "Immunity",
    "vuln": "Vulnerability",
    "neutral": "Neutral",
}
