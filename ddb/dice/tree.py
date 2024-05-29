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

import uuid

import d20

from .constants import DiceOperation, RollKind, RollType

SUPPORTED_DIE_SIZES = (4, 6, 8, 10, 12, 20, 100)


class RollRequest:
    def __init__(self, action, rolls, context=None, roll_id=None, set_id=None):
        """
        :type action: str
        :type rolls: list[RollRequestRoll]
        :type context: RollContext or None
        :type roll_id: str or None
        :type set_id: str or None
        """
        self.action = action
        self.rolls = rolls
        self.context = context
        self.roll_id = roll_id
        self.set_id = set_id

    @classmethod
    def from_dict(cls, d):
        rolls = [RollRequestRoll.from_dict(r) for r in d["rolls"]]
        if (context := d.get("context")) is not None:
            context = RollContext.from_dict(context)
        return cls(d["action"], rolls, context, d.get("rollId"), d.get("setId"))

    def to_dict(self):
        rolls = [rr.to_dict() for rr in self.rolls]
        context = self.context.to_dict() if self.context is not None else None
        return {"action": self.action, "rolls": rolls, "context": context, "rollId": self.roll_id, "setId": self.set_id}

    @classmethod
    def new(cls, rolls, context=None, action="custom", set_id="00102"):
        """
        Creates a new RollRequest.

        :type rolls: list[RollRequestRoll]
        :param RollContext context: The context this roll took place in.
        :param str action: The action that this is a roll for (name of attack, spell, check, or abbr of save).
        :param str set_id: The dice set ID the roll was made with (default basic black)
        """
        roll_id = str(uuid.uuid4())
        return cls(action, rolls, context, roll_id, set_id)


class RollContext:
    def __init__(self, entity_id: str = None, entity_type: str = None, name: str = None, avatar_url: str = None):
        self.entity_id = entity_id
        self.entity_type = entity_type
        self.name = name
        self.avatar_url = avatar_url

    @classmethod
    def from_dict(cls, d):
        return cls(d.get("entityId"), d.get("entityType"), d.get("name"), d.get("avatarUrl"))

    def to_dict(self):
        return {
            "entityId": self.entity_id,
            "entityType": self.entity_type,
            "name": self.name,
            "avatarUrl": self.avatar_url,
        }

    @classmethod
    def from_character(cls, character):
        """Returns a context associated with a DDB character."""
        return cls(character.upstream_id, "character", character.name, character.image)


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
        dice_notation = DiceNotation.from_dict(d["diceNotation"])
        roll_type = RollType(d["rollType"])
        roll_kind = RollKind(d["rollKind"])
        if (result := d.get("result")) is not None:
            result = RollResult.from_dict(result)
        return cls(dice_notation, roll_type, roll_kind, result)

    def to_dict(self):
        result = self.result.to_dict() if self.result is not None else None
        return {
            "diceNotation": self.dice_notation.to_dict(),
            "rollType": self.roll_type.value,
            "rollKind": self.roll_kind.value,
            "result": result,
        }

    @classmethod
    def from_d20(cls, result, roll_type=RollType.ROLL, roll_kind=RollKind.NONE):
        """
        Creates a satisfied RollRequestRoll from a d20 roll result.

        :type result: d20.RollResult
        :type roll_type: RollType
        :type roll_kind: RollKind
        """
        dice_notation = DiceNotation.from_d20(result)
        roll_result = RollResult.from_d20_and_dice_notation(result, dice_notation)
        return cls(dice_notation, roll_type, roll_kind, roll_result)

    def to_d20(self, stringifier=None, comment=None):
        """
        Returns a d20.RollResult representing this roll request.

        :param stringifier: The d20 stringifier to use to stringify the result.
        :type stringifier: d20.Stringifier
        :param comment: The comment to add to the resulting expression.
        :type comment: str or None
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
        return cls(d["values"], d["total"], d["constant"])

    def to_dict(self):
        return {"values": self.values, "total": self.total, "constant": self.constant}

    @classmethod
    def from_d20_and_dice_notation(cls, result: d20.RollResult, dice_notation):
        values = [die.die_value for dt in dice_notation.set for die in dt.dice]  # multi-loop drifting!!!
        return cls(values, result.total, dice_notation.constant)


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
        dice_set = [DieTerm.from_dict(dt) for dt in d["set"]]
        return cls(dice_set, d["constant"])

    def to_dict(self):
        dice_set = [dt.to_dict() for dt in self.set]
        return {"set": dice_set, "constant": self.constant}

    @classmethod
    def from_d20(cls, result: d20.RollResult):
        # DiceNotation only supports (XdY+)*(N)? so anything that doesn't fit that must be a constant
        dice_set = []
        constants = []

        def recurse(root: d20.Number):
            if isinstance(root, d20.Parenthetical):
                root = root.value
            # a leaf we care about will always be dice or literal (which falls thru)
            if isinstance(root, d20.Dice) and root.size in SUPPORTED_DIE_SIZES:
                dice_set.append(DieTerm.from_d20(root))
            # we only want to recurse on sets, positive unops, and positive binops
            elif isinstance(root, d20.Set):
                for term in root.keptset:
                    recurse(term)
            elif isinstance(root, d20.UnOp):
                if root.op == "+":
                    recurse(root.value)
                else:
                    constants.append(root.total)
            elif isinstance(root, d20.BinOp):
                if root.op == "+":
                    recurse(root.left)
                    recurse(root.right)
                elif root.op == "-":
                    constants.append(-root.right.total)
                    recurse(root.left)
                else:
                    constants.append(root.total)
            # otherwise it's unsupported and we leave it as a constant
            else:
                constants.append(root.total)

        recurse(result.expr.roll)

        return cls(dice_set, int(sum(constants)))

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
            root = module_base.BinOp(root, "+", dice)

        # step 3: combine with a constant with a BinOp (if there)
        if self.constant < 0:
            root = module_base.BinOp(root, "-", module_base.Literal(-self.constant))
        elif self.constant > 0:
            root = module_base.BinOp(root, "+", module_base.Literal(self.constant))

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
        dice = [Die.from_dict(die) for die in d["dice"]]
        operation = DiceOperation(d["operation"])
        return cls(d["count"], d["dieType"], dice, operation, d.get("operand"))

    def to_dict(self):
        dice = [die.to_dict() for die in self.dice]
        return {
            "count": self.count,
            "dieType": self.die_type,
            "dice": dice,
            "operation": self.operation.value,
            "operand": self.operand,
        }

    # noinspection PyUnboundLocalVariable, PyTypeChecker
    # not quite perfect for the walrus yet - op/sel are defined by the walrus
    @classmethod
    def from_d20(cls, dice: d20.Dice):
        # we only support one set of kh/kl, so if we have more ops than that we just return the simplest representation
        if (
            len(dice.operations) == 1
            and (op := dice.operations[0]).op == "k"
            and len(op.sels) == 1
            and (sel := op.sels[0]).cat in ("h", "l")
        ):
            the_dice = [Die.from_d20(d) for d in dice.values]
            dice_op = DiceOperation.MIN if sel.cat == "l" else DiceOperation.MAX
            return cls(dice.num, f"d{dice.size}", the_dice, dice_op, sel.num)
        else:
            the_dice = [Die.from_d20(d) for d in dice.keptset]
            return cls(dice.num, f"d{dice.size}", the_dice, DiceOperation.SUM)

    @property
    def size(self):
        return int(self.die_type.strip("d"))

    def d20_ast(self):
        """
        :rtype: d20.ast.Dice or d20.ast.OperatedDice
        """
        dice = d20.ast.Dice(self.count, self.size)
        if self.operation == DiceOperation.SUM:
            return dice
        elif self.operation == DiceOperation.MIN:
            klX = d20.ast.SetOperator("k", [d20.ast.SetSelector("l", self.operand)])
            return d20.ast.OperatedDice(dice, klX)
        else:  # DiceOperation.MAX
            khX = d20.ast.SetOperator("k", [d20.ast.SetSelector("h", self.operand)])
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
            op = d20.SetOperator("k", [d20.SetSelector("l", self.operand)])
            op.operate(inst)
            inst.operations.append(op)
        elif self.operation == DiceOperation.MAX:
            op = d20.SetOperator("k", [d20.SetSelector("h", self.operand)])
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
        return cls(d["dieType"], d["dieValue"])

    def to_dict(self):
        return {"dieType": self.die_type, "dieValue": self.die_value}

    @classmethod
    def from_d20(cls, die: d20.Die):
        return cls(f"d{die.size}", die.number)

    @property
    def size(self):
        return int(self.die_type.strip("d"))

    def d20_expr(self):
        """
        :rtype: d20.Die
        """
        return d20.Die(self.size, values=[d20.Literal(self.die_value)])
