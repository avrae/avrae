import d20


class VerboseMDStringifier(d20.MarkdownStringifier):
    def _str_expression(self, node):
        return f"**{node.comment or 'Result'}**: {self._stringify(node.roll)}\n" \
               f"**Total:** {int(node.total)}"


class PersistentRollContext(d20.RollContext):
    """
    A roll context that does not reset between rolls.
    """

    def reset(self):
        pass


class ContextPersistingRoller(d20.Roller):
    def __init__(self):
        super().__init__()
        self.context = PersistentRollContext()


def d20_with_adv(adv):
    if adv == d20.AdvType.NONE:
        return "1d20"
    elif adv == d20.AdvType.ADV:
        return "2d20kh1"
    elif adv == d20.AdvType.DIS:
        return "2d20kl1"
    elif adv == 2:  # todo d20 support for elven advantage
        return "3d20kh1"
    return "1d20"
