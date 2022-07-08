from typing import Any, List, TYPE_CHECKING, Tuple, Union

from . import Effect
from .. import results, utils
from ..errors import TargetException
from ..runtime import AutomationTarget

_TargetT = Any

if TYPE_CHECKING:
    from cogs5e.models.sheet.statblock import StatBlock

    _TargetT = Union[StatBlock, str, None]


class Target(Effect):
    def __init__(self, target, effects: list, sortBy=None, **kwargs):
        super().__init__("target", **kwargs)
        self.target = target
        self.effects = effects
        self.sort_by = sortBy

    @classmethod
    def from_data(cls, data):
        data["effects"] = Effect.deserialize(data["effects"])
        return super().from_data(data)

    def to_dict(self):
        out = super().to_dict()
        effects = [e.to_dict() for e in self.effects]
        out.update({"type": "target", "target": self.target, "effects": effects})
        if self.sort_by:
            out["sortBy"] = self.sort_by
        return out

    def run(self, autoctx):
        super().run(autoctx)

        # WEB-038 (.io #121) - this will semantically work correctly, but will make the display really weird
        previous_target = autoctx.target
        targets = autoctx.targets

        match self.target:
            case "all" | "each":
                iteration_results = self.run_all_target(autoctx, targets)
            case "self":
                iteration_results = self.run_self_target(autoctx)
            case "parent":
                iteration_results = self.run_parent_target(autoctx)
            case "children":
                iteration_results = self.run_children_target(autoctx)
            case int(idx1):
                iteration_results = self.run_indexed_target(autoctx, targets, idx1 - 1)
            case _:
                raise TargetException(f"Invalid target supplied: {self.target!r}")

        # in case we had no valid targets, we should still run everything once against no target to display Meta
        if not iteration_results:
            iteration_results = self.run_effects(autoctx, target=None)

        # restore the previous target
        autoctx.target = previous_target
        autoctx.metavars["target"] = utils.maybe_alias_statblock(previous_target)  # #1335

        return results.TargetResult(iteration_results)

    # ==== target type impls ====
    def run_self_target(self, autoctx) -> list[results.TargetIteration]:
        return self.run_effects(autoctx, target=autoctx.caster)

    # --- action target types ---
    def run_all_target(self, autoctx, targets) -> list[results.TargetIteration]:
        if autoctx.ieffect is not None and autoctx.from_button:
            raise TargetException("You can only use the `self`, `parent`, or `children` target on an IEffect button.")

        result_pairs = []
        for idx, (original_idx, target) in enumerate(self.sorted_targets(targets)):
            result_pairs.extend(self.run_effects(autoctx, target, idx, original_idx))

        return result_pairs

    def run_indexed_target(self, autoctx, targets, idx) -> list[results.TargetIteration]:
        if autoctx.ieffect is not None and autoctx.from_button:
            raise TargetException("You can only use the `self`, `parent`, or `children` target on an IEffect button.")

        sorted_targets = self.sorted_targets(targets)
        try:
            original_idx, target = sorted_targets[idx]
        except IndexError:
            return []

        return self.run_effects(autoctx, target, 0, original_idx)

    # --- button target types ---
    def run_parent_target(self, autoctx) -> list[results.TargetIteration]:
        if autoctx.ieffect is None:
            raise TargetException("You can only use the `self`, `each`, or numbered targets on an action.")

        parent_effect = autoctx.ieffect.get_parent_effect()
        if parent_effect is None:
            return []
        target = parent_effect.combatant
        if target is None:
            return []

        return self.run_effects(autoctx, target)

    def run_children_target(self, autoctx) -> list[results.TargetIteration]:
        if autoctx.ieffect is None:
            raise TargetException("You can only use the `self`, `each`, or numbered targets on an action.")

        # build target list
        targets = []
        for idx, child_effect in enumerate(autoctx.ieffect.get_children_effects()):
            # build list from children of children if child is a stacking
            if child_effect.stack:
                for idx, subchild_effect in enumerate(child_effect.get_children_effects()):
                    target = subchild_effect.combatant
                    if target is None:
                        continue
                    if target not in targets:
                        targets.append(target)
            else:
                target = child_effect.combatant
                if target is None:
                    continue
                if target not in targets:
                    targets.append(target)

        result_pairs = []

        for idx, (original_idx, target) in enumerate(self.sorted_targets(targets)):
            result_pairs.extend(self.run_effects(autoctx, target, idx, original_idx))
        return result_pairs

    # ==== helpers ====
    def sorted_targets(self, targets) -> List[Tuple[int, _TargetT]]:
        """
        Given a list of targets, returns a list of pairs representing the sorted targets and their original index
        in the input list (for result building later).
        """
        if self.sort_by == "hp_asc":
            return sorted(enumerate(targets), key=lambda pair: utils.target_hp_or_default(pair[1], float("inf")))
        elif self.sort_by == "hp_desc":
            return sorted(
                enumerate(targets), key=lambda pair: utils.target_hp_or_default(pair[1], float("-inf")), reverse=True
            )
        return list(enumerate(targets))

    def run_effects(self, autoctx, target, target_index=0, original_target_index=None) -> list[results.TargetIteration]:
        # set up autoctx and metavars
        autoctx.target = AutomationTarget(autoctx, target)
        autoctx.metavars["target"] = utils.maybe_alias_statblock(target)  # #1335
        autoctx.metavars["targetIndex"] = target_index  # #1711
        autoctx.metavars["targetNumber"] = target_index + 1

        # args
        args = autoctx.args
        args.set_context(autoctx.target.target)
        rr = min(args.last("rr", 1, int), 25)

        in_target = autoctx.target.target is not None
        iteration_results = []

        # #1335
        autoctx.metavars["targetIteration"] = 1

        # 2 binary attributes: (rr?, target?)
        # each case must end with a push_embed_field()
        if rr > 1:
            total_damage = 0
            for iteration in range(rr):
                if len(self.effects) == 1:
                    iter_title = f"{type(self.effects[0]).__name__} {iteration + 1}"
                else:
                    iter_title = f"Iteration {iteration + 1}"

                # #1335
                autoctx.metavars["targetIteration"] = iteration + 1

                # target, rr
                if in_target:
                    autoctx.queue(f"\n**__{iter_title}__**")

                child_results = self.run_children(self.effects, autoctx)
                total_damage += sum(r.get_damage() for r in child_results)
                iteration_results.append(
                    results.TargetIteration(
                        target_type=self.target,
                        is_simple=autoctx.target.is_simple,
                        target_id=autoctx.target.combatant and autoctx.target.combatant.id,
                        target_index=original_target_index,
                        target_iteration=iteration + 1,
                        results=child_results,
                    )
                )

                # no target, rr
                if not in_target:
                    autoctx.push_embed_field(iter_title)

            if in_target:  # target, rr
                if total_damage:
                    autoctx.queue(f"\n**__Total Damage__**: {total_damage}")

                autoctx.push_embed_field(autoctx.target.name)
            else:  # no target, rr
                if total_damage:
                    autoctx.queue(f"{total_damage}")
                    autoctx.push_embed_field("Total Damage", inline=True)
        else:
            child_results = self.run_children(self.effects, autoctx)
            iteration_results.append(
                results.TargetIteration(
                    target_type=self.target,
                    is_simple=autoctx.target.is_simple,
                    target_id=autoctx.target.combatant and autoctx.target.combatant.id,
                    target_index=original_target_index,
                    target_iteration=1,
                    results=child_results,
                )
            )
            if in_target:  # target, no rr
                autoctx.push_embed_field(autoctx.target.name)
            else:  # no target, no rr
                autoctx.push_embed_field(None, to_meta=True)

        return iteration_results

    def build_str(self, caster, evaluator):
        super().build_str(caster, evaluator)
        return self.build_child_str(self.effects, caster, evaluator)

    @property
    def children(self):
        return super().children + self.effects
