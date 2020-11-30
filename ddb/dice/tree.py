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

from .constants import DiceOperation, RollKind, RollType


class RollRequest:
    def __init__(self, action, rolls, context=None, roll_id=None):
        """
        :type action: str
        :type rolls: list[RollRequestRoll]
        :type context: RollContext
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
