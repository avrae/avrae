from . import Effect
from .. import utils
from ..errors import TargetException
from ..results import TargetResult
from ..runtime import AutomationTarget


class Target(Effect):
    def __init__(self, target, effects: list, sortBy=None, **kwargs):
        super().__init__("target", **kwargs)
        self.target = target
        self.effects = effects
        self.sort_by = sortBy

    @classmethod
    def from_data(cls, data):
        data["effects"] = Effect.deserialize(data["effects"])
        return super(Target, cls).from_data(data)

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
                result_pairs = self.run_all_target(autoctx, targets)
            case "self":
                result_pairs = self.run_self_target(autoctx)
            case "parent":
                result_pairs = self.run_parent_target(autoctx)
            case "children":
                result_pairs = self.run_children_target(autoctx)
            case int(idx1):
                result_pairs = self.run_indexed_target(autoctx, targets, idx1 - 1)
            case _:
                raise TargetException(f"Invalid target supplied: {self.target!r}")

        # in case we had no valid targets, we should still run everything once against no target to display Meta
        if not result_pairs:
            result_pairs = self.run_one_target(autoctx, target=None, target_index=0)

        # restore the previous target
        autoctx.target = previous_target
        autoctx.metavars["target"] = utils.maybe_alias_statblock(previous_target)  # #1335

        final_targets, results = zip(*result_pairs)  # convenient unzipping :D
        return TargetResult(final_targets, results)

    # ==== target type impls ====
    def run_self_target(self, autoctx):
        return self.run_one_target(autoctx, target=autoctx.caster, target_index=0)

    # --- action target types ---
    def run_all_target(self, autoctx, targets):
        if autoctx.ieffect is not None:
            raise TargetException("You can only use the `self`, `parent`, or `children` target on an IEffect button.")

        result_pairs = []
        for idx, target in enumerate(self.sorted_targets(targets)):
            result_pairs.extend(self.run_one_target(autoctx, target, idx))

        return result_pairs

    def run_indexed_target(self, autoctx, targets, idx):
        if autoctx.ieffect is not None:
            raise TargetException("You can only use the `self`, `parent`, or `children` target on an IEffect button.")

        targets = self.sorted_targets(targets)
        try:
            target = targets[idx]
        except IndexError:
            return []

        return self.run_one_target(autoctx, target, 0)

    # --- button target types ---
    def run_parent_target(self, autoctx):
        if autoctx.ieffect is None:
            raise TargetException("You can only use the `self`, `each`, or numbered targets on an action.")

        parent_effect = autoctx.ieffect.get_parent_effect()
        if parent_effect is None:
            return []
        target = parent_effect.combatant
        if target is None:
            return []

        return self.run_one_target(autoctx, target, 0)

    def run_children_target(self, autoctx):
        if autoctx.ieffect is None:
            raise TargetException("You can only use the `self`, `each`, or numbered targets on an action.")

        # build target list
        targets = []
        for idx, child_effect in enumerate(autoctx.ieffect.get_children_effects()):
            target = child_effect.combatant
            if target is None:
                continue
            if target not in targets:
                targets.append(target)

        result_pairs = []
        for idx, target in enumerate(self.sorted_targets(targets)):
            result_pairs.append(self.run_one_target(autoctx, target, idx))
        return result_pairs

    # ==== helpers ====
    def sorted_targets(self, targets):
        if self.sort_by == "hp_asc":
            return sorted(targets, key=lambda t: utils.target_hp_or_default(t, float("inf")))
        elif self.sort_by == "hp_desc":
            return sorted(targets, key=lambda t: utils.target_hp_or_default(t, float("-inf")), reverse=True)
        return targets

    def run_one_target(self, autoctx, target, target_index):
        result_pairs = []
        autoctx.target = AutomationTarget(target)
        autoctx.metavars["target"] = utils.maybe_alias_statblock(target)  # #1335
        autoctx.metavars["targetIndex"] = target_index  # #1711
        autoctx.metavars["targetNumber"] = target_index + 1
        for iteration_result in self.run_effects(autoctx):
            result_pairs.append((target, iteration_result))
        return result_pairs

    def run_effects(self, autoctx):
        args = autoctx.args
        args.set_context(autoctx.target.target)
        rr = min(args.last("rr", 1, int), 25)

        in_target = autoctx.target.target is not None
        results = []

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

                iteration_results = self.run_children(self.effects, autoctx)
                total_damage += sum(r.get_damage() for r in iteration_results)
                results.append(iteration_results)

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
            results.append(self.run_children(self.effects, autoctx))
            if in_target:  # target, no rr
                autoctx.push_embed_field(autoctx.target.name)
            else:  # no target, no rr
                autoctx.push_embed_field(None, to_meta=True)

        return results

    def build_str(self, caster, evaluator):
        super().build_str(caster, evaluator)
        return self.build_child_str(self.effects, caster, evaluator)

    @property
    def children(self):
        return super().children + self.effects
