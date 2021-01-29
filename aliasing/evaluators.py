import re
import time
from math import ceil, floor, sqrt

import draconic

from aliasing.api.functions import err, rand, randint, roll, safe_range, typeof, vroll
from aliasing.errors import EvaluationError

DEFAULT_BUILTINS = {
    # builtins
    'floor': floor, 'ceil': ceil, 'round': round, 'len': len, 'max': max, 'min': min, 'enumerate': enumerate,
    'range': safe_range, 'sqrt': sqrt, 'sum': sum, 'any': any, 'all': all, 'time': time.time,
    # ours
    'roll': roll, 'vroll': vroll, 'err': err, 'typeof': typeof,
    # legacy from simpleeval
    'rand': rand, 'randint': randint
}
SCRIPTING_RE = re.compile(
    r'(?<!\\)(?:'  # backslash-escape
    r'{{(?P<drac1>.+?)}}'  # {{drac1}}
    r'|(?<!{){(?P<roll>.+?)}'  # {roll}
    r'|<drac2>(?P<drac2>(?:.|\n)+?)</drac2>'  # <drac2>drac2</drac2>
    r'|<(?P<lookup>[^\s]+?)>'  # <lookup>
    r')'
)


# ==== mini-evaluators ====
class MathEvaluator(draconic.SimpleInterpreter):
    """Evaluator with basic math functions exposed."""

    @classmethod
    def with_character(cls, character, spell_override=None):
        names = character.get_scope_locals()
        if spell_override is not None:
            names['spell'] = spell_override

        builtins = {**names, **DEFAULT_BUILTINS}
        return cls(builtins=builtins)

    # also disable per-eval limits, limit should be global
    def _preflight(self):
        pass

    def transformed_str(self, string):
        """Transforms a dicecloud-formatted string (evaluating text in {})."""
        try:
            return re.sub(r'(?<!\\){(.+?)}', lambda m: str(self.eval(m.group(1).strip())), string)
        except Exception as ex:
            raise EvaluationError(ex, string)


class SpellEvaluator(MathEvaluator):
    @classmethod
    def with_caster(cls, caster, spell_override=None):
        names = caster.get_scope_locals()
        if spell_override is not None:
            names['spell'] = spell_override

        builtins = {**names, **DEFAULT_BUILTINS}
        return cls(builtins=builtins)

    def transformed_str(self, string, extra_names=None):
        """Parses a spell-formatted string (evaluating {{}} and replacing {} with rollstrings)."""
        original_names = None
        if extra_names:
            original_names = self.builtins.copy()
            self.builtins.update(extra_names)

        def evalrepl(match):
            try:
                if match.group('drac1'):  # {{}}
                    evalresult = self.eval(match.group('drac1').strip())
                elif match.group('roll'):  # {}
                    try:
                        evalresult = self.eval(match.group('roll').strip())
                    except:
                        evalresult = match.group(0)
                else:
                    evalresult = None
            except Exception as ex:
                raise EvaluationError(ex, match.group(0))

            return str(evalresult) if evalresult is not None else ''

        output = re.sub(SCRIPTING_RE, evalrepl, string)  # evaluate

        if original_names:
            self.builtins = original_names

        return output
