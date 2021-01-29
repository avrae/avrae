import re
import time
from math import ceil, floor, sqrt

from aliasing.functions import err, rand, randint, roll, safe_range, typeof, vroll

GVAR_SIZE_LIMIT = 100_000
SVAR_SIZE_LIMIT = 10_000
UVAR_SIZE_LIMIT = 10_000
CVAR_SIZE_LIMIT = 10_000
ALIAS_SIZE_LIMIT = 100_000
SNIPPET_SIZE_LIMIT = 5_000

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
