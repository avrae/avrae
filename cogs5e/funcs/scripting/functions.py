import random

import d20
import draconic

from cogs5e.models.errors import AvraeException
from utils.dice import RerollableStringifier

MAX_ITER_LENGTH = 10000


# vroll(), roll()
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
    return _vroll(dice, multiply, add)


def roll(dice):
    """
    Rolls dice and returns the total.

    :param str dice: The dice to roll.
    :return: The roll's total, or 0 if an error was encountered.
    :rtype: int
    """
    return _roll(dice)


def _roll(dice, roller=None):
    if roller is None:
        roller = d20.Roller()

    try:
        result = roller.roll(dice)
    except d20.RollError:
        return 0
    return result.total


def _vroll(dice, multiply=1, add=0, roller=None):
    if roller is None:
        roller = d20.Roller()

    dice_ast = roller.parse(dice)

    if multiply != 1 or add != 0:
        def mapper(node):
            if isinstance(node, d20.ast.Dice):
                node.num = (node.num * multiply) + add
            return node

        dice_ast = d20.utils.tree_map(mapper, dice_ast)

    try:
        rolled = roller.roll(dice_ast)
    except d20.RollError:
        return None
    return SimpleRollResult(rolled)


# range()
def safe_range(start, stop=None, step=None):
    if stop is None and step is None:
        if start > MAX_ITER_LENGTH:
            raise draconic.IterableTooLong("This range is too large.")
        return list(range(start))
    elif stop is not None and step is None:
        if stop - start > MAX_ITER_LENGTH:
            raise draconic.IterableTooLong("This range is too large.")
        return list(range(start, stop))
    elif stop is not None and step is not None:
        if (stop - start) / step > MAX_ITER_LENGTH:
            raise draconic.IterableTooLong("This range is too large.")
        return list(range(start, stop, step))
    else:
        raise draconic.DraconicValueError("Invalid arguments passed to range()")


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


# rand(), randint(x)
def rand():
    return random.random()


def randint(top):
    return random.randrange(top)
