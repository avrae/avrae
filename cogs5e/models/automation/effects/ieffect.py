from cogs5e.models import initiative as init
from cogs5e.models.errors import InvalidArgument
from . import Effect
from ..errors import AutomationException, TargetException
from ..results import IEffectResult


class IEffect(Effect):
    def __init__(self, name: str, duration: int, effects: str, end: bool = False, conc: bool = False,
                 desc: str = None, stacking: bool=False, **kwargs):
        super().__init__("ieffect", **kwargs)
        self.name = name
        self.duration = duration
        self.effects = effects
        self.tick_on_end = end
        self.concentration = conc
        self.desc = desc
        self.stacking = stacking

    def to_dict(self):
        out = super().to_dict()
        out.update({"name": self.name, "duration": self.duration, "effects": self.effects, "end": self.tick_on_end,
                    "conc": self.concentration, "desc": self.desc, "stacking": self.stacking})
        return out

    def run(self, autoctx):
        super().run(autoctx)
        if autoctx.target is None:
            raise TargetException("Tried to add an effect without a target! Make sure all IEffect effects are inside "
                                  "of a Target effect.")

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
            effect = init.Effect.new(autoctx.target.target.combat, autoctx.target.target, self.name,
                                     duration, autoctx.parse_annostr(self.effects), tick_on_end=self.tick_on_end,
                                     concentration=self.concentration, desc=desc)

            # concentration spells
            if autoctx.conc_effect:
                if autoctx.conc_effect.combatant is autoctx.target.target and self.concentration:
                    raise InvalidArgument("Concentration spells cannot add concentration effects to the caster.")
                effect.set_parent(autoctx.conc_effect)

            # stacking
            if self.stacking and (stack_parent := autoctx.target.target.get_effect(effect.name, strict=True)):
                count = 2
                effect.desc = None
                effect.duration = effect.remaining = -1
                effect.concentration = False
                effect.set_parent(stack_parent)
                original_name = effect.name
                effect.name = f"{original_name} x{count}"
                while autoctx.target.target.get_effect(effect.name, strict=True):
                    count += 1
                    effect.name = f"{original_name} x{count}"

            # add
            effect_result = autoctx.target.target.add_effect(effect)
            autoctx.queue(f"**Effect**: {effect.get_str(description=False)}")
            if conc_conflict := effect_result['conc_conflict']:
                autoctx.queue(f"**Concentration**: dropped {', '.join([e.name for e in conc_conflict])}")
        else:
            effect = init.Effect.new(None, None, self.name, duration, autoctx.parse_annostr(self.effects),
                                     tick_on_end=self.tick_on_end, concentration=self.concentration, desc=desc)
            autoctx.queue(f"**Effect**: {effect.get_str(description=False)}")

        return IEffectResult(effect=effect, conc_conflict=conc_conflict)

    def build_str(self, caster, evaluator):
        super().build_str(caster, evaluator)
        return self.name
