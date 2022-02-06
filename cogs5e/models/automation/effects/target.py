from . import Effect
from .. import utils
from ..results import TargetResult
from ..runtime import AutomationTarget
from cogs5e.models.sheet.statblock import StatBlock


class Target(Effect):
    def __init__(self, target, effects: list, sorting=None, **kwargs):
        super().__init__("target", **kwargs)
        self.target = target
        self.effects = effects
        self.sorting = sorting

    @classmethod
    def from_data(cls, data):
        data['effects'] = Effect.deserialize(data['effects'])
        return super(Target, cls).from_data(data)

    def to_dict(self):
        out = super().to_dict()
        effects = [e.to_dict() for e in self.effects]
        out.update({"type": "target", "target": self.target, "effects": effects, "sorting": self.sorting})
        return out

    def run(self, autoctx):
        super().run(autoctx)
        # WEB-038 (.io #121) - this will semantically work correctly, but will make the display really weird
        previous_target = autoctx.target
        result_pairs = []

        if self.sorting == 'ascending_hp':
            targets = sorted(autoctx.targets, key = lambda t: (t.hp or 0) if isinstance(t, StatBlock) else 0)
        else:
            targets = autoctx.targets

        if self.target in ('all', 'each'):
            for target in targets:
                autoctx.target = AutomationTarget(target)
                autoctx.metavars['target'] = utils.maybe_alias_statblock(target)  # #1335
                for iteration_result in self.run_effects(autoctx):
                    result_pairs.append((target, iteration_result))
        elif self.target == 'self':
            target = autoctx.caster
            autoctx.target = AutomationTarget(target)
            autoctx.metavars['target'] = utils.maybe_alias_statblock(target)  # #1335
            for iteration_result in self.run_effects(autoctx):
                result_pairs.append((target, iteration_result))
        else:
            try:
                target = targets[self.target - 1]
                autoctx.target = AutomationTarget(target)
                autoctx.metavars['target'] = utils.maybe_alias_statblock(target)  # #1335
            except IndexError:
                return TargetResult()
            for iteration_result in self.run_effects(autoctx):
                result_pairs.append((target, iteration_result))

        autoctx.target = previous_target
        autoctx.metavars['target'] = utils.maybe_alias_statblock(previous_target)  # #1335

        targets, results = zip(*result_pairs)  # convenient unzipping :D
        return TargetResult(targets, results)

    def run_effects(self, autoctx):
        args = autoctx.args
        args.set_context(autoctx.target.target)
        rr = min(args.last('rr', 1, int), 25)

        in_target = autoctx.target.target is not None
        results = []

        # #1335
        autoctx.metavars['targetIteration'] = 1

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
                autoctx.metavars['targetIteration'] = iteration + 1

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
