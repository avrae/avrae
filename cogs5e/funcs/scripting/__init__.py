import re

SCRIPTING_RE = re.compile(r'(?<!\\)(?:(?:{{(.+?)}})|(?:<([^\s]+)>)|(?:(?<!{){(.+?)}))')
MAX_ITER_LENGTH = 10000

from cogs5e.funcs.scripting.combat import SimpleCombat, SimpleCombatant, SimpleEffect, SimpleGroup
from cogs5e.funcs.scripting.evaluators import MathEvaluator, ScriptingEvaluator, SpellEvaluator
from cogs5e.funcs.scripting.functions import DEFAULT_FUNCTIONS, DEFAULT_OPERATORS
from cogs5e.funcs.scripting.helpers import get_aliases, get_gvar_values, get_servaliases, \
    get_servsnippets, get_snippets, get_uvars, parse_no_char, parse_snippets, set_uvar

# does no one find this weird?

if __name__ == '__main__':
    e = ScriptingEvaluator(None)
    while True:
        print(e.eval(input()))
