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
def simple_roll(dice):
    """
    Rolls dice and returns the total.

    .. note::
        This function's true signature is ``roll(dice)``.

    :param str dice: The dice to roll.
    :return: The roll's total, or 0 if an error was encountered.
    :rtype: int
    """
    return roll(dice).total


# vroll()
class SimpleRollResult:
    def __init__(self, dice, total, full, raw, roll_obj):
        self.dice = dice.strip()
        self.total = total
        self.full = full.strip()
        self.raw = raw
        self._roll = roll_obj

    def __str__(self):
        """
        Equivalent to ``result.full``.
        """
        return self.full

    def consolidated(self):
        """
        Gets the most simplified version of the roll string. Consolidates totals and damage types together.

        >>> result = vroll("3d6[fire]+1d4[cold]")
        >>> str(result)
        '3d6 (3, 3, 2) [fire] + 1d4 (2) [cold] = `10`'
        >>> result.consolidated()
        '8 [fire] + 2 [cold]'

        :rtype: str
        """
        return self._roll.consolidated()


def vroll(dice, multiply=1, add=0):
    """
    Rolls dice and returns a detailed roll result.

    :param str dice: The dice to roll.
    :param int multiply: How many times to multiply each set of dice by.
    :param int add: How many dice to add to each set of dice.
    :return: The result of the roll.
    :rtype: :class:`~cogs5e.funcs.scripting.functions.SimpleRollResult`
    """
    if multiply != 1 or add != 0:
        def subDice(matchobj):
            return str((int(matchobj.group(1)) * multiply) + add) + 'd' + matchobj.group(2)

        dice = re.sub(r'(\d+)d(\d+)', subDice, dice)
    rolled = roll(dice, inline=True)
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
    """
    Loads an object from a JSON string. See :func:`json.loads`.
    """
    return json.loads(jsonstr)


def dump_json(obj):
    """
    Serializes an object to a JSON string. See :func:`json.dumps`.
    """
    return json.dumps(obj)


# err()
class AliasException(AvraeException):
    pass


def err(reason):
    """
    Stops evaluation of an alias and shows the user an error.

    :param str reason: The error to show.
    :raises: AliasException
    """
    raise AliasException(reason)


# typeof()
def typeof(inst):
    """
    Returns the name of the type of an object.

    :param inst: The object to find the type of.
    :return: The type of the object.
    :rtype: str
    """
    return type(inst).__name__


DEFAULT_OPERATORS = simpleeval.DEFAULT_OPERATORS.copy()
DEFAULT_OPERATORS.pop(ast.Pow)

DEFAULT_FUNCTIONS = simpleeval.DEFAULT_FUNCTIONS.copy()
DEFAULT_FUNCTIONS.update({
    # builtins
    'floor': floor, 'ceil': ceil, 'round': round, 'len': len, 'max': max, 'min': min,
    'range': safe_range, 'sqrt': sqrt, 'sum': sum, 'any': any, 'all': all, 'time': time.time,
    # ours
    'roll': simple_roll, 'vroll': vroll, 'load_json': load_json, 'dump_json': dump_json,
    'err': err, 'typeof': typeof, 'argparse': argparse
})
