import ast
import re
from math import ceil, floor

from simpleeval import SimpleEval, IterableTooLong, EvalWithCompoundTypes

from cogs5e.funcs.scripting.helpers import MAX_ITER_LENGTH


class MathEvaluator(SimpleEval):
    """Evaluator with basic math functions exposed."""
    MATH_FUNCTIONS = {'ceil': ceil, 'floor': floor, 'max': max, 'min': min, 'round': round}

    def __init__(self, operators=None, functions=None, names=None):
        if not functions:
            functions = self.MATH_FUNCTIONS
        super(MathEvaluator, self).__init__(operators, functions, names)

    @classmethod
    def with_character(cls, character):
        names = {}
        names.update(character.get_cvars())
        names.update(character.get_stat_vars())
        names['spell'] = character.get_spell_ab() - character.get_prof_bonus()
        return cls(names=names)

    def parse(self, string):
        """Parses a dicecloud-formatted string (evaluating text in {})."""
        return re.sub(r'(?<!\\){(.+?)}', lambda m: str(self.eval(m.group(1))), string)


class ScriptingEvaluator(EvalWithCompoundTypes):
    """Evaluator with compound types, comprehensions, and assignments exposed."""

    def __init__(self, operators=None, functions=None, names=None):
        super(ScriptingEvaluator, self).__init__(operators, functions, names)

        self.nodes.update({
            ast.JoinedStr: self._eval_joinedstr,  # f-string
            ast.FormattedValue: self._eval_formattedvalue,  # things in f-strings
            ast.ListComp: self._eval_listcomp,
            ast.SetComp: self._eval_setcomp,
            ast.DictComp: self._eval_dictcomp,
            ast.comprehension: self._eval_comprehension
        })

        self.assign_nodes = {
            ast.Name: self._assign_name,
            ast.Tuple: self._assign_tuple,
            ast.Subscript: self._assign_subscript
        }

        self._loops = 0

    def eval(self, expr):  # allow for ast.Assign to set names
        """ evaluate an expression, using the operators, functions and
            names previously set up. """

        # set a copy of the expression aside, so we can give nice errors...

        self.expr = expr

        # and evaluate:
        expression = ast.parse(expr.strip()).body[0]
        if isinstance(expression, ast.Expr):
            return self._eval(expression.value)
        elif isinstance(expression, ast.Assign):
            return self._eval_assign(expression)
        else:
            raise TypeError("Unknown ast body type")

    def _eval_assign(self, node):
        names = node.targets[0]
        values = node.value
        self._assign(names, values)

    def _assign(self, names, values, eval_values=True):
        try:
            handler = self.assign_nodes[type(names)]
        except KeyError:
            raise TypeError(f"Assignment to {type(names).__name__} is not allowed")
        return handler(names, values, eval_values)

    def _assign_name(self, name, value, eval_value=True):
        if not isinstance(self.names, dict):
            raise TypeError("cannot set name: incorrect name type")
        else:
            if eval_value:
                value = self._eval(value)
            self.names[name.id] = value

    def _assign_tuple(self, names, values, eval_values=True):
        if not all(isinstance(n, ast.Name) for n in names.elts):
            raise TypeError("Assigning to multiple non-names via unpack is not allowed")
        names = [n.id for n in names.elts]  # turn ast into str
        if not isinstance(values, ast.Tuple):
            raise ValueError(f"unequal unpack: {len(names)} names, 1 value")
        if eval_values:
            values = [self._eval(n) for n in values.elts]  # get what we actually want to assign
        else:
            values = values.elts
        if not len(values) == len(names):
            raise ValueError(f"unequal unpack: {len(names)} names, {len(values)} values")
        else:
            if not isinstance(self.names, dict):
                raise TypeError("cannot set name: incorrect name type")
            else:
                for name, value in zip(names, values):
                    self.names[name] = value  # and assign it

    def _assign_subscript(self, name, value, eval_value=True):
        if eval_value:
            value = self._eval(value)

        container = self._eval(name.value)
        key = self._eval(name.slice)
        container[key] = value
        self._assign(name.value, container, eval_values=False)

    def _eval_joinedstr(self, node):
        return ''.join(str(self._eval(n)) for n in node.values)

    def _eval_formattedvalue(self, node):
        if node.format_spec:
            fmt = "{:" + self._eval(node.format_spec) + "}"
            return fmt.format(self._eval(node.value))
        else:
            return self._eval(node.value)

    def _eval_listcomp(self, node):
        return list(self._eval(node.elt) for generator in node.generators for _ in self._eval(generator))

    def _eval_setcomp(self, node):
        return set(self._eval(node.elt) for generator in node.generators for _ in self._eval(generator))

    def _eval_dictcomp(self, node):
        return {self._eval(node.key): self._eval(node.value) for generator in node.generators for _ in
                self._eval(generator)}

    def _eval_comprehension(self, node):
        iterable = self._eval(node.iter)
        if len(iterable) + self._loops > MAX_ITER_LENGTH:
            raise IterableTooLong("Execution limit exceeded: too many loops.")
        self._loops += len(iterable)
        for item in iterable:
            self._assign(node.target, item, False)
            if all(self._eval(stmt) for stmt in node.ifs):
                yield item
