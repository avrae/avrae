import logging

from ..errors import AutomationException, StopExecution

__all__ = (
    'Effect', 'Target', 'Attack', 'Save', 'Damage', 'TempHP', 'IEffect', 'Roll', 'Text', 'SetVariable', 'Condition',
    'UseCounter',
)

log = logging.getLogger(__name__)


class Effect:
    def __init__(self, type_, meta=None, **_):  # ignore bad kwargs
        self.type = type_
        if meta:  # meta is deprecated
            meta = Effect.deserialize(meta)
        else:
            meta = []
        self.meta = meta

    @staticmethod
    def deserialize(data):
        return [EFFECT_MAP[e['type']].from_data(e) for e in data]

    @staticmethod
    def serialize(obj_list):
        return [e.to_dict() for e in obj_list]

    @staticmethod
    def run_children(child, autoctx):
        results = []
        for effect in child:
            try:
                result = effect.run(autoctx)
                if result is not None:
                    results.append(result)
            except StopExecution:
                raise
            except AutomationException as e:
                autoctx.meta_queue(f"**Error**: {e}")
        return results

    # required methods
    @classmethod
    def from_data(cls, data):  # catch-all
        data.pop('type')
        return cls(**data)

    def to_dict(self):
        meta = Effect.serialize(self.meta or [])
        return {"type": self.type, "meta": meta}

    def run(self, autoctx):
        log.debug(f"Running {self.type}")
        if self.meta:
            for metaeffect in self.meta:
                metaeffect.run(autoctx)

    def build_str(self, caster, evaluator):
        if self.meta:
            for metaeffect in self.meta:
                # metaeffects shouldn't add anything to a str - they should set up annostrs
                metaeffect.build_str(caster, evaluator)
        return "I do something (you shouldn't see this)"

    @staticmethod
    def build_child_str(child, caster, evaluator):
        out = []
        for effect in child:
            effect_str = effect.build_str(caster, evaluator)
            if effect_str:
                out.append(effect_str)
        return ', '.join(out)

    @property
    def children(self):
        """Returns the child effects of this effect."""
        return self.meta


from . import attack, condition, damage, ieffect, roll, save, target, temphp, text, usecounter, variable

Target = target.Target
Attack = attack.Attack
Save = save.Save
Damage = damage.Damage
TempHP = temphp.TempHP
IEffect = ieffect.IEffect
Roll = roll.Roll
Text = text.Text
SetVariable = variable.SetVariable
Condition = condition.Condition
UseCounter = usecounter.UseCounter

EFFECT_MAP = {
    "target": Target,
    "attack": Attack,
    "save": Save,
    "damage": Damage,
    "temphp": TempHP,
    "ieffect": IEffect,
    "roll": Roll,
    "text": Text,
    "variable": SetVariable,
    "condition": Condition,
    "counter": UseCounter,
}
