import copy

import d20
import draconic

from . import Effect
from .. import utils
from ..errors import TargetException
from ..results import TempHPResult


class TempHP(Effect):
    def __init__(
        self, amount: str, higher: dict = None, cantripScale: bool = None, **kwargs
    ):
        super().__init__("temphp", **kwargs)
        self.amount = amount
        self.higher = higher
        self.cantripScale = cantripScale

    def to_dict(self):
        out = super().to_dict()
        out.update({"amount": self.amount})
        if self.higher is not None:
            out["higher"] = self.higher
        if self.cantripScale is not None:
            out["cantripScale"] = self.cantripScale
        return out

    def run(self, autoctx):
        super().run(autoctx)
        if autoctx.target is None:
            raise TargetException(
                "Tried to add temp HP without a target! Make sure all TempHP effects are inside "
                "of a Target effect."
            )
        args = autoctx.args
        amount = self.amount
        maxdmg = args.last("max", None, bool, ephem=True)

        # check if we actually need to run this damage roll (not in combat and roll is redundant)
        if autoctx.target.is_simple and self.is_meta(autoctx, True):
            return

        amount = autoctx.parse_annostr(amount)
        dice_ast = copy.copy(d20.parse(amount))
        dice_ast = utils.upcast_scaled_dice(self, autoctx, dice_ast)

        if maxdmg:
            dice_ast = d20.utils.tree_map(utils.max_mapper, dice_ast)

        dmgroll = d20.roll(dice_ast)
        thp_amount = max(dmgroll.total, 0)
        autoctx.queue(f"**THP**: {dmgroll.result}")
        autoctx.metavars["lastTempHp"] = thp_amount  # #1335

        if autoctx.target.combatant:
            autoctx.target.combatant.temp_hp = thp_amount
            autoctx.footer_queue(
                "{}: {}".format(
                    autoctx.target.combatant.name, autoctx.target.combatant.hp_str()
                )
            )
        elif autoctx.target.character:
            autoctx.target.character.temp_hp = thp_amount
            autoctx.footer_queue(
                "{}: {}".format(
                    autoctx.target.character.name, autoctx.target.character.hp_str()
                )
            )

        return TempHPResult(amount=thp_amount, amount_roll=dmgroll)

    def is_meta(self, autoctx, strict=False):
        if not strict:
            return any(f"{{{v}}}" in self.amount for v in autoctx.metavars)
        return any(f"{{{v}}}" == self.amount for v in autoctx.metavars)

    def build_str(self, caster, evaluator):
        super().build_str(caster, evaluator)
        try:
            amount = evaluator.transformed_str(self.amount)
            evaluator.builtins["lastTempHp"] = amount
        except draconic.DraconicException:
            amount = self.amount
            evaluator.builtins["lastTempHp"] = 0
        return f"{amount} temp HP"
