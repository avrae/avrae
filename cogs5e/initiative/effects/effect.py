from typing import Iterator, List, Optional, Tuple, Union

import math

from cogs5e.models.errors import InvalidArgument
from utils.argparser import ParsedArguments, argparse
from ._types import _CharacterT, _CombatT, _CombatantT
from .interaction import InitEffectInteraction, init_interactions_from_args
from .passive import InitPassiveEffect
from ..types import CombatantType
from ..utils import create_effect_id


class InitEffectReference:
    def __init__(self, combatant_id, effect_id):
        self.combatant_id = combatant_id
        self.effect_id = effect_id

    @classmethod
    def from_effect(cls, effect):
        return cls(effect.combatant.id, effect.id)

    @classmethod
    def from_dict(cls, d):
        return cls(d["combatant_id"], d["effect_id"])

    def to_dict(self):
        return {"combatant_id": self.combatant_id, "effect_id": self.effect_id}


class InitiativeEffect:
    def __init__(
        self,
        combat: Optional[_CombatT],
        combatant: Optional[_CombatantT],
        id: str,
        name: str,
        effects: InitPassiveEffect = None,
        interactions: List[InitEffectInteraction] = None,
        duration: Optional[int] = None,
        end_round: Optional[int] = None,
        end_on_turn_end: bool = False,
        concentration: bool = False,
        children: List[InitEffectReference] = None,
        parent: Optional[InitEffectReference] = None,
        desc: str = None,
    ):
        if effects is None:
            effects = InitPassiveEffect()
        if interactions is None:
            interactions = []
        if children is None:
            children = []

        # inject effect instance into the child interaction
        for interaction in interactions:
            interaction.effect = self

        self.combat = combat
        self.combatant = combatant
        self.id = id
        self.name = name
        self.effects = effects
        self.interactions = interactions
        self.duration = duration
        self.end_round = end_round
        self.end_on_turn_end = bool(end_on_turn_end)
        self.concentration = bool(concentration)
        self.children = children
        self.parent = parent
        self.desc = desc

    @classmethod
    def new(
        cls,
        combat: Optional[_CombatT],
        combatant: Optional[_CombatantT],
        name: str,
        effect_args: Union[str, ParsedArguments],
        duration: Optional[int],
        end_on_turn_end: bool = False,
        concentration: bool = False,
        character: Optional[_CharacterT] = None,
        desc: Optional[str] = None,
    ):
        if isinstance(effect_args, str):
            if (combatant and combatant.type == CombatantType.PLAYER) or character:
                effect_args = argparse(effect_args, character=combatant.character or character)
            else:
                effect_args = argparse(effect_args)

        effects = InitPassiveEffect.from_args(effect_args)
        interactions = init_interactions_from_args(effect_args, effect_name=name)

        # duration handling
        if duration is not None:
            try:
                duration = int(duration)
                if duration < 0:
                    duration = None
            except (ValueError, TypeError):
                raise InvalidArgument("Effect duration must be an integer or None.")

        if combat is not None and duration is not None:
            end_round = combat.round_num + duration
            if end_on_turn_end:
                end_round -= 1
        else:
            end_round = None

        return cls(
            combat=combat,
            combatant=combatant,
            id=create_effect_id(),
            name=name,
            effects=effects,
            interactions=interactions,
            duration=duration,
            end_round=end_round,
            end_on_turn_end=end_on_turn_end,
            concentration=concentration,
            desc=desc,
        )

    @classmethod
    def from_dict(cls, d: dict, combat: _CombatT, combatant: _CombatantT):
        if d.get("_v", 1) < 2:
            return  # todo: JIT migrator
        effects = InitPassiveEffect.from_dict(d["effects"])
        interactions = [InitEffectInteraction.deserialize(i) for i in d["interactions"]]
        children = [InitEffectReference.from_dict(r) for r in d["children"]]
        if parent_data := d["parent"]:
            parent = InitEffectReference.from_dict(parent_data)
        else:
            parent = None
        return cls(
            combat=combat,
            combatant=combatant,
            id=d["id"],
            name=d["name"],
            effects=effects,
            interactions=interactions,
            duration=d["duration"],
            end_round=d["end_round"],
            end_on_turn_end=d["end_on_turn_end"],
            concentration=d["concentration"],
            children=children,
            parent=parent,
            desc=d["desc"],
        )

    def to_dict(self):
        effects = self.effects.to_dict()
        interactions = [i.to_dict() for i in self.interactions]
        children = [ref.to_dict() for ref in self.children]
        parent = self.parent.to_dict() if self.parent else None
        return {
            "id": self.id,
            "name": self.name,
            "effects": effects,
            "interactions": interactions,
            "duration": self.duration,
            "end_round": self.end_round,
            "end_on_turn_end": self.end_on_turn_end,
            "concentration": self.concentration,
            "children": children,
            "parent": parent,
            "desc": self.desc,
            "_v": 2,
        }

    def set_parent(self, parent: "InitiativeEffect"):
        """Sets the parent of an effect."""
        self.parent = InitEffectReference.from_effect(parent)
        parent.children.append(InitEffectReference.from_effect(self))
        return self

    # --- stringification ---
    def __str__(self):
        return self.get_str(duration=True, parenthetical=True, concentration=True, description=True)

    def get_short_str(self) -> str:
        """Gets a short string describing the effect (for display in init summary)"""
        return self.get_str(duration=True, parenthetical=False, concentration=False, description=False)

    def get_str(self, duration=True, parenthetical=True, concentration=True, description=True) -> str:
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

    def _duration_cmp(self) -> Tuple[int, int, int]:
        """
        Returns a tuple of (end_round, end_turn_index, end?).
        Find the minimal of all of these in the effect parent hierarchy to find the effect that will end first.
        """
        end_round = self.end_round if self.end_round is not None else float("inf")

        if self.combatant is None:
            return end_round, 0, 1 if self.end_on_turn_end else 0

        index = self.combatant.index
        return end_round, index, 1 if self.end_on_turn_end else 0

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
        end_round, tick_index, ticks_on_end = min_duration
        if math.isinf(end_round):
            return ""

        if self.combat is None:
            ticks_remaining = self.duration
        elif self.combatant is None or self.combat.index is None:
            ticks_remaining = self.end_round - self.combat.round_num
        else:
            has_ticked_this_round = self.combat.index > tick_index if ticks_on_end else self.combat.index >= tick_index
            ticks_remaining = self.end_round - (self.combat.round_num - (0 if has_ticked_this_round else 1))

        if ticks_remaining <= 1:  # effect ends on next tick
            if self.combat is not None and self.combatant is not None and tick_index != self.combatant.index:
                # another combatant's turn
                combatant = self.combat.combatants[tick_index]
                if ticks_on_end:
                    return f"[until end of {combatant.name}'s turn]"
                else:
                    return f"[until start of {combatant.name}'s next turn]"
            else:
                # our turn, or unknown combatant
                if ticks_on_end:
                    return "[until end of turn]"
                else:
                    return "[until start of next turn]"
        elif ticks_remaining > 5_256_000:  # years
            divisor, unit = 5256000, "year"
        elif ticks_remaining > 438_000:  # months
            divisor, unit = 438000, "month"
        elif ticks_remaining > 100_800:  # weeks
            divisor, unit = 100800, "week"
        elif ticks_remaining > 14_400:  # days
            divisor, unit = 14400, "day"
        elif ticks_remaining > 600:  # hours
            divisor, unit = 600, "hour"
        elif ticks_remaining > 10:  # minutes
            divisor, unit = 10, "minute"
        else:  # rounds
            divisor, unit = 1, "round"

        rounded = round(ticks_remaining / divisor, 1) if divisor > 1 else ticks_remaining
        return f"[{rounded} {unit}s]"

    def _parenthetical_str(self):
        """Gets the descriptive text inside parentheses."""
        text = []
        if self.effects:
            text.append(str(self.effects))
        for interaction in self.interactions:
            interaction_str = str(interaction)
            if interaction_str:
                text.append(interaction_str)
        if parent := self.get_parent_effect():
            text.append(f"Parent: {parent.name}")  # name of parent effect
        if text:
            return f"({'; '.join(text)})"
        return ""

    # --- hooks ---
    def on_turn(self, num_turns=1):
        """
        Called on the start of the parent combatant's turn in combat.
        Removes itself if the effect is no longer applicable.
        """
        if self.combat is None or self.end_round is None:
            return

        # if we end on the start of turn and it's the round to end and we're going forwards, remove ourselves
        if (not self.end_on_turn_end) and self.combat.round_num >= self.end_round and num_turns > 0:
            self.remove()

    def on_turn_end(self, num_turns=1):
        """
        Called on the end of the parent combatant's turn in combat.
        Removes itself if the effect is no longer applicable.
        """
        if self.combat is None or self.end_round is None:
            return

        # if we end on the end of turn and it's the round to end and we're going forwards, remove ourselves
        if self.end_on_turn_end and self.combat.round_num >= self.end_round and num_turns > 0:
            self.remove()

    # parenting
    def get_parent_effect(self) -> Optional["InitiativeEffect"]:
        if self.parent:
            return self._effect_from_reference(self.parent)
        return None

    def get_children_effects(self) -> Iterator["InitiativeEffect"]:
        """Returns an iterator of Effects of this Effect's children."""
        for e in self.children.copy():
            child = self._effect_from_reference(e)
            if child:
                yield child
            else:
                self.children.remove(e)  # effect was removed elsewhere; disown it

    def _effect_from_reference(self, e: InitEffectReference) -> Optional["InitiativeEffect"]:
        if self.combat is None:
            return None
        combatant = self.combat.combatant_by_id(e.combatant_id)
        if combatant is None:
            return None
        effect = combatant.effect_by_id(e.effect_id)
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
        if self.combatant is not None:
            self.combatant.remove_effect(self)
