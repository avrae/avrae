import d20


class VerboseMDStringifier(d20.MarkdownStringifier):
    def _str_expression(self, node):
        if node.comment:
            comment = node.comment.rstrip("\\")

            if len(comment) == 0:
                comment = None
        else:
            comment = None

        return f"**{comment or 'Result'}**: {self._stringify(node.roll)}\n**Total**: {int(node.total)}"


class PersistentRollContext(d20.RollContext):
    """
    A roll context that tracks lifetime rolls as well as individual rolls.
    """

    def __init__(self, max_rolls=1000, max_total_rolls=None):
        """
        :param max_rolls: The maximum number of rolls allowed in an individual roll.
        :param max_total_rolls: The maximum number of rolls allowed throughout this object's lifetime.
        """
        super().__init__(max_rolls)
        self.max_total_rolls = max_total_rolls or max_rolls
        self.total_rolls = 0

    def count_roll(self, n=1):
        super().count_roll(n)
        self.total_rolls += 1
        if self.total_rolls > self.max_total_rolls:
            raise d20.TooManyRolls("Too many dice rolled.")


class RerollableStringifier(d20.SimpleStringifier):
    """A stringifier that's guaranteed to output a string that can be rerolled without modifying the semantics."""

    def _stringify(self, node):
        if not node.kept:
            return None
        return super()._stringify(node)

    def _str_expression(self, node):
        return self._stringify(node.roll)

    def _str_literal(self, node):
        return str(node.total)

    def _str_parenthetical(self, node):
        return f"({self._stringify(node.value)})"

    def _str_set(self, node):
        out = f"{', '.join([self._stringify(v) for v in node.values if v.kept])}"
        if len(node.values) == 1:
            return f"({out},)"
        return f"({out})"

    def _str_dice(self, node):
        return self._str_set(node)

    def _str_die(self, node):
        return str(node.total)


def d20_with_adv(adv):
    """Returns Xd20 for the correct advantage type."""
    if adv == d20.AdvType.NONE:
        return "1d20"
    elif adv == d20.AdvType.ADV:
        return "2d20kh1"
    elif adv == d20.AdvType.DIS:
        return "2d20kl1"
    elif adv == 2:
        return "3d20kh1"
    return "1d20"


def get_roll_comment(expr):
    """Gets the dice and comment from a roll expression."""
    result = d20.parse(expr, allow_comments=True)
    return str(result.roll), (result.comment or "")
