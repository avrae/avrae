import d20


class VerboseMDStringifier(d20.MarkdownStringifier):
    def _str_expression(self, node):
        return f"**{node.comment or 'Result'}**: {self._stringify(node.roll)}\n" \
               f"**Total:** {int(node.total)}"


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
    """Gets the comment from a roll expression."""
    result = d20.parse(expr)
    return result.comment or ''


def do_resistances(damage_expr, resistances, immunities, vulnerabilities, neutrals):
    """
    Modifies a dice expression in place, inserting binary operations where necessary to handle resistances to given
    damage types.

    :type damage_expr: d20.Expression
    :type resistances: list of str
    :type immunities: list of str
    :type vulnerabilities: list of str
    :type neutrals: list of str
    """

    # clean resists and whatnot
    resistances = {r for r in resistances if r}
    immunities = {r for r in immunities if r}
    vulnerabilities = {r for r in vulnerabilities if r}
    neutrals = {r for r in neutrals if r}

    # simplify damage types
    d20.utils.simplify_expr_annotations(damage_expr.roll, ambig_inherit='left')

    # depth first visit expression nodes: if it has an annotation, add the appropriate binops and move to the next
    def do_visit(node):
        if node.annotation:
            ann = node.annotation.lower()
            if any(n.lower() in ann for n in neutrals):  # neutral overrides all
                return node

            if any(v.lower() in ann for v in vulnerabilities):
                node = d20.BinOp(d20.Parenthetical(node), '*', d20.Literal(2))

            if ann.startswith('^') or ann.endswith('^'):  # break here - don't handle resist/immune
                return node

            if any(r.lower() in ann for r in resistances):
                node = d20.BinOp(d20.Parenthetical(node), '/', d20.Literal(2))

            if any(im.lower() in ann for im in immunities):
                node = d20.BinOp(d20.Parenthetical(node), '*', d20.Literal(0))

            return node

        for i, child in enumerate(node.children):
            replacement = do_visit(child)
            if replacement and replacement is not child:
                node.set_child(i, replacement)
        return None

    do_visit(damage_expr)
