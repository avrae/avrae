import abc
import collections

import d20

import aliasing.api.statblock
import gamedata
from cogs5e.models.sheet.statblock import StatBlock
from .errors import NoCounterFound


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

    @classmethod
    def from_data(cls, data):
        return cls(id=data['id'], type_id=data['typeId'])

    def to_dict(self):
        return {'id': self.id, 'typeId': self.type_id}

    def build_str(self, plural):
        charges = 'charges' if plural else 'charge'
        entity_name = self.entity.name if self.entity is not None else "Unknown Ability"
        return f"{charges} of {entity_name}"

    def __repr__(self):
        return f"<AbilityReference id={self.id!r} type_id={self.type_id!r} entity={self.entity!r}>"


def abilityreference_counter_discovery(ref, char):
    """
    Given an AbilityReference and a character, discover the most appropriate CC to use for the counter.

    Discovery types:

    1. limiteduse ID - the entity is the limited use object directly and we can look it up directly from live sync id
    2. source feature ID - the entity is a source feature and we found a cc that was imported by ddb, granted by that
       feature
    3. source feature name - we found a cc with the same name as that feature
    4. source feature granted lu name - there is a cc with the same name as a cc granted by that feature (e.g. Combat
       Superiority grants Superiority Dice)
    5. root feature - there is a cc granted by a feature that is a child of the same feature the given feature is a
       child of (ddb only)
    6. parent feature name - there is a cc with the same name as a feature that is a parent of given feature
    7. parent feature granted lu name - there is a cc with the same name as a limited use granted by a feature that
       is a parent of given feature

    :type ref: AbilityReference
    :type char: cogs5e.models.character.Character
    :rtype: cogs5e.models.sheet.player.CustomCounter
    :raises NoCounterFound: if no appropriate counter could be found
    """
    e = ref.entity

    if e is None:
        raise NoCounterFound("Invalid ability specified in AbilityReference!")
    if not (isinstance(e, gamedata.mixins.LimitedUseGrantorMixin) or isinstance(e, gamedata.LimitedUse)):
        raise NoCounterFound(f"{e.name} has no custom counter information.")

    # register mappings
    consumables_by_name = {}
    consumables_by_lu_id = {}
    consumables_by_feature_id = {}
    for cc in char.consumables:
        consumables_by_name[cc.name] = cc
        if char.sheet_type == 'beyond':
            if cc.live_id is not None:
                lu_id, _ = cc.live_id.split('-', 1)
                consumables_by_lu_id[int(lu_id)] = cc
            if (cc.ddb_source_feature_type and cc.ddb_source_feature_id) is not None:
                feat_id = (cc.ddb_source_feature_type, cc.ddb_source_feature_id)
                consumables_by_feature_id[feat_id] = cc

    eid = e.entity_id
    tid = e.type_id

    # 1: cc with same id (if the tid is the cc tid)
    if tid == gamedata.LimitedUse.type_id:
        if (limiteduse_cc := consumables_by_lu_id.get(eid)) is not None:
            return limiteduse_cc
        e = e.parent
        eid = e.entity_id
        tid = e.type_id

    # 2: cc with same source entity
    if (source_cc := consumables_by_feature_id.get((tid, eid))) is not None:
        return source_cc

    # 3: cc with same name as source entity
    if (source_name_cc := consumables_by_name.get(e.name)) is not None:
        return source_name_cc

    # 4: cc with same name as cc granted by source entity
    for granted_lu in e.limited_use:
        if (lu_name_cc := consumables_by_name.get(granted_lu.name)) is not None:
            return lu_name_cc

    # 5: cc with same root feature as source entity
    # also set up parent order while we're here
    root_feature = e
    parents = []
    while root_feature.parent:
        root_feature = root_feature.parent
        parents.append(root_feature)

    # find all ccs' root feature, and their depth (we want the shallowest)
    consumables_by_root = collections.defaultdict(lambda: [])
    for (source_tid, source_eid), cc in consumables_by_feature_id.items():
        cc_feature_root = gamedata.compendium.lookup_entity(source_tid, source_eid)
        if cc_feature_root is None:
            continue
        depth = 0
        while cc_feature_root.parent:
            depth += 1
            cc_feature_root = cc_feature_root.parent
        consumables_by_root[cc_feature_root].append((cc, depth))

    if consumables_by_root[root_feature]:
        root_feature_cc, depth = sorted(consumables_by_root[root_feature], key=lambda pair: pair[1])[0]
        return root_feature_cc

    # 6: cc with same name as any source entity parent, or 7: same name as any cc granted by source entity parent
    for parent_feature in parents:
        if (parent_name_cc := consumables_by_name.get(parent_feature.name)) is not None:
            return parent_name_cc

        for granted_lu in parent_feature.limited_use:
            if (parent_lu_name_cc := consumables_by_name.get(granted_lu.name)) is not None:
                return parent_lu_name_cc

    # error
    raise NoCounterFound(f"Could not find an appropriate counter for {e.name}.")
