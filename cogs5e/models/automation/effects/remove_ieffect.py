from typing import TYPE_CHECKING

import aliasing.api.combat
from cogs5e.models.errors import InvalidArgument
from . import Effect
from .ieffect import IEffectMetaVar
from ..errors import AutomationException
from ..results import RemoveIEffectResult

if TYPE_CHECKING:
    from . import AutomationContext
    from cogs5e.initiative import InitiativeEffect


class RemoveIEffect(Effect):
    def __init__(self, removeParent: str = None, target: str = None, **kwargs):
        super().__init__("remove_ieffect", **kwargs)
        self.remove_parent = removeParent
        self.target = target

    def to_dict(self):
        out = super().to_dict()
        if self.remove_parent is not None:
            out["removeParent"] = self.remove_parent
        if self.target is not None:
            out["target"] = self.target
        return out

    def run(self, autoctx: "AutomationContext"):
        super().run(autoctx)
        ieffect = None
        if self.target:
            ieffect_ref = autoctx.metavars.get(self.target, None)
            if not isinstance(ieffect_ref, (IEffectMetaVar, aliasing.api.combat.SimpleEffect)):
                raise InvalidArgument(
                    f"Could not set IEffect target: The variable `{self.target}` is not an IEffectMetaVar "
                    f"(got `{type(ieffect_ref).__name__}`)."
                )

            # noinspection PyProtectedMember
            ieffect = ieffect_ref._effect
            autoctx.queue(f"**Cancelled Effect**: {ieffect.name} on {ieffect.combatant.name}")
        elif (ieffect := autoctx.ieffect) is None:
            raise AutomationException("Tried to remove an IEffect without an active IEffect context!")
        else:
            autoctx.meta_queue(f"**Removed Effect**: {ieffect.name}")

        # remove the effect
        removed_parent = None
        if ieffect:
            ieffect.remove()

            # remove parent, if applicable
            if self.remove_parent is not None and (parent_effect := ieffect.get_parent_effect()) is not None:
                removed_parent = self.run_remove_parent(autoctx, parent_effect)

        return RemoveIEffectResult(removed_effect=ieffect, removed_parent=removed_parent)

    def run_remove_parent(self, autoctx: "AutomationContext", parent_effect: "InitiativeEffect"):
        do_remove = self.remove_parent == "always" or (
            self.remove_parent == "if_no_children" and not any(parent_effect.get_children_effects())
        )
        if do_remove:
            parent_effect.remove()
            autoctx.meta_queue(f"**Removed Effect**: {parent_effect.name}")
            return parent_effect

    def build_str(self, caster, evaluator):
        super().build_str(caster, evaluator)
        # this should only display when a target is used since IEffect button automation is never stringified
        return "Removes targeted effect"
