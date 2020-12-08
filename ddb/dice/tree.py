"""
Classes representing the roll result tree as defined in the following form:

RollRequest
https://github.com/DnDBeyond/ddb-integrated-dice/blob/master/packages/ddb-dice/src/utils/RollRequest.ts
    - RollContext
    - RollRequestRoll
    https://github.com/DnDBeyond/ddb-integrated-dice/blob/master/packages/ddb-dice/src/utils/RollRequestRoll.ts
        - DiceNotation
        https://github.com/DnDBeyond/ddb-integrated-dice/blob/master/packages/ddb-dice/src/utils/DiceNotation.ts
            - DieTerm
            https://github.com/DnDBeyond/ddb-integrated-dice/blob/master/packages/ddb-dice/src/utils/DieTerm.ts
                - DiceOperation
                - Die
                https://github.com/DnDBeyond/ddb-integrated-dice/blob/master/packages/ddb-dice/src/dice/Die.ts
        - RollResult
        https://github.com/DnDBeyond/ddb-integrated-dice/blob/master/packages/ddb-dice/src/utils/RollResult.ts
        - RollType
        - RollKind
"""
import d20

from .constants import DiceOperation, RollKind, RollType


class RollRequest:
    def __init__(self, action, rolls, context=None, roll_id=None):
        """
        :type action: str
        :type rolls: list[RollRequestRoll]
        :type context: RollContext or None
        :type roll_id: str or None
        """
        self.action = action
        self.rolls = rolls
        self.context = context
        self.roll_id = roll_id

    @classmethod
    def from_dict(cls, d):
        rolls = [RollRequestRoll.from_dict(r) for r in d['rolls']]
        if (context := d.get('context')) is not None:
            context = RollContext.from_dict(context)
        return cls(d['action'], rolls, context, d.get('rollId'))


class RollContext:
    def __init__(self, entity_id=None, entity_type=None):
        self.entity_id = entity_id
        self.entity_type = entity_type

    @classmethod
    def from_dict(cls, d):
        return cls(d.get('entityId'), d.get('entityType'))


class RollRequestRoll:
    def __init__(self, dice_notation, roll_type, roll_kind, result=None):
        """
        :type dice_notation: DiceNotation
        :type roll_type: RollType
        :type roll_kind: RollKind
        :type result: RollResult or None
        """
        self.dice_notation = dice_notation
        self.roll_type = roll_type
        self.roll_kind = roll_kind
        self.result = result

    @classmethod
    def from_dict(cls, d):
        dice_notation = DiceNotation.from_dict(d['diceNotation'])
        roll_type = RollType(d['rollType'])
        roll_kind = RollKind(d['rollKind'])
        if (result := d.get('result')) is not None:
            result = RollResult.from_dict(result)
        return cls(dice_notation, roll_type, roll_kind, result)

    def to_d20(self, stringifier=None, comment=None):
        """
        Returns a d20.RollResult representing this roll request.

        :param stringifier: The d20 stringifier to use to stringify the result.
        :type stringifier: d20.Stringifier
        :param str comment: The comment to add to the resulting expression.
        :rtype: d20.RollResult
        """
        if stringifier is None:
            stringifier = d20.MarkdownStringifier()
        ast = self.dice_notation.d20_ast(comment=comment)
        result = self.dice_notation.d20_expr(comment=comment)
        return d20.RollResult(ast, result, stringifier)


class RollResult:
    def __init__(self, values, total, constant):
        """
        :type values: list[int]
        :type total: int
        :type constant: int
        """
        self.values = values
        self.total = total
        self.constant = constant

    @classmethod
    def from_dict(cls, d):
        return cls(d['values'], d['total'], d['constant'])


class DiceNotation:
    def __init__(self, dice_set, constant):
        """
        :type dice_set: list[DieTerm]
        :type constant: int
        """
        self.set = dice_set
        self.constant = constant

    @classmethod
    def from_dict(cls, d):
        dice_set = [DieTerm.from_dict(dt) for dt in d['set']]
        return cls(dice_set, d['constant'])

    def d20_ast(self, **kwargs):
        """
        :return: The d20 AST representing the dice rolled in this roll.
        :rtype: d20.ast.Expression
        """
        return self._build_tree(module_base=d20.ast, child_method=lambda dt: dt.d20_ast, **kwargs)

    def d20_expr(self, **kwargs):
        """
        :return: The d20 expression representing the results of this roll.
        :rtype: d20.Expression
        """
        return self._build_tree(module_base=d20, child_method=lambda dt: dt.d20_expr, **kwargs)

    def _build_tree(self, module_base, child_method, comment=None):
        """
        Base method for building an ast or expression tree.

        :param module_base: The module to get tree node classes from. (AST or Expression)
        :param child_method: A callable that returns a method of DieTerm to generate tree nodes for children.
        :param str comment: A comment to add to the resulting expression.
        """
        # if no dice were rolled, just return the literal
        if not self.set:
            return module_base.Expression(module_base.Literal(self.constant), comment=comment)

        # step 1: generate Dice for each roll in the set
        set_dice = [child_method(dt)() for dt in self.set]

        # step 2: combine them with BinOps
        root, *rest = set_dice
        for dice in rest:
            root = module_base.BinOp(root, '+', dice)

        # step 3: combine with a constant with a BinOp (if there)
        if self.constant < 0:
            root = module_base.BinOp(root, '-', module_base.Literal(-self.constant))
        elif self.constant > 0:
            root = module_base.BinOp(root, '+', module_base.Literal(self.constant))

        # done
        return module_base.Expression(root, comment=comment)


class DieTerm:
    def __init__(self, count, die_type, dice, operation, operand=None):
        """
        :type count: int
        :type die_type: str
        :type dice: list[Die]
        :type operation: DiceOperation
        :type operand: int
        """
        self.count = count
        self.die_type = die_type
        self.dice = dice
        self.operation = operation
        self.operand = operand

    @classmethod
    def from_dict(cls, d):
        dice = [Die.from_dict(die) for die in d['dice']]
        operation = DiceOperation(d['operation'])
        return cls(d['count'], d['dieType'], dice, operation, d.get('operand'))

    @property
    def size(self):
        return int(self.die_type.strip('d'))

    def d20_ast(self):
        """
        :rtype: d20.ast.Dice or d20.ast.OperatedDice
        """
        dice = d20.ast.Dice(self.count, self.size)
        if self.operation == DiceOperation.SUM:
            return dice
        elif self.operation == DiceOperation.MIN:
            klX = d20.ast.SetOperator('k', [d20.ast.SetSelector('l', self.operand)])
            return d20.ast.OperatedDice(dice, klX)
        else:  # DiceOperation.MAX
            khX = d20.ast.SetOperator('k', [d20.ast.SetSelector('h', self.operand)])
            return d20.ast.OperatedDice(dice, khX)

    def d20_expr(self):
        """
        :rtype: d20.Dice
        """
        # create expression for each individual Die
        the_dice = [die.d20_expr() for die in self.dice]
        inst = d20.Dice(num=self.count, size=self.size, values=the_dice)

        # setup operations
        if self.operation == DiceOperation.MIN:
            op = d20.SetOperator('k', [d20.SetSelector('l', self.operand)])
            op.operate(inst)
            inst.operations.append(op)
        elif self.operation == DiceOperation.MAX:
            op = d20.SetOperator('k', [d20.SetSelector('h', self.operand)])
            op.operate(inst)
            inst.operations.append(op)

        return inst


class Die:
    def __init__(self, die_type, die_value):
        """
        :type die_type: str
        :type die_value: int
        """
        self.die_type = die_type
        self.die_value = die_value

    @classmethod
    def from_dict(cls, d):
        return cls(d['dieType'], d['dieValue'])

    @property
    def size(self):
        return int(self.die_type.strip('d'))

    def d20_expr(self):
        """
        :rtype: d20.Die
        """
        return d20.Die(self.size, values=[d20.Literal(self.die_value)])
