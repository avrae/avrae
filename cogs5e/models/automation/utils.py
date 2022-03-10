from typing import Callable

import d20
import draconic

import aliasing.api.statblock
from cogs5e.models.sheet.statblock import StatBlock


def maybe_alias_statblock(target):
    """Returns the AliasStatBlock for the target if applicable."""
    if not isinstance(target, (StatBlock, str, type(None))):
        raise ValueError("target must be a statblock, str, or None")
    return (
        aliasing.api.statblock.AliasStatBlock(target)
        if isinstance(target, StatBlock)
        else target
    )


def upcast_scaled_dice(effect, autoctx, dice_ast):
    """Scales the dice of the cast to its appropriate amount (handling cantrip scaling and higher level addition)."""
    if autoctx.is_spell:
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


def crit_mapper(node: d20.ast.Node):
    """A function that doubles the number of dice for each Dice AST node."""
    if isinstance(node, d20.ast.Dice):
        return d20.ast.Dice(node.num * 2, node.size)
    return node


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
