import abc
from typing import List, Optional

import disnake

from cogs5e.models.errors import InvalidArgument
from cogs5e.models.sheet.attack import Attack, old_to_automation
from utils.argparser import ParsedArguments
from .._types import _IEffectT
from ..utils import create_button_interaction_id


class InitEffectInteraction(abc.ABC):
    effect: _IEffectT  # injected by the parent effect during construction

    @classmethod
    def from_dict(cls, data):
        raise NotImplementedError

    def to_dict(self):
        raise NotImplementedError

    def __str__(self):
        raise NotImplementedError


class AttackInteraction(InitEffectInteraction):
    """
    This interaction adds an additional attack the combatant can take using !a.
    For compatibility with ``actionutils.run_attack``, this is actually just a wrapper around an Attack.
    """

    def __init__(self, attack: Attack):
        self.attack = attack

    @classmethod
    def from_dict(cls, data):
        return cls(
            attack=Attack.from_dict(data["attack"]),
        )

    def to_dict(self):
        return {
            "attack": self.attack.to_dict(),
        }

    def __str__(self):
        return f"Attack: {self.attack.name}"


class ButtonInteraction(InitEffectInteraction):
    """This interaction adds a button to the combatant's turn message to run some automation."""

    def __init__(
        self,
        id: str,
        automation,
        label: str,
        verb: Optional[str] = None,
        style: disnake.ButtonStyle = disnake.ButtonStyle.primary,
    ):
        self.id = id
        self.automation = automation
        self.label = label
        self.verb = verb
        self.style = style

    @classmethod
    def new(
        cls,
        automation,
        label: str,
        verb: Optional[str] = None,
        style: disnake.ButtonStyle = disnake.ButtonStyle.primary,
    ):
        return cls(id=create_button_interaction_id(), automation=automation, label=label, verb=verb, style=style)

    @classmethod
    def from_dict(cls, data):
        from cogs5e.models.automation import Automation

        return cls(
            id=data["id"],
            automation=Automation.from_data(data["automation"]),
            label=data["label"],
            verb=data["verb"],
            style=disnake.ButtonStyle(data["style"]),
        )

    def to_dict(self):
        return {
            "id": self.id,
            "automation": self.automation.to_dict(),
            "label": self.label,
            "verb": self.verb,
            "style": int(self.style),
        }

    def __str__(self):
        return self.label


# ==== parsing ====
def attack_interactions_from_args(args: ParsedArguments, effect_name: str) -> List[AttackInteraction]:
    out = []
    for attack_arg in args.get("attack"):
        out.append(action_interaction_from_arg(attack_arg, effect_name=effect_name))
    return out


def action_interaction_from_arg(arg, effect_name):
    try:
        to_hit, damage, text = arg.split("|")
    except ValueError:
        raise InvalidArgument("`attack` arg must be formatted `HIT|DAMAGE|TEXT`")
    return AttackInteraction(attack=Attack(name=effect_name, automation=old_to_automation(to_hit, damage, text)))
