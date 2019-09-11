import ast
import json
import re
import time
from math import ceil, floor, sqrt

import simpleeval
from simpleeval import IterableTooLong

from cogs5e.funcs.dice import roll
from cogs5e.models.errors import AvraeException
from utils.argparser import argparse
from . import MAX_ITER_LENGTH


# roll()
def simple_roll(rollStr):
    return roll(rollStr).total


# vroll()
class SimpleRollResult:
    def __init__(self, dice, total, full, raw, roll_obj):
        self.dice = dice.strip()
        self.total = total
        self.full = full.strip()
        self.raw = raw
        self._roll = roll_obj

    def __str__(self):
        return self.full

    def consolidated(self):
        return self._roll.consolidated()


def verbose_roll(rollStr, multiply=1, add=0):
    if multiply != 1 or add != 0:
        def subDice(matchobj):
            return str((int(matchobj.group(1)) * multiply) + add) + 'd' + matchobj.group(2)

        rollStr = re.sub(r'(\d+)d(\d+)', subDice, rollStr)
    rolled = roll(rollStr, inline=True)
    try:
        return SimpleRollResult(rolled.rolled, rolled.total, rolled.skeleton,
                                [part.to_dict() for part in rolled.raw_dice.parts], rolled)
    except AttributeError:
        return None


# range()
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


# json
def load_json(jsonstr):
    return json.loads(jsonstr)


def dump_json(obj):
    return json.dumps(obj)


# err()
class AliasException(AvraeException):
    pass


def raise_alias_exception(reason):
    raise AliasException(reason)


# typeof()
def typeof(inst):
    return type(inst).__name__


DEFAULT_OPERATORS = simpleeval.DEFAULT_OPERATORS.copy()
DEFAULT_OPERATORS.pop(ast.Pow)

DEFAULT_FUNCTIONS = simpleeval.DEFAULT_FUNCTIONS.copy()
DEFAULT_FUNCTIONS.update({
    # builtins
    'floor': floor, 'ceil': ceil, 'round': round, 'len': len, 'max': max, 'min': min,
    'range': safe_range, 'sqrt': sqrt, 'sum': sum, 'any': any, 'all': all, 'time': time.time,
    # ours
    'roll': simple_roll, 'vroll': verbose_roll, 'load_json': load_json, 'dump_json': dump_json,
    'err': raise_alias_exception, 'typeof': typeof, 'argparse': argparse
})
