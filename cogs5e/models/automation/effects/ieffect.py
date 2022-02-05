from cogs5e import initiative as init
from cogs5e.models.errors import InvalidArgument
from . import Effect
from ..errors import AutomationException, TargetException
from ..results import IEffectResult


class IEffect(Effect):
    def __init__(
        self, name: str, duration: int, effects: str, end: bool = False, conc: bool = False,
        desc: str = None, stacking: bool = False, save_as: str = None, parent: str = None, **kwargs
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
        out.update(
            {
                "name": self.name, "duration": self.duration, "effects": self.effects, "end": self.tick_on_end,
                "conc": self.concentration, "desc": self.desc, "stacking": self.stacking, "save_as": self.save_as,
                "parent": self.parent
            }
        )
        return out

    def run(self, autoctx):
        super().run(autoctx)
        if autoctx.target is None:
            raise TargetException(
                "Tried to add an effect without a target! Make sure all IEffect effects are inside "
                "of a Target effect."
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

        duration = autoctx.args.last('dur', duration, int)
        conc_conflict = []
        if isinstance(autoctx.target.target, init.Combatant):
            effect = init.Effect.new(
                autoctx.target.target.combat, autoctx.target.target, self.name,
                duration, autoctx.parse_annostr(self.effects), tick_on_end=self.tick_on_end,
                concentration=self.concentration, desc=desc
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
                effect.desc = None
                effect.duration = effect.remaining = -1
                effect.concentration = False
                original_name = effect.name
                effect.name = f"{original_name} x{count}"
                while autoctx.target.target.get_effect(effect.name, strict=True):
                    count += 1
                    effect.name = f"{original_name} x{count}"

            # parenting
            explicit_parent = None
            if self.parent is not None and (parent_ref := autoctx.metavars.get(self.parent, None)) is not None:
                if not isinstance(parent_ref, IEffectMetaVar):
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
            if conc_conflict := effect_result['conc_conflict']:
                autoctx.queue(f"**Concentration**: dropped {', '.join([e.name for e in conc_conflict])}")

            # save as
            if self.save_as is not None:
                autoctx.metavars[self.save_as] = IEffectMetaVar(effect)
        else:
            effect = init.Effect.new(
                None, None, self.name, duration, autoctx.parse_annostr(self.effects),
                tick_on_end=self.tick_on_end, concentration=self.concentration, desc=desc
            )
            autoctx.queue(f"**Effect**: {effect.get_str(description=False)}")

        return IEffectResult(effect=effect, conc_conflict=conc_conflict)

    def build_str(self, caster, evaluator):
        super().build_str(caster, evaluator)
        return f"Effect: {self.name}"


class IEffectMetaVar:
    """
    Proxy type to hold a reference to a created IEffect. This type can be used to set the parent of another IEffect
    later in the execution.
    """

    def __init__(self, effect: init.Effect):
        self._effect = effect

    def __str__(self):
        return self._effect.get_str(description=False)

    def __eq__(self, other):
        return self._effect == other
