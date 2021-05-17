import abc

import d20

import aliasing.api.statblock
import gamedata
from cogs5e.models.sheet.statblock import StatBlock


def maybe_alias_statblock(target):
    """Returns the AliasStatBlock for the target if applicable."""
    if not isinstance(target, (StatBlock, str, type(None))):
        raise ValueError("target must be a statblock, str, or None")
    return aliasing.api.statblock.AliasStatBlock(target) if isinstance(target, StatBlock) else target


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

        if effect.higher and not autoctx.get_cast_level() == autoctx.spell.level:
            higher = effect.higher.get(str(autoctx.get_cast_level()))
            if higher:
                higher_ast = d20.parse(higher)
                dice_ast.roll = d20.ast.BinOp(dice_ast.roll, '+', higher_ast.roll)

    return dice_ast


def mi_mapper(minimum):
    """Returns a function that maps Dice AST objects to OperatedDice with miX attached."""

    def mapper(node):
        if isinstance(node, d20.ast.Dice):
            miX = d20.ast.SetOperator('mi', [d20.ast.SetSelector(None, int(minimum))])
            return d20.ast.OperatedDice(node, miX)
        return node

    return mapper


def max_mapper(node):
    """A function that maps Dice AST objects to OperatedDice that set their values to their maximum."""
    if isinstance(node, d20.ast.Dice):
        miX = d20.ast.SetOperator('mi', [d20.ast.SetSelector(None, node.size)])
        return d20.ast.OperatedDice(node, miX)
    return node


def crit_mapper(node):
    """A function that doubles the number of dice for each Dice AST node."""
    if isinstance(node, d20.ast.Dice):
        return d20.ast.Dice(node.num * 2, node.size)
    return node


# ---- use counter stuff ----
def deserialize_usecounter_target(target):
    """
    :rtype: SpellSlotReference or AbilityReference
    """
    if isinstance(target, str):
        return target
    elif 'slot' in target:
        return SpellSlotReference.from_data(target)
    elif 'id' in target:
        return AbilityReference.from_data(target)
    raise ValueError(f"Unknown usecounter target: {target!r}")


class _UseCounterTarget(abc.ABC):  # this is just here for type niceness because python doesn't have interfaces <.<
    def __init__(self, **kwargs):
        pass

    @classmethod
    def from_data(cls, data):
        return cls(**data)

    def to_dict(self):
        raise NotImplementedError

    def build_str(self, plural):
        raise NotImplementedError

    def __repr__(self):
        raise NotImplementedError


class SpellSlotReference(_UseCounterTarget):
    def __init__(self, slot: int, **kwargs):
        super().__init__(**kwargs)
        self.slot = slot

    def to_dict(self):
        return {'slot': self.slot}

    def build_str(self, plural):
        slots = 'slots' if plural else 'slot'
        return f"level {self.slot} spell {slots}"

    def __str__(self):
        return str(self.slot)

    def __repr__(self):
        return f"<SpellSlotReference slot={self.slot!r}>"


class AbilityReference(_UseCounterTarget):
    def __init__(self, id: int, type_id: int, **kwargs):
        super().__init__(**kwargs)
        self.id = id
        self.type_id = type_id

    @property
    def entity(self):
        return gamedata.compendium.lookup_entity(self.type_id, self.id)

    def to_dict(self):
        return {'id': self.id, 'type_id': self.type_id}

    def build_str(self, plural):
        charges = 'charges' if plural else 'charge'
        entity_name = self.entity.name if self.entity is not None else "Unknown Ability"
        return f"{charges} of {entity_name}"

    def __repr__(self):
        return f"<AbilityReference id={self.id!r} type_id={self.type_id!r} entity={self.entity!r}>"
