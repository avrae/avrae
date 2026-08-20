import d20

from utils.dice import RerollableStringifier


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
        d20.utils.simplify_expr(self._roll.expr, ambig_inherit="left")
        return RerollableStringifier().stringify(self._roll.expr.roll)
