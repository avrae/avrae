import re
from typing import List, Optional

import disnake

import aliasing.api.combat
from cogs5e import initiative as init
from cogs5e.models.errors import InvalidArgument
from cogs5e.models.sheet.resistance import Resistance
from utils.enums import AdvantageType
from utils.functions import smart_trim
from . import Effect
from ..errors import AutomationException, InvalidIntExpression, TargetException
from ..results import IEffectResult


class LegacyIEffect(Effect):
    """Legacy implementation of initiative effects. Deprecated."""

    def __init__(
        self,
        name: str,
        duration: int,
        effects: str,
        end: bool = False,
        conc: bool = False,
        desc: str = None,
        stacking: bool = False,
        save_as: str = None,
        parent: str = None,
        **kwargs,
    ):
        super().__init__("ieffect", **kwargs)
        self.name = name
        self.duration = duration
        self.effects = effects
        self.tick_on_end = end
        self.concentration = conc
        self.desc = desc
        self.stacking = stacking
        self.save_as = save_as
        self.parent = parent

    def to_dict(self):
        out = super().to_dict()
        out.update({
            "name": self.name,
            "duration": self.duration,
            "effects": self.effects,
            "end": self.tick_on_end,
            "conc": self.concentration,
            "desc": self.desc,
            "stacking": self.stacking,
            "save_as": self.save_as,
            "parent": self.parent,
        })
        return out

    def run(self, autoctx):
        super().run(autoctx)
        if autoctx.target is None:
            raise TargetException(
                "Tried to add an effect without a target! Make sure all IEffect effects are inside of a Target effect."
            )

        if isinstance(self.duration, str):
            try:
                duration = autoctx.parse_intexpression(self.duration)
            except Exception:
                raise AutomationException(f"{self.duration} is not an integer (in effect duration)")
        else:
            duration = self.duration

        if self.desc:
            desc = autoctx.parse_annostr(self.desc)
            if len(desc) > 500:
                desc = f"{desc[:500]}..."
        else:
            desc = None

        duration = autoctx.args.last("dur", duration, int)
        conc_conflict = []
        if autoctx.target.combatant is not None:
            effect_args = autoctx.parse_annostr(self.effects)
            effect = init.InitiativeEffect.new(
                combat=autoctx.target.target.combat,
                combatant=autoctx.target.target,
                name=self.name,
                duration=duration,
                effect_args=effect_args,
                end_on_turn_end=self.tick_on_end,
                concentration=self.concentration,
                desc=desc,
            )
            conc_parent = None
            stack_parent = None

            # concentration spells
            if autoctx.conc_effect:
                if autoctx.conc_effect.combatant is autoctx.target.target and self.concentration:
                    raise InvalidArgument("Concentration spells cannot add concentration effects to the caster.")
                conc_parent = autoctx.conc_effect

            # stacking
            if self.stacking and (stack_parent := autoctx.target.target.get_effect(effect.name, strict=True)):
                count = 2
                new_name = f"{self.name} x{count}"
                while autoctx.target.target.get_effect(new_name, strict=True):
                    count += 1
                    new_name = f"{self.name} x{count}"
                effect = init.InitiativeEffect.new(
                    combat=autoctx.target.target.combat,
                    combatant=autoctx.target.target,
                    name=new_name,
                    effect_args=effect_args,
                )

            # parenting
            explicit_parent = None
            if self.parent is not None and (parent_ref := autoctx.metavars.get(self.parent, None)) is not None:
                if not isinstance(parent_ref, (IEffectMetaVar, aliasing.api.combat.SimpleEffect)):
                    raise InvalidArgument(
                        f"Could not set IEffect parent: The variable `{self.parent}` is not an IEffectMetaVar "
                        f"(got `{type(parent_ref).__name__}`)."
                    )
                # noinspection PyProtectedMember
                explicit_parent = parent_ref._effect

            if parent_effect := stack_parent or explicit_parent or conc_parent:
                effect.set_parent(parent_effect)

            # add
            effect_result = autoctx.target.target.add_effect(effect)
            autoctx.queue(f"**Effect**: {effect.get_str(description=False)}")
            if conc_conflict := effect_result["conc_conflict"]:
                autoctx.queue(f"**Concentration**: dropped {', '.join([e.name for e in conc_conflict])}")

            # save as
            if self.save_as is not None:
                autoctx.metavars[self.save_as] = IEffectMetaVar(effect)
        else:
            effect = init.InitiativeEffect.new(
                combat=None,
                combatant=None,
                name=self.name,
                duration=duration,
                effect_args=autoctx.parse_annostr(self.effects),
                end_on_turn_end=self.tick_on_end,
                concentration=self.concentration,
                desc=desc,
            )
            autoctx.queue(f"**Effect**: {effect.get_str(description=False)}")

        return IEffectResult(effect=effect, conc_conflict=conc_conflict)

    def build_str(self, caster, evaluator):
        super().build_str(caster, evaluator)
        return f"Effect: {self.name}"


class IEffect(Effect):
    def __init__(
        self,
        name: str,
        duration: Optional[str | int] = None,
        effects: Optional["_PassiveEffectsWrapper"] = None,
        attacks: List["_AttackInteractionWrapper"] = None,
        buttons: List["_ButtonInteractionWrapper"] = None,
        end: bool = False,
        conc: bool = False,
        desc: str = None,
        stacking: bool = False,
        save_as: str = None,
        parent: str = None,
        target_self: bool = False,
        tick_on_caster: bool = False,
        **kwargs,
    ):
        if attacks is None:
            attacks = []
        if buttons is None:
            buttons = []
        super().__init__("ieffect2", **kwargs)
        self.name = name
        self.duration = duration
        self.effects = effects
        self.attacks = attacks
        self.buttons = buttons
        self.end_on_turn_end = end
        self.concentration = conc
        self.desc = desc
        self.stacking = stacking
        self.save_as = save_as
        self.parent = parent
        self.target_self = target_self
        self.tick_on_caster = tick_on_caster

    @classmethod
    def from_data(cls, data):
        if data.get("effects") is not None:
            data["effects"] = _PassiveEffectsWrapper(data["effects"])
        if data.get("attacks") is not None:
            data["attacks"] = [_AttackInteractionWrapper.from_dict(d) for d in data["attacks"]]
        if data.get("buttons") is not None:
            data["buttons"] = [_ButtonInteractionWrapper.from_dict(d) for d in data["buttons"]]
        return super().from_data(data)

    def to_dict(self):
        out = super().to_dict()
        effects = self.effects.data if self.effects is not None else None
        out.update({
            "name": self.name,
            "duration": self.duration,
            "effects": effects,
            "attacks": [a.to_dict() for a in self.attacks],
            "buttons": [b.to_dict() for b in self.buttons],
            "end": self.end_on_turn_end,
            "conc": self.concentration,
            "desc": self.desc,
            "stacking": self.stacking,
            "save_as": self.save_as,
            "parent": self.parent,
            "target_self": self.target_self,
            "tick_on_caster": self.tick_on_caster,
        })
        return out

    def run(self, autoctx):
        super().run(autoctx)
        if autoctx.target is None:
            raise TargetException(
                "Tried to add an effect without a target! Make sure all IEffect effects are inside of a Target effect."
            )

        if isinstance(self.duration, str):
            try:
                duration = autoctx.parse_intexpression(self.duration)
            except Exception:
                raise AutomationException(f"{self.duration} is not an integer (in effect duration)")
        else:
            duration = self.duration

        if self.desc:
            desc = smart_trim(autoctx.parse_annostr(self.desc), max_len=500, dots="...")
        else:
            desc = None

        duration = autoctx.args.last("dur", duration, int)
        parsed_name = autoctx.parse_annostr(self.name)
        if self.effects is not None:
            effects = self.effects.resolve(autoctx)
        else:
            effects = init.effects.InitPassiveEffect()
        attacks = [a.resolve(autoctx) for a in self.attacks]
        buttons = [b.resolve(autoctx) for b in self.buttons]

        if self.target_self:
            combatant = autoctx.caster
            effect_target = f" on {combatant.name}"
            if not isinstance(combatant, init.Combatant):
                combatant = None
        else:
            combatant = autoctx.target.combatant
            effect_target = ""

        tick_on_combatant_id = None
        if self.tick_on_caster:
            if isinstance(autoctx.caster, init.Combatant):
                tick_on_combatant_id = autoctx.caster.id
            else:
                autoctx.meta_queue(
                    f"**Warning**: The effect `{parsed_name}`'s duration may be off by up to 1 round since the caster"
                    " is not in combat."
                )

        conc_conflict = []
        if combatant is not None:
            effect = init.InitiativeEffect.new(
                combat=combatant.combat,
                combatant=combatant,
                name=parsed_name,
                duration=duration,
                passive_effects=effects,
                attacks=attacks,
                buttons=buttons,
                end_on_turn_end=self.end_on_turn_end,
                concentration=self.concentration,
                desc=desc,
                tick_on_combatant_id=tick_on_combatant_id,
            )
            conc_parent = None
            stack_parent = None

            # concentration spells
            if autoctx.conc_effect:
                if autoctx.conc_effect.combatant is combatant and self.concentration:
                    raise InvalidArgument("Concentration spells cannot add concentration effects to the caster.")
                conc_parent = autoctx.conc_effect

            # stacking
            # find the next correct name for the effect and create a new one, without conflicting pieces
            if self.stacking and (stack_parent := combatant.get_effect(effect.name, strict=True)):
                count = 2
                new_name = f"{parsed_name} x{count}"
                while combatant.get_effect(new_name, strict=True):
                    count += 1
                    new_name = f"{parsed_name} x{count}"
                effect = init.InitiativeEffect.new(
                    combat=combatant.combat,
                    combatant=combatant,
                    name=new_name,
                    passive_effects=effects,
                )

            # parenting
            explicit_parent = None
            if self.parent is not None and (parent_ref := autoctx.metavars.get(self.parent, None)) is not None:
                if not isinstance(parent_ref, (IEffectMetaVar, aliasing.api.combat.SimpleEffect)):
                    raise InvalidArgument(
                        f"Could not set IEffect parent: The variable `{self.parent}` is not an initiative effect "
                        f"(expected IEffectMetaVar or SimpleEffect, got `{type(parent_ref).__name__}`)."
                    )
                # noinspection PyProtectedMember
                explicit_parent = parent_ref._effect
            # explicit support for parenting to the parent of this ieffect's parent
            elif self.parent == "ieffect.parent" and (parent_ref := autoctx.metavars.get("ieffect", None)) is not None:
                if not isinstance(parent_ref, aliasing.api.combat.SimpleEffect):
                    raise InvalidArgument(
                        f"Could not set IEffect parent: The variable `{self.parent}` is not an initiative effect "
                        f"(expected SimpleEffect, got `{type(parent_ref).__name__}`)."
                    )

                # parent_ref.parent is None in data tests
                if parent_ref.parent:
                    # noinspection PyProtectedMember
                    explicit_parent = parent_ref.parent._effect

            if parent_effect := stack_parent or explicit_parent or conc_parent:
                effect.set_parent(parent_effect)

            # add
            effect_result = combatant.add_effect(effect)
            autoctx.queue(f"**Effect{effect_target}**: {effect.get_str(description=False)}")
            if conc_conflict := effect_result["conc_conflict"]:
                autoctx.queue(f"**Concentration{effect_target}**: dropped {', '.join([e.name for e in conc_conflict])}")

            # save as
            if self.save_as is not None:
                autoctx.metavars[self.save_as] = IEffectMetaVar(effect)
        else:
            effect = init.InitiativeEffect.new(
                combat=None,
                combatant=None,
                name=parsed_name,
                duration=duration,
                passive_effects=effects,
                attacks=attacks,
                buttons=buttons,
                end_on_turn_end=self.end_on_turn_end,
                concentration=self.concentration,
                desc=desc,
            )
            autoctx.queue(f"**Effect{effect_target}**: {effect.get_str(description=False)}")

        return IEffectResult(effect=effect, conc_conflict=conc_conflict)

    def build_str(self, caster, evaluator):
        super().build_str(caster, evaluator)
        clean_name = re.sub(r"{+.+?}+", "<<Variable>>", self.name)
        return f"Effect: {clean_name}"


# ==== metavars ====
class IEffectMetaVar:
    """
    Proxy type to hold a reference to a created IEffect. This type can be used to set the parent of another IEffect
    later in the execution.
    """

    def __init__(self, effect: init.InitiativeEffect):
        self._effect = effect

    def __str__(self):
        return self._effect.get_str(description=False)

    def __eq__(self, other):
        return self._effect == other


# ==== helpers ====
class _PassiveEffectsWrapper:
    """This class stores the dict in ``effects`` and uses it to construct an InitPassiveEffect when necessary."""

    def __init__(self, data: dict[str, str | list[str]]):
        self.data = data

    def resolve(self, autoctx) -> init.effects.InitPassiveEffect:
        return init.effects.InitPassiveEffect(
            attack_advantage=self.resolve_attack_advantage(autoctx),
            to_hit_bonus=self.resolve_annotatedstring(autoctx, "to_hit_bonus"),
            damage_bonus=self.resolve_annotatedstring(autoctx, "damage_bonus"),
            magical_damage=bool(self.resolve_intexpression(autoctx, "magical_damage")),
            silvered_damage=bool(self.resolve_intexpression(autoctx, "silvered_damage")),
            resistances=self.resolve_resistances(autoctx, "resistances"),
            immunities=self.resolve_resistances(autoctx, "immunities"),
            vulnerabilities=self.resolve_resistances(autoctx, "vulnerabilities"),
            ignored_resistances=self.resolve_resistances(autoctx, "ignored_resistances"),
            ac_value=self.resolve_intexpression(autoctx, "ac_value"),
            ac_bonus=self.resolve_intexpression(autoctx, "ac_bonus"),
            max_hp_value=self.resolve_intexpression(autoctx, "max_hp_value"),
            max_hp_bonus=self.resolve_intexpression(autoctx, "max_hp_bonus"),
            save_bonus=self.resolve_annotatedstring(autoctx, "save_bonus"),
            save_adv=self.resolve_save_advs(autoctx, "save_adv"),
            save_dis=self.resolve_save_advs(autoctx, "save_dis"),
            check_bonus=self.resolve_annotatedstring(autoctx, "check_bonus"),
            check_adv=self.resolve_check_advs(autoctx, "check_adv"),
            check_dis=self.resolve_check_advs(autoctx, "check_dis"),
            dc_bonus=self.resolve_intexpression(autoctx, "dc_bonus"),
        )

    def resolve_annotatedstring(self, autoctx, attr: str) -> str | None:
        data = self.data.get(attr)
        if data is None:
            return None
        return autoctx.parse_annostr(data)

    def resolve_intexpression(self, autoctx, attr: str) -> int | None:
        data = self.data.get(attr)
        if data is None:
            return None
        return autoctx.parse_intexpression(data)

    def resolve_attack_advantage(self, autoctx) -> AdvantageType | None:
        """attack_advantage: a special IntExpression that must be a valid AdvantageType"""
        value = self.resolve_intexpression(autoctx, "attack_advantage")
        if value is None:
            return None
        try:
            return AdvantageType(value)
        except ValueError as e:
            raise InvalidIntExpression("`attack_advantage` must be -1, 0, 1, or 2.") from e

    def resolve_annotatedstring_list(self, autoctx, attr: str, allow_falsy=False) -> list[str]:
        """
        Given an attr, evaluates each element in data[attr] as an AnnotatedString. If allow_falsy is false, filters out
        empty strings from the resulting list.
        """
        data = self.data.get(attr)
        if data is None:
            return []
        if not isinstance(data, list):
            raise AutomationException(f"`{attr}` must be a list of AnnotatedString if supplied.")
        out = []
        for value in data:
            resolved = autoctx.parse_annostr(value)
            if resolved or allow_falsy:
                out.append(resolved)
        return out

    def resolve_resistances(self, autoctx, attr: str) -> list[Resistance]:
        """resistances: a list of AnnotatedString -> a list of Resistance"""
        data = self.resolve_annotatedstring_list(autoctx, attr)
        return [Resistance.from_str(dt) for dt in data]

    def resolve_save_advs(self, autoctx, attr: str) -> set[str]:
        """save_adv: a list of AnnotatedString -> a set of str"""
        data = self.resolve_annotatedstring_list(autoctx, attr)
        return init.effects.passive.resolve_save_advs(data)

    def resolve_check_advs(self, autoctx, attr: str) -> set[str]:
        """check_adv: a list of AnnotatedString -> a set of str"""
        data = self.resolve_annotatedstring_list(autoctx, attr)
        return init.effects.passive.resolve_check_advs(data)


class _AttackInteractionWrapper:
    """This is used to hold the AttackInteraction data until it is used (lazy deserialization)."""

    def __init__(
        self,
        attack,
        default_dc: Optional[str] = None,
        default_attack_bonus: Optional[str] = None,
        default_casting_mod: Optional[str] = None,
    ):
        self.attack = attack
        self.default_dc = default_dc
        self.default_attack_bonus = default_attack_bonus
        self.default_casting_mod = default_casting_mod

    @classmethod
    def from_dict(cls, d):
        from cogs5e.models.sheet.attack import Attack

        if not isinstance(d, dict):
            raise AutomationException("Invalid attack granted by an effect.")
        if "attack" not in d:
            raise AutomationException("Attacks granted by effects must include the 'attack' key.")
        return cls(
            attack=Attack.from_dict(d["attack"]),
            default_dc=d.get("defaultDC"),
            default_attack_bonus=d.get("defaultAttackBonus"),
            default_casting_mod=d.get("defaultCastingMod"),
        )

    def to_dict(self):
        return {
            "attack": self.attack.to_dict(),
            "defaultDC": self.default_dc,
            "defaultAttackBonus": self.default_attack_bonus,
            "defaultCastingMod": self.default_casting_mod,
        }

    def resolve(self, autoctx) -> init.effects.AttackInteraction:
        return init.effects.AttackInteraction(
            attack=self.attack,
            override_default_dc=maybe_intexpression(autoctx, self.default_dc),
            override_default_attack_bonus=maybe_intexpression(autoctx, self.default_attack_bonus),
            override_default_casting_mod=maybe_intexpression(autoctx, self.default_casting_mod),
            granting_spell_id=autoctx.spell.entity_id if autoctx.is_spell else None,
            granting_spell_cast_level=autoctx.get_cast_level(),
            original_choice=autoctx.metavars["choice"],
        )


class _ButtonInteractionWrapper:
    """This is used to hold the ButtonInteraction data until it is used (lazy deserialization)."""

    def __init__(
        self,
        label: str,
        automation,
        verb: Optional[str] = None,
        style: Optional[str] = None,
        default_dc: Optional[str] = None,
        default_attack_bonus: Optional[str] = None,
        default_casting_mod: Optional[str] = None,
    ):
        self.label = label
        self.automation = automation
        self.verb = verb
        self.style = style
        self.default_dc = default_dc
        self.default_attack_bonus = default_attack_bonus
        self.default_casting_mod = default_casting_mod

    @classmethod
    def from_dict(cls, d):
        from .. import Automation

        if not isinstance(d, dict):
            raise AutomationException("Invalid button granted by an effect.")
        if "automation" not in d:
            raise AutomationException("Buttons granted by effects must include the 'automation' key.")
        if "label" not in d:
            raise AutomationException("Buttons granted by effects must include the 'label' key.")

        automation = Automation.from_data(d["automation"])
        return cls(
            label=d["label"],
            automation=automation,
            verb=d.get("verb"),
            style=d.get("style"),
            default_dc=d.get("defaultDC"),
            default_attack_bonus=d.get("defaultAttackBonus"),
            default_casting_mod=d.get("defaultCastingMod"),
        )

    def to_dict(self):
        return {
            "label": self.label,
            "automation": self.automation.to_dict(),
            "verb": self.verb,
            "style": self.style,
            "defaultDC": self.default_dc,
            "defaultAttackBonus": self.default_attack_bonus,
            "defaultCastingMod": self.default_casting_mod,
        }

    def resolve(self, autoctx) -> init.effects.ButtonInteraction:
        label = autoctx.parse_annostr(self.label)

        verb = None
        if self.verb is not None:
            verb = autoctx.parse_annostr(self.verb)

        style = disnake.ButtonStyle.primary
        if self.style is not None:
            style = autoctx.parse_intexpression(self.style)
            if not 1 <= style <= 4:
                raise AutomationException("Button styles must be between 1 and 4 inclusive.")
            style = disnake.ButtonStyle(style)

        return init.effects.ButtonInteraction.new(
            automation=self.automation,
            label=label,
            verb=verb,
            style=style,
            override_default_dc=maybe_intexpression(autoctx, self.default_dc),
            override_default_attack_bonus=maybe_intexpression(autoctx, self.default_attack_bonus),
            override_default_casting_mod=maybe_intexpression(autoctx, self.default_casting_mod),
            granting_spell_id=autoctx.spell.entity_id if autoctx.is_spell else None,
            granting_spell_cast_level=autoctx.get_cast_level(),
            original_choice=autoctx.metavars["choice"],
        )


def maybe_intexpression(autoctx, value: Optional[str]):
    if value is None:
        return value
    return autoctx.parse_intexpression(value)
