import abc
import collections

import gamedata
from . import Effect
from ..errors import AutomationException, NoCounterFound, StopExecution
from ..results import UseCounterResult
from ..utils import stringify_intexpr


class UseCounter(Effect):
    def __init__(
        self,
        counter,
        amount: str,
        allowOverflow: bool = False,
        errorBehaviour: str = "warn",
        fixedValue: bool = None,
        **kwargs,
    ):
        """
        :type counter: str or SpellSlotReference or AbilityReference
        """
        super().__init__("counter", **kwargs)
        self.counter = counter
        self.amount = amount
        self.allow_overflow = allowOverflow
        self.error_behaviour = errorBehaviour
        self.fixedValue = fixedValue

    @classmethod
    def from_data(cls, data):
        if not isinstance(data["counter"], str):
            data["counter"] = deserialize_usecounter_target(data["counter"])
        return super().from_data(data)

    def to_dict(self):
        out = super().to_dict()
        counter = self.counter if isinstance(self.counter, str) else self.counter.to_dict()
        out.update({
            "counter": counter,
            "amount": self.amount,
            "allowOverflow": self.allow_overflow,
            "errorBehaviour": self.error_behaviour,
        })
        if self.fixedValue is not None:
            out["fixedValue"] = self.fixedValue
        return out

    def run(self, autoctx):
        super().run(autoctx)

        # set to default values in case of error
        autoctx.metavars["lastCounterName"] = None
        autoctx.metavars["lastCounterRemaining"] = 0
        autoctx.metavars["lastCounterUsedAmount"] = 0
        autoctx.metavars["lastCounterRequestedAmount"] = 0  # 1491

        # handle -amt, -l, -i
        amt = autoctx.args.last("amt", None, int, ephem=True)
        ignore = autoctx.args.last("i")
        # -l, nopact handled in use_spell_slot

        try:
            if self.fixedValue:
                amt = None
            amount = amt or autoctx.parse_intexpression(self.amount)
        except Exception:
            raise AutomationException(f"{self.amount!r} cannot be interpreted as an amount (in Use Counter)")

        autoctx.metavars["lastCounterRequestedAmount"] = amount  # 1491

        try:
            if isinstance(self.counter, SpellSlotReference):  # spell slot
                result = self.use_spell_slot(autoctx, amount, ignore)
            else:
                result = self.get_and_use_counter(autoctx, amount, ignore)
        except Exception as e:
            result = UseCounterResult(skipped=True, requested_amount=amount)
            if self.error_behaviour == "warn":
                autoctx.meta_queue(f"**Warning**: Could not use counter - {e}")
            elif self.error_behaviour == "raise":
                raise StopExecution(f"Could not use counter: {e}") from e

        autoctx.metavars["lastCounterName"] = result.counter_name
        autoctx.metavars["lastCounterRemaining"] = result.counter_remaining
        autoctx.metavars["lastCounterUsedAmount"] = result.used_amount
        return result

    def get_and_use_counter(self, autoctx, amount, ignore_resources: bool = False):
        if ignore_resources:  # handled here to return counter name (#1582)
            if isinstance(self.counter, AbilityReference):
                name = self.counter.entity.name if self.counter.entity is not None else "Unknown Ability"
            else:
                name = self.counter
            return UseCounterResult(counter_name=name, requested_amount=amount, skipped=True)

        if autoctx.character is None:
            raise NoCounterFound("The caster does not have custom counters.")

        if isinstance(self.counter, AbilityReference):
            counter = abilityreference_counter_discovery(self.counter, autoctx.character)
        else:  # str - get counter by match
            counter = autoctx.character.get_consumable(self.counter)
            if counter is None:
                raise NoCounterFound(f"No counter with the name {self.counter!r} was found.")

        return self.use_custom_counter(autoctx, counter, amount)

    def use_spell_slot(self, autoctx, amount, ignore_resources: bool = False):
        spellref_level = autoctx.parse_intexpression(self.counter.slot)
        level = autoctx.args.last("l", spellref_level, int)
        nopact = autoctx.args.last("nopact")
        if ignore_resources:  # handled here to return counter name (#1582)
            return UseCounterResult(counter_name=str(level), requested_amount=amount, skipped=True)

        autoctx.caster_needs_commit = True
        old_value = autoctx.caster.spellbook.get_slots(level)
        target_value = new_value = old_value - amount

        # if allow overflow is on, clip to bounds
        if self.allow_overflow:
            new_value = max(min(target_value, autoctx.caster.spellbook.get_max_slots(level)), 0)

        # use the slot(s) and output
        autoctx.caster.spellbook.set_slots(level, new_value, pact=not nopact)
        delta = new_value - old_value
        overflow = abs(new_value - target_value)
        slots_str = autoctx.caster.spellbook.slots_str(level)

        # update the runtime to set the level
        autoctx.spell_level_override = level

        # queue resource usage in own field
        delta_str = f"({delta:+})" if delta else ""
        overflow_str = f"\n({overflow} overflow)" if overflow else ""
        autoctx.postflight_queue_field(name="Spell Slots", value=f"{slots_str} {delta_str}{overflow_str}")

        return UseCounterResult(
            counter_name=str(level),
            counter_remaining=new_value,
            used_amount=old_value - new_value,
            requested_amount=amount,
        )

    def use_custom_counter(self, autoctx, counter, amount):
        autoctx.caster_needs_commit = True
        old_value = counter.value
        target_value = old_value - amount

        # use the charges and output
        final_value = counter.set(target_value, strict=not self.allow_overflow)
        delta = final_value - old_value
        overflow = abs(final_value - target_value)

        # queue resource usage in own field
        delta_str = f"({delta:+})" if delta else ""
        overflow_str = f"\n({overflow} overflow)" if overflow else ""
        autoctx.postflight_queue_field(name=counter.name, value=f"{str(counter)} {delta_str}{overflow_str}")

        return UseCounterResult(
            counter_name=counter.name, counter_remaining=final_value, used_amount=-delta, requested_amount=amount
        )

    def build_str(self, caster, evaluator):
        super().build_str(caster, evaluator)
        # amount
        amount = stringify_intexpr(evaluator, self.amount)

        # guaranteed metavars
        evaluator.builtins["lastCounterName"] = str(self.counter)
        evaluator.builtins["lastCounterRequestedAmount"] = amount
        evaluator.builtins["lastCounterUsedAmount"] = amount

        # counter name
        plural = abs(amount) != 1
        if isinstance(self.counter, str):
            charges = "charges" if plural else "charge"
            counter_name = f"{charges} of {self.counter}"
        else:
            counter_name = self.counter.build_str(caster, evaluator, plural=plural)

        # uses/restores
        if amount < 0:
            return f"restores {-amount} {counter_name}"
        else:
            return f"uses {amount} {counter_name}"


# ==== helpers ====
def deserialize_usecounter_target(target):
    """
    :rtype: SpellSlotReference or AbilityReference
    """
    if isinstance(target, str):
        return target
    elif "slot" in target:
        return SpellSlotReference.from_data(target)
    elif "id" in target:
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

    def build_str(self, caster, evaluator, plural):
        raise NotImplementedError

    def __repr__(self):
        raise NotImplementedError


class SpellSlotReference(_UseCounterTarget):
    def __init__(self, slot, **kwargs):
        super().__init__(**kwargs)
        self.slot = slot

    def to_dict(self):
        return {"slot": self.slot}

    def build_str(self, caster, evaluator, plural):
        level = stringify_intexpr(evaluator, self.slot)
        slots = "slots" if plural else "slot"
        return f"level {level} spell {slots}"

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
        return cls(id=data["id"], type_id=data["typeId"])

    def to_dict(self):
        return {"id": self.id, "typeId": self.type_id}

    def build_str(self, caster, evaluator, plural):
        charges = "charges" if plural else "charge"
        entity_name = self.entity.name if self.entity is not None else "Unknown Ability"
        return f"{charges} of {entity_name}"

    def __str__(self):
        return self.entity.name if self.entity is not None else "Unknown Ability"

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
        if char.sheet_type == "beyond":
            if cc.live_id is not None:
                try:
                    lu_id, lu_tid = cc.live_id.split("-", 1)
                    consumables_by_lu_id[int(lu_tid), int(lu_id)] = cc
                except ValueError:
                    pass
            if (cc.ddb_source_feature_type and cc.ddb_source_feature_id) is not None:
                feat_id = (cc.ddb_source_feature_type, cc.ddb_source_feature_id)
                consumables_by_feature_id[feat_id] = cc

    eid = e.entity_id
    tid = e.type_id

    # if we are referencing a LimitedUse directly:
    if isinstance(e, gamedata.LimitedUse):
        # 1: cc with same id
        if (limiteduse_cc := consumables_by_lu_id.get((tid, eid))) is not None:
            return limiteduse_cc

        # 1.5: cc with same name as the LimitedUse
        if (limiteduse_name_cc := consumables_by_name.get(e.name)) is not None:
            return limiteduse_name_cc

        # otherwise fall back to the granting feature
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
