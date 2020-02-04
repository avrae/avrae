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
