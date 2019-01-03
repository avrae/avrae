import ast
import json
import re
import time
from math import floor, ceil, sqrt

import simpleeval
from simpleeval import IterableTooLong

from cogs5e.funcs.dice import roll
from cogs5e.funcs.scripting.helpers import MAX_ITER_LENGTH
from cogs5e.models.errors import AvraeException


def simple_roll(rollStr):
    return roll(rollStr).total


class SimpleRollResult:
    def __init__(self, dice, total, full, raw):
        self.dice = dice.strip()
        self.total = total
        self.full = full.strip()
        self.raw = raw

    def __str__(self):
        return self.full


def verbose_roll(rollStr, multiply=1, add=0):
    if multiply != 1 or add != 0:
        def subDice(matchobj):
            return str((int(matchobj.group(1)) * multiply) + add) + 'd' + matchobj.group(2)

        rollStr = re.sub(r'(\d+)d(\d+)', subDice, rollStr)
    rolled = roll(rollStr, inline=True)
    try:
        return SimpleRollResult(rolled.rolled, rolled.total, rolled.skeleton,
                                [part.to_dict() for part in rolled.raw_dice.parts])
    except AttributeError:
        return None


def safe_range(start, stop=None, step=None):
    if stop is None and step is None:
        if start > MAX_ITER_LENGTH:
            raise IterableTooLong("This range is too large.")
        return list(range(start))
    elif stop is not None and step is None:
        if stop - start > MAX_ITER_LENGTH:
            raise IterableTooLong("This range is too large.")
        return list(range(start, stop))
    elif stop is not None and step is not None:
        if (stop - start) / step > MAX_ITER_LENGTH:
            raise IterableTooLong("This range is too large.")
        return list(range(start, stop, step))
    else:
        raise ValueError("Invalid arguments passed to range()")


def load_json(jsonstr):
    return json.loads(jsonstr)


def dump_json(obj):
    return json.dumps(obj)


class AliasException(AvraeException):
    pass


def raise_alias_exception(reason):
    raise AliasException(reason)


DEFAULT_OPERATORS = simpleeval.DEFAULT_OPERATORS.copy()
DEFAULT_OPERATORS.pop(ast.Pow)

DEFAULT_FUNCTIONS = simpleeval.DEFAULT_FUNCTIONS.copy()
DEFAULT_FUNCTIONS.update({'floor': floor, 'ceil': ceil, 'round': round, 'len': len, 'max': max, 'min': min,
                          'range': safe_range, 'sqrt': sqrt, 'sum': sum, 'any': any, 'all': all,
                          'roll': simple_roll, 'vroll': verbose_roll, 'load_json': load_json, 'dump_json': dump_json,
                          'time': time.time, 'err': raise_alias_exception})
