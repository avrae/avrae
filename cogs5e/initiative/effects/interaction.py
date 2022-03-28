import abc
from typing import List

from cogs5e.models.errors import InvalidArgument
from cogs5e.models.sheet.attack import Attack, old_to_automation
from utils.argparser import ParsedArguments
from ._types import _IEffectT


class InitEffectInteraction(abc.ABC):
    type: str
    effect: _IEffectT  # injected by the parent effect during construction

    @classmethod
    def from_dict(cls, data):
        raise NotImplementedError

    def to_dict(self):
        raise NotImplementedError

    def __str__(self):
        raise NotImplementedError

    @staticmethod
    def deserialize(interaction_data: dict):
        match interaction_data:
            case {"type": AttackInteraction.type, **rest}:
                return AttackInteraction.from_dict(rest)
            case {"type": ButtonInteraction.type, **rest}:
                return ButtonInteraction.from_dict(rest)
        raise ValueError(f"Could not deserialize InitEffectInteraction: {interaction_data!r}")


class AttackInteraction(InitEffectInteraction):
    """
    This interaction adds an additional attack the combatant can take using !a.
    For compatibility with ``actionutils.run_attack``, this is actually just a wrapper around an Attack.
    """

    type = "attack"

    def __init__(self, attack: Attack, **kwargs):
        super().__init__(**kwargs)
        self.attack = attack

    @classmethod
    def from_dict(cls, data):
        return cls(
            attack=Attack.from_dict(data["attack"]),
        )

    def to_dict(self):
        return {
            "type": self.type,
            "attack": self.attack.to_dict(),
        }

    def __str__(self):
        if self.effect.combatant is None:
            return f"Attack: {self.attack.name}"
        return f"Attack: {self.attack.automation.build_str(self.effect.combatant)}"


class ButtonInteraction(InitEffectInteraction):
    """This interaction adds a button to the combatant's turn message to run some automation."""

    type = "button"

    def __init__(self, automation, label: str, **kwargs):
        super().__init__(**kwargs)
        self.automation = automation
        self.label = label

    @classmethod
    def from_dict(cls, data):
        from cogs5e.models.automation import Automation

        return cls(label=data["label"], automation=Automation.from_data(data["automation"]))

    def to_dict(self):
        return {"type": self.type, "label": self.label, "automation": self.automation.to_dict()}

    def __str__(self):
        return self.label


# ==== parsing ====
def init_interactions_from_args(args: ParsedArguments, effect_name: str) -> List[InitEffectInteraction]:
    out = []
    for attack_arg in args.get("-attack"):
        out.append(action_interaction_from_arg(attack_arg, effect_name=effect_name))
    return out


def action_interaction_from_arg(arg, effect_name):
    try:
        to_hit, damage, text = arg.split("|")
    except ValueError:
        raise InvalidArgument("`attack` arg must be formatted `HIT|DAMAGE|TEXT`")
    return AttackInteraction(attack=Attack(name=effect_name, automation=old_to_automation(to_hit, damage, text)))
