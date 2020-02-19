import ast
import json
import time
from math import ceil, floor, sqrt

import d20
import simpleeval
from d20 import roll
from simpleeval import IterableTooLong

from cogs5e.models.errors import AvraeException
from utils.argparser import argparse
from utils.dice import RerollableStringifier
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
    def __init__(self, result):
        """
        :type result: d20.RollResult
        """
        self.dice = d20.MarkdownStringifier().stringify(result.expr.roll)
        self.total = result.total
        self.full = str(result)
        self.result = result
        self.raw = result.expr
        self._roll = result

    def __str__(self):
        """
        Equivalent to ``result.full``.
        """
        return self.full

    def consolidated(self):
        """
        Gets the most simplified version of the roll string. Consolidates totals and damage types together.

        Note that this modifies the result expression in place!

        >>> result = vroll("3d6[fire]+1d4[cold]")
        >>> str(result)
        '3d6 (3, 3, 2) [fire] + 1d4 (2) [cold] = `10`'
        >>> result.consolidated()
        '8 [fire] + 2 [cold]'

        :rtype: str
        """
        d20.utils.simplify_expr(self._roll.expr, ambig_inherit='left')
        return RerollableStringifier().stringify(self._roll.expr.roll)


def vroll(dice, multiply=1, add=0):
    """
    Rolls dice and returns a detailed roll result.

    :param str dice: The dice to roll.
    :param int multiply: How many times to multiply each set of dice by.
    :param int add: How many dice to add to each set of dice.
    :return: The result of the roll.
    :rtype: :class:`~cogs5e.funcs.scripting.functions.SimpleRollResult`
    """
    dice_ast = d20.parse(dice)

    if multiply != 1 or add != 0:
        def mapper(node):
            if isinstance(node, d20.ast.Dice):
                node.num = (node.num * multiply) + add
            return node

        dice_ast = d20.utils.tree_map(mapper, dice_ast)

    try:
        rolled = roll(dice_ast)
    except d20.RollError:
        return None
    return SimpleRollResult(rolled)


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
