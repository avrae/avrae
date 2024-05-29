import copy
from typing import Callable

import d20
import draconic
from d20.utils import TreeType

import aliasing.api.statblock
from cogs5e.models.sheet.statblock import StatBlock


def maybe_alias_statblock(target):
    """Returns the AliasStatBlock for the target if applicable."""
    if not isinstance(target, (StatBlock, str, type(None))):
        raise ValueError("target must be a statblock, str, or None")
    if isinstance(target, StatBlock):
        return aliasing.api.statblock.AliasStatBlock(target)

    return aliasing.api.statblock.AliasStatBlock(StatBlock(name=target or "Target"))


def upcast_scaled_dice(effect, autoctx, dice_ast):
    """Scales the dice of the cast to its appropriate amount (handling cantrip scaling and higher level addition)."""
    if effect.cantripScale:
        level = autoctx.caster.spellbook.caster_level
        if level < 5:
            level_dice = 1
        elif level < 11:
            level_dice = 2
        elif level < 17:
            level_dice = 3
        else:
            level_dice = 4
        level_dice = autoctx.args.last("cantripdice", default=level_dice, type_=int)

        def mapper(node):
            if isinstance(node, d20.ast.Dice):
                node.num = level_dice
            return node

        dice_ast = d20.utils.tree_map(mapper, dice_ast)

    if effect.higher:
        higher = effect.higher.get(str(autoctx.get_cast_level()))
        if higher:
            higher_ast = d20.parse(higher)
            dice_ast.roll = d20.ast.BinOp(dice_ast.roll, "+", higher_ast.roll)

    return dice_ast


def mi_mapper(minimum: int) -> Callable[[d20.ast.Node], d20.ast.Node]:
    """Returns a function that maps Dice AST objects to OperatedDice with miX attached."""

    def mapper(node: d20.ast.Node):
        if isinstance(node, d20.ast.Dice):
            miX = d20.ast.SetOperator("mi", [d20.ast.SetSelector(None, int(minimum))])
            return d20.ast.OperatedDice(node, miX)
        return node

    return mapper


def max_mapper(node: d20.ast.Node):
    """A function that maps Dice AST objects to OperatedDice that set their values to their maximum."""
    if isinstance(node, d20.ast.Dice):
        miX = d20.ast.SetOperator("mi", [d20.ast.SetSelector(None, node.size)])
        return d20.ast.OperatedDice(node, miX)
    return node


def max_add_crit_mapper(node: d20.ast.Node):
    """A function that adds the maximum value of each Dice AST node as a literal

    :return: A tuple containing the node and a bool for if the tree mapper should continue.
    :rtype: tuple(node, bool)
    """
    if isinstance(node, d20.ast.OperatedDice):
        return d20.ast.BinOp(node, "+", d20.ast.Literal(node.value.num * node.value.size)), False
    if isinstance(node, d20.ast.Dice):
        return d20.ast.BinOp(node, "+", d20.ast.Literal(node.num * node.size)), False
    return node, True


def crit_mapper(node: d20.ast.Node):
    """A function that doubles the number of dice for each Dice AST node."""
    if isinstance(node, d20.ast.Dice):
        return d20.ast.Dice(node.num * 2, node.size)
    return node


def double_dice_crit_mapper(node: d20.ast.Node):
    """A function that replaces each Dice AST node with itself multiplied by 2.

    :return: A tuple containing the node and a bool for if the tree mapper should continue.
    :rtype: tuple(node, bool)
    """
    if isinstance(node, (d20.ast.OperatedDice, d20.ast.Dice)):
        return d20.ast.BinOp(node, "*", d20.ast.Literal(2)), False
    return node, True


def crit_dice_gen(dice_ast: d20.ast.Node, critdice: int):
    """A function that finds the size of left most Dice AST node and generates crit dice based on that, for
    crit types that double all original dice, but not any additional crit dice. By finding the left most dice,
    we do our best to ensure its based on the weapon/source and not any other additional bonuses."""
    left = d20.utils.leftmost(dice_ast)

    # if we're at the bottom of the branch and it's the dice, add *critdice*
    if isinstance(left, d20.ast.Dice):
        return d20.ast.Dice(critdice, left.size)


def critdice_tree_update(dice_ast: d20.ast.Node, critdice: int):
    """
    Modifies the AST by adding *critdice* dice to any leftmost Dice, branching recursively on any Set.

    .. note::
        This mutates the AST, so it should be copied before calling to avoid mutating the cached AST.
    """
    left = dice_ast
    while left.children:
        # if we encounter a set going down the left branch, branch and run recursively on all children
        if isinstance(left, d20.ast.NumberSet):
            for child in left.children:
                critdice_tree_update(child, critdice)
            return
        # otherwise continue down the left branch
        left = left.children[0]

    # if we're at the bottom of the branch and it's the dice, add *critdice*
    if isinstance(left, d20.ast.Dice):
        left.num += critdice


def stringify_intexpr(evaluator, expr):
    """
    For use in str builders - use the given evaluator to return the result of the intexpr, or nan if any exception is
    caught

    :rtype: int or float
    """
    if isinstance(expr, (int, float)):
        return expr

    try:
        return int(evaluator.eval(str(expr)))
    except (TypeError, ValueError, draconic.DraconicException):
        return float("nan")


def target_hp_or_default(target, default):
    """Returns the target's hp if defined, otherwise default"""
    if isinstance(target, StatBlock) and target.hp is not None:
        return target.hp
    else:
        return default


def tree_map_prefix(func: Callable[[TreeType], tuple[TreeType, bool]], node: TreeType) -> TreeType:
    """
    Returns a copy of the tree, with each node replaced with ``func(node)[0]``.

    :param func: A transformer function that takes a node and returns a tuple (replacement,
                 continue_operations_on_children).
    :param node: The root of the tree to transform.
    """
    copied = copy.copy(node)
    operated, continue_operations_on_children = func(copied)
    if not continue_operations_on_children:
        # we still recurse on the children so that it satisfies the "returns a copy of the tree" property
        # so make the function a no-op
        func = lambda x: (x, True)  # noqa E731
    for i, child in enumerate(copied.children):
        copied.set_child(i, tree_map_prefix(func, child))
    return operated
