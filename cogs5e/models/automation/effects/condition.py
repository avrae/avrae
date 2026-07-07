from . import Effect
from ..errors import AutomationEvaluationException, StopExecution
from ..results import ConditionResult


class Condition(Effect):
    def __init__(self, condition: str, onTrue: list, onFalse: list, errorBehaviour: str = "false", **kwargs):
        super().__init__("condition", **kwargs)
        self.condition = condition
        self.on_true = onTrue
        self.on_false = onFalse
        self.error_behaviour = errorBehaviour

    @classmethod
    def from_data(cls, data):
        data["onTrue"] = Effect.deserialize(data["onTrue"])
        data["onFalse"] = Effect.deserialize(data["onFalse"])
        return super().from_data(data)

    def to_dict(self):
        out = super().to_dict()
        on_true = Effect.serialize(self.on_true)
        on_false = Effect.serialize(self.on_false)
        out.update({
            "condition": self.condition,
            "onTrue": on_true,
            "onFalse": on_false,
            "errorBehaviour": self.error_behaviour,
        })
        return out

    def run(self, autoctx):
        super().run(autoctx)
        did_error = False
        do_true = False
        do_false = False
        try:
            condition_result = autoctx.parse_annostr(self.condition, is_full_expression=True)
        except AutomationEvaluationException as e:
            did_error = True
            if self.error_behaviour == "true":
                do_true = True
            elif self.error_behaviour == "false":
                do_false = True
            elif self.error_behaviour == "both":
                do_true = True
                do_false = True
            elif self.error_behaviour == "neither":
                pass
            else:  # raise
                raise StopExecution(f"Error when evaluating condition `{self.condition}`:\n{e}")
        else:
            if condition_result:
                do_true = True
            else:
                do_false = True

        children = []
        if do_true:
            children += self.run_children(self.on_true, autoctx)
        if do_false:
            children += self.run_children(self.on_false, autoctx)

        return ConditionResult(did_true=do_true, did_false=do_false, did_error=did_error, children=children)

    def build_str(self, caster, evaluator):
        super().build_str(caster, evaluator)

        on_true = self.build_child_str(self.on_true, caster, evaluator)
        on_false = self.build_child_str(self.on_false, caster, evaluator)

        # neither: do nothing
        if not (on_true or on_false):
            return ""

        # one: return "maybe X".
        elif on_true and not on_false:
            return f"maybe {on_true}"
        elif on_false and not on_true:
            return f"maybe {on_false}"

        # both: return "X or Y", unless they're the same.
        elif on_true == on_false:
            return on_true
        else:
            return f"{on_true} or {on_false}"

    @property
    def children(self):
        return super().children + self.on_false + self.on_true
