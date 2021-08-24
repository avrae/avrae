import copy

import d20
import draconic

from utils.dice import RerollableStringifier
from . import Effect
from .. import utils
from ..results import RollResult


class Roll(Effect):
    def __init__(self, dice: str, name: str, higher: dict = None, cantripScale: bool = None, hidden: bool = False,
                 **kwargs):
        super().__init__("roll", **kwargs)
        self.dice = dice
        self.name = name
        self.higher = higher
        self.cantripScale = cantripScale
        self.hidden = hidden

    def to_dict(self):
        out = super().to_dict()
        out.update({
            "dice": self.dice, "name": self.name, "hidden": self.hidden
        })
        if self.higher is not None:
            out['higher'] = self.higher
        if self.cantripScale is not None:
            out['cantripScale'] = self.cantripScale
        return out

    def run(self, autoctx):
        super().run(autoctx)
        d = autoctx.args.join('d', '+', ephem=True)
        maxdmg = autoctx.args.last('max', None, bool, ephem=True)
        mi = autoctx.args.last('mi', None, int)

        # add on combatant damage effects (#224)
        if autoctx.combatant:
            effect_d = '+'.join(autoctx.combatant.active_effects('d'))
            if effect_d:
                if d:
                    d = f"{d}+{effect_d}"
                else:
                    d = effect_d

        dice_ast = copy.copy(d20.parse(autoctx.parse_annostr(self.dice)))
        dice_ast = utils.upcast_scaled_dice(self, autoctx, dice_ast)

        if not self.hidden:
            # -mi # (#527)
            if mi:
                dice_ast = d20.utils.tree_map(utils.mi_mapper(mi), dice_ast)

            if d:
                d_ast = d20.parse(d)
                dice_ast.roll = d20.ast.BinOp(dice_ast.roll, '+', d_ast.roll)

            if maxdmg:
                dice_ast = d20.utils.tree_map(utils.max_mapper, dice_ast)

        rolled = d20.roll(dice_ast)
        if not self.hidden:
            autoctx.meta_queue(f"**{self.name.title()}**: {rolled.result}")

        simplified_expr = copy.deepcopy(rolled.expr)
        d20.utils.simplify_expr(simplified_expr)
        simplified = RerollableStringifier().stringify(simplified_expr.roll)
        autoctx.metavars[self.name] = simplified
        autoctx.metavars['lastRoll'] = rolled.total  # #1335
        return RollResult(result=rolled.total, roll=rolled, simplified=simplified, hidden=self.hidden)

    def build_str(self, caster, evaluator):
        super().build_str(caster, evaluator)
        try:
            evaluator.builtins[self.name] = evaluator.transformed_str(self.dice)
        except draconic.DraconicException:
            evaluator.builtins[self.name] = self.dice
        evaluator.builtins['lastRoll'] = 0
        return ""
