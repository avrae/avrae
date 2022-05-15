import abc
from typing import List, Optional, TYPE_CHECKING

import disnake

import gamedata
from cogs5e.models.errors import InvalidArgument
from cogs5e.models.sheet.attack import Attack, old_to_automation
from utils.argparser import ParsedArguments
from ..utils import create_button_interaction_id

if TYPE_CHECKING:
    from .effect import InitiativeEffect


class InitEffectInteraction(abc.ABC):
    effect: "InitiativeEffect"  # injected by the parent effect during construction

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

    def __init__(
        self,
        attack: Attack,
        *,
        override_default_dc: Optional[int] = None,
        override_default_attack_bonus: Optional[int] = None,
        override_default_casting_mod: Optional[int] = None,
        granting_spell_id: Optional[int] = None,
        granting_spell_cast_level: Optional[int] = None,
    ):
        self.inner_attack = attack
        self.override_default_dc = override_default_dc
        self.override_default_attack_bonus = override_default_attack_bonus
        self.override_default_casting_mod = override_default_casting_mod
        self.granting_spell_id = granting_spell_id
        self.granting_spell_cast_level = granting_spell_cast_level

    @classmethod
    def from_dict(cls, data):
        return cls(
            attack=Attack.from_dict(data["attack"]),
            override_default_dc=data.get("override_default_dc"),
            override_default_attack_bonus=data.get("override_default_attack_bonus"),
            override_default_casting_mod=data.get("override_default_casting_mod"),
            granting_spell_id=data.get("granting_spell_id"),
            granting_spell_cast_level=data.get("granting_spell_cast_level"),
        )

    def to_dict(self):
        return {
            "attack": self.inner_attack.to_dict(),
            "override_default_dc": self.override_default_dc,
            "override_default_attack_bonus": self.override_default_attack_bonus,
            "override_default_casting_mod": self.override_default_casting_mod,
            "granting_spell_id": self.granting_spell_id,
            "granting_spell_cast_level": self.granting_spell_cast_level,
        }

    @property
    def attack(self) -> Attack:
        """
        To handle the custom runtime settings like overriding the default attack bonus, we set the
        ``__run_automation_kwargs__`` attribute.

        Not the most elegant solution ever, but oh well.
        """
        attack = Attack.copy(self.inner_attack)
        if self.granting_spell_id is not None:
            spell = gamedata.compendium.lookup_entity(gamedata.Spell.entity_type, self.granting_spell_id)
        else:
            spell = None
        attack.__run_automation_kwargs__ = dict(
            ab_override=self.override_default_attack_bonus,
            dc_override=self.override_default_dc,
            spell_override=self.override_default_casting_mod,
            spell=spell,
            spell_level_override=self.granting_spell_cast_level,
        )
        return attack

    def __str__(self):
        return f"Attack: {self.inner_attack.name}"


class ButtonInteraction(InitEffectInteraction):
    """This interaction adds a button to the combatant's turn message to run some automation."""

    def __init__(
        self,
        id: str,
        automation,
        label: str,
        verb: Optional[str] = None,
        style: disnake.ButtonStyle = disnake.ButtonStyle.primary,
        *,
        override_default_dc: Optional[int] = None,
        override_default_attack_bonus: Optional[int] = None,
        override_default_casting_mod: Optional[int] = None,
        granting_spell_id: Optional[int] = None,
        granting_spell_cast_level: Optional[int] = None,
    ):
        self.id = id
        self.automation = automation
        self.label = label
        self.verb = verb
        self.style = style
        self.override_default_dc = override_default_dc
        self.override_default_attack_bonus = override_default_attack_bonus
        self.override_default_casting_mod = override_default_casting_mod
        self.granting_spell_id = granting_spell_id
        self.granting_spell_cast_level = granting_spell_cast_level

    @classmethod
    def new(
        cls,
        automation,
        label: str,
        verb: Optional[str] = None,
        style: disnake.ButtonStyle = disnake.ButtonStyle.primary,
        *,
        override_default_dc: Optional[int] = None,
        override_default_attack_bonus: Optional[int] = None,
        override_default_casting_mod: Optional[int] = None,
        granting_spell_id: Optional[int] = None,
        granting_spell_cast_level: Optional[int] = None,
    ):
        return cls(
            id=create_button_interaction_id(),
            automation=automation,
            label=label,
            verb=verb,
            style=style,
            override_default_dc=override_default_dc,
            override_default_attack_bonus=override_default_attack_bonus,
            override_default_casting_mod=override_default_casting_mod,
            granting_spell_id=granting_spell_id,
            granting_spell_cast_level=granting_spell_cast_level,
        )

    @classmethod
    def from_dict(cls, data):
        from cogs5e.models.automation import Automation

        return cls(
            id=data["id"],
            automation=Automation.from_data(data["automation"]),
            label=data["label"],
            verb=data["verb"],
            style=disnake.ButtonStyle(data["style"]),
            override_default_dc=data.get("override_default_dc"),
            override_default_attack_bonus=data.get("override_default_attack_bonus"),
            override_default_casting_mod=data.get("override_default_casting_mod"),
            granting_spell_id=data.get("granting_spell_id"),
            granting_spell_cast_level=data.get("granting_spell_cast_level"),
        )

    def to_dict(self):
        return {
            "id": self.id,
            "automation": self.automation.to_dict(),
            "label": self.label,
            "verb": self.verb,
            "style": int(self.style),
            "override_default_dc": self.override_default_dc,
            "override_default_attack_bonus": self.override_default_attack_bonus,
            "override_default_casting_mod": self.override_default_casting_mod,
            "granting_spell_id": self.granting_spell_id,
            "granting_spell_cast_level": self.granting_spell_cast_level,
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
