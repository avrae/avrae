from typing import TYPE_CHECKING

from . import Effect
from ..errors import AutomationException
from ..results import RemoveIEffectResult

if TYPE_CHECKING:
    from . import AutomationContext
    from cogs5e.initiative import InitiativeEffect


class RemoveIEffect(Effect):
    def __init__(self, removeParent: str = None, **kwargs):
        super().__init__("remove_ieffect", **kwargs)
        self.remove_parent = removeParent

    def to_dict(self):
        out = super().to_dict()
        if self.remove_parent is not None:
            out["removeParent"] = self.remove_parent
        return out

    def run(self, autoctx: "AutomationContext"):
        super().run(autoctx)
        if autoctx.ieffect is None:
            raise AutomationException("Tried to remove an IEffect without an active IEffect context!")

        # remove the effect
        autoctx.ieffect.remove()
        autoctx.meta_queue(f"**Removed Effect**: {autoctx.ieffect.name}")

        # remove parent, if applicable
        removed_parent = None
        if self.remove_parent is not None and (parent_effect := autoctx.ieffect.get_parent_effect()) is not None:
            removed_parent = self.run_remove_parent(autoctx, parent_effect)

        return RemoveIEffectResult(removed_effect=autoctx.ieffect, removed_parent=removed_parent)

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
        # this should never display since IEffect button automation is never stringified
        return "Removes triggering effect"
