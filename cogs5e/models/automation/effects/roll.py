import copy
from functools import cached_property

import d20
import draconic
import math

from utils.dice import RerollableStringifier
from . import Effect
from .. import utils
from ..results import RollResult


class Roll(Effect):
    def __init__(
        self,
        dice: str,
        name: str,
        higher: dict = None,
        cantripScale: bool = None,
        hidden: bool = False,
        displayName: str = None,
        fixedValue: bool = None,
        **kwargs,
    ):
        super().__init__("roll", **kwargs)
        self.dice = dice
        self.name = name
        self.higher = higher
        self.cantripScale = cantripScale
        self.hidden = hidden
        self.displayName = displayName
        self.fixedValue = fixedValue

    def to_dict(self):
        out = super().to_dict()
        out.update({"dice": self.dice, "name": self.name, "hidden": self.hidden})
        if self.higher is not None:
            out["higher"] = self.higher
        if self.cantripScale is not None:
            out["cantripScale"] = self.cantripScale
        if self.displayName is not None:
            out["displayName"] = self.displayName
        if self.fixedValue is not None:
            out["fixedValue"] = self.fixedValue
        return out

    def run(self, autoctx):
        super().run(autoctx)

        dice_ast = copy.copy(d20.parse(autoctx.parse_annostr(self.dice)))
        dice_ast = utils.upcast_scaled_dice(self, autoctx, dice_ast)

        if not (self.fixedValue or self.hidden):
            d = autoctx.args.join("d", "+", ephem=True)

            # add on combatant damage effects (#224)
            effect_d = autoctx.caster_active_effects(
                mapper=lambda effect: effect.effects.damage_bonus, reducer="+".join
            )
            if effect_d:
                if d:
                    d = f"{d}+{effect_d}"
                else:
                    d = effect_d

            if d:
                d_ast = d20.parse(d)
                dice_ast.roll = d20.ast.BinOp(dice_ast.roll, "+", d_ast.roll)
        if not self.hidden:
            maxdmg = autoctx.args.last("max", None, bool, ephem=True)
            mi = autoctx.args.last("mi", None, int)

            # -mi # (#527)
            if mi:
                dice_ast = d20.utils.tree_map(utils.mi_mapper(mi), dice_ast)

            if maxdmg:
                dice_ast = d20.utils.tree_map(utils.max_mapper, dice_ast)

        rolled = d20.roll(dice_ast)
        if not self.hidden:
            name_out = self.displayName
            if not name_out:
                name_out = self.name.title()
            autoctx.meta_queue(f"**{name_out}**: {rolled.result}")

        simplified_expr = copy.deepcopy(rolled.expr)
        d20.utils.simplify_expr(simplified_expr)
        simplified_metavar = RollEffectMetaVar(simplified_expr)
        autoctx.metavars[self.name] = simplified_metavar
        autoctx.metavars["lastRoll"] = rolled.total  # #1335
        return RollResult(result=rolled.total, roll=rolled, simplified_metavar=simplified_metavar, hidden=self.hidden)

    def build_str(self, caster, evaluator):
        super().build_str(caster, evaluator)
        try:
            evaluator.builtins[self.name] = evaluator.transformed_str(self.dice)
        except draconic.DraconicException:
            evaluator.builtins[self.name] = self.dice
        evaluator.builtins["lastRoll"] = 0
        return ""


class RollEffectMetaVar:
    """
    Proxy type for the rerollable string generated in Roll effects. This is its own class to allow checking if a
    metavar was generated as the result of a Roll.
    """

    def __init__(self, simplified_expr: d20.Expression):
        self._expr = simplified_expr

    # cached props
    @cached_property
    def _str(self):
        return RerollableStringifier().stringify(self._expr.roll)

    @cached_property
    def _total(self):
        return self._expr.total

    # magic methods
    def __str__(self):
        return self._str

    def __int__(self):
        return int(self._total)

    def __float__(self):
        return float(self._total)

    def __bool__(self):
        return bool(self._total)

    def __eq__(self, other):
        return self._total == other

    def __lt__(self, other):
        return self._total < other

    def __le__(self, other):
        return self._total <= other

    def __ne__(self, other):
        return self._total != other

    def __gt__(self, other):
        return self._total > other

    def __ge__(self, other):
        return self._total >= other

    def __floor__(self):
        return math.floor(self._total)

    def __ceil__(self):
        return math.ceil(self._total)

    def __add__(self, other):
        return self._lbin_op(other, "+")

    def __sub__(self, other):
        return self._lbin_op(other, "-")

    def __mul__(self, other):
        return self._lbin_op(other, "*")

    def __floordiv__(self, other):
        return self._lbin_op(other, "//")

    def __truediv__(self, other):
        return self._lbin_op(other, "/")

    def __mod__(self, other):
        return self._lbin_op(other, "%")

    def __radd__(self, other):
        return self._rbin_op(other, "+")

    def __rsub__(self, other):
        return self._rbin_op(other, "-")

    def __rmul__(self, other):
        return self._rbin_op(other, "*")

    def __rfloordiv__(self, other):
        return self._rbin_op(other, "//")

    def __rtruediv__(self, other):
        return self._rbin_op(other, "/")

    def __rmod__(self, other):
        return self._rbin_op(other, "%")

    def _lbin_op(self, other, op):
        if isinstance(other, (int, float)):
            return RollEffectMetaVar(d20.Expression(d20.BinOp(self._expr, op, d20.Literal(other)), self._expr.comment))
        elif isinstance(other, RollEffectMetaVar):
            return RollEffectMetaVar(d20.Expression(d20.BinOp(self._expr, op, other._expr), self._expr.comment))
        raise NotImplementedError

    def _rbin_op(self, other, op):
        if isinstance(other, (int, float)):
            return RollEffectMetaVar(d20.Expression(d20.BinOp(d20.Literal(other), op, self._expr), self._expr.comment))
        elif isinstance(other, RollEffectMetaVar):
            return RollEffectMetaVar(d20.Expression(d20.BinOp(other._expr, op, self._expr), self._expr.comment))
        raise NotImplementedError

    def __pos__(self):
        return RollEffectMetaVar(d20.Expression(d20.UnOp("+", self._expr), self._expr.comment))

    def __neg__(self):
        return RollEffectMetaVar(d20.Expression(d20.UnOp("-", self._expr), self._expr.comment))
