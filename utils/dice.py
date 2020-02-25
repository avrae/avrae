import re

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


def _resist_tokenize(res_str):
    """Extracts a set of tokens from a string (any consecutive chain of letters)."""
    return set(m.group(0) for m in re.finditer(r'\w+', res_str))


def do_resistances(damage_expr, resistances, immunities, vulnerabilities, neutrals):
    """
    Modifies a dice expression in place, inserting binary operations where necessary to handle resistances to given
    damage types.

    :type damage_expr: d20.Expression
    :type resistances: list of cogs5e.models.sheet.resistance.Resistance
    :type immunities: list of cogs5e.models.sheet.resistance.Resistance
    :type vulnerabilities: list of cogs5e.models.sheet.resistance.Resistance
    :param neutrals: A list of resistances that should be explicitly ignored.
    :type neutrals: list of cogs5e.models.sheet.resistance.Resistance
    """

    # simplify damage types
    d20.utils.simplify_expr_annotations(damage_expr.roll, ambig_inherit='left')

    # depth first visit expression nodes: if it has an annotation, add the appropriate binops and move to the next
    def do_visit(node):
        if node.annotation:
            original_annotation = node.annotation
            ann = _resist_tokenize(node.annotation.lower())

            if any(n.applies_to(ann) for n in neutrals):  # neutral overrides all
                return node

            if any(v.applies_to(ann) for v in vulnerabilities):
                node = d20.BinOp(d20.Parenthetical(node), '*', d20.Literal(2))

            if original_annotation.startswith('[^') or original_annotation.endswith('^]'):
                # break here - don't handle resist/immune
                return node

            if any(r.applies_to(ann) for r in resistances):
                node = d20.BinOp(d20.Parenthetical(node), '/', d20.Literal(2))

            if any(im.applies_to(ann) for im in immunities):
                node = d20.BinOp(d20.Parenthetical(node), '*', d20.Literal(0))

            return node

        for i, child in enumerate(node.children):
            replacement = do_visit(child)
            if replacement and replacement is not child:
                node.set_child(i, replacement)
        return None

    do_visit(damage_expr)


if __name__ == '__main__':
    from cogs5e.models.sheet.resistance import Resistance
    import traceback

    while True:
        try:
            result = d20.roll(input())
            print(str(result))
            do_resistances(result.expr,
                           resistances=[Resistance('resist', ['magical']), Resistance('both')],
                           immunities=[Resistance('immune'), Resistance('this', only=['magical'])],
                           vulnerabilities=[Resistance('vuln'), Resistance('both')],
                           neutrals=[Resistance('neutral')])
            print(d20.MarkdownStringifier().stringify(result.expr))
        except Exception as e:
            traceback.print_exc()
