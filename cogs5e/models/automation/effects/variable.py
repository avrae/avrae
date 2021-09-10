import draconic

from . import Effect
from ..errors import AutomationEvaluationException, AutomationException, StopExecution
from ..results import SetVariableResult


class SetVariable(Effect):
    def __init__(self, name: str, value: str, higher: dict = None, onError: str = None, **kwargs):
        super().__init__('variable', **kwargs)
        self.name = name
        self.value = value
        self.higher = higher
        self.on_error = onError

    def to_dict(self):
        out = super().to_dict()
        out.update({"name": self.name, "value": self.value})
        if self.higher is not None:
            out['higher'] = self.higher
        if self.on_error is not None:
            out['onError'] = self.on_error
        return out

    def run(self, autoctx):
        super().run(autoctx)
        level_value = self.value
        # handle upcast
        if autoctx.is_spell and self.higher and autoctx.get_cast_level() != autoctx.spell.level:
            higher = self.higher.get(str(autoctx.get_cast_level()))
            if higher:
                level_value = higher

        did_error = False

        # parse value
        try:
            value = autoctx.parse_annostr(level_value, is_full_expression=True)
        except AutomationEvaluationException as e:
            did_error = True
            if self.on_error is not None:
                value = autoctx.parse_annostr(self.on_error, is_full_expression=True)
            else:
                raise StopExecution(f"Error in SetVariable (`{self.name} = {level_value}`):\n{e}")

        # cast to int
        try:
            final_value = int(value)
        except (TypeError, ValueError):
            raise AutomationException(f"{value} cannot be interpreted as an integer "
                                      f"(in `{self.name} = {level_value}`).")

        # bind
        autoctx.metavars[self.name] = final_value
        return SetVariableResult(value=value, did_error=did_error)

    def build_str(self, caster, evaluator):
        super().build_str(caster, evaluator)
        try:
            value = evaluator.eval(self.value)
        except draconic.DraconicException:
            try:
                value = evaluator.eval(self.on_error)
            except draconic.DraconicException:
                value = self.value
        try:
            evaluator.builtins[self.name] = int(value)
        except (TypeError, ValueError):
            evaluator.builtins[self.name] = value
        return ""
