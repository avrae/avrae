import copy

import d20
import draconic

from cogs5e.models.sheet.resistance import Resistances, do_resistances
from . import Effect
from .roll import RollEffectMetaVar
from .. import utils
from ..errors import TargetException
from ..results import DamageResult


class Damage(Effect):
    def __init__(
        self,
        damage: str,
        overheal: bool = False,
        higher: dict = None,
        cantripScale: bool = None,
        **kwargs,
    ):
        super().__init__("damage", **kwargs)
        self.damage = damage
        self.overheal = overheal
        # common
        self.higher = higher
        self.cantripScale = cantripScale

    def to_dict(self):
        out = super().to_dict()
        out.update({"damage": self.damage, "overheal": self.overheal})
        if self.higher is not None:
            out["higher"] = self.higher
        if self.cantripScale is not None:
            out["cantripScale"] = self.cantripScale
        return out

    def run(self, autoctx):
        super().run(autoctx)
        if autoctx.target is None:
            raise TargetException(
                "Tried to do damage without a target! Make sure all Damage effects are inside "
                "of a Target effect."
            )
        # general arguments
        args = autoctx.args
        damage = self.damage
        resistances = Resistances()
        d_args = args.get("d", [], ephem=True)
        c_args = args.get("c", [], ephem=True)
        crit_arg = args.last("crit", None, bool, ephem=True)
        nocrit = args.last("nocrit", default=False, type_=bool, ephem=True)
        max_arg = args.last("max", None, bool, ephem=True)
        magic_arg = args.last("magical", None, bool, ephem=True)
        silvered_arg = args.last("silvered", None, bool, ephem=True)
        mi_arg = args.last("mi", None, int)
        dtype_args = args.get("dtype", [], ephem=True)
        critdice = sum(args.get("critdice", type_=int))
        hide = args.last("h", type_=bool)

        # character-specific arguments
        if autoctx.character and "critdice" not in args:
            critdice = autoctx.character.options.extra_crit_dice

        # combat-specific arguments
        if not autoctx.target.is_simple:
            resistances = autoctx.target.get_resists().copy()
        resistances.update(Resistances.from_args(args, ephem=True))

        # check if we actually need to run this damage roll (not in combat and roll is redundant)
        if autoctx.target.is_simple and self.is_meta(autoctx):
            return

        # add on combatant damage effects (#224)
        if autoctx.combatant:
            d_args.extend(autoctx.combatant.active_effects("d"))

        # check if we actually need to care about the -d tag
        if self.contains_roll_meta(autoctx):
            d_args = []  # d was likely applied in the Roll effect already

        # set up damage AST
        damage = autoctx.parse_annostr(damage)
        dice_ast = copy.copy(d20.parse(damage))
        dice_ast = utils.upcast_scaled_dice(self, autoctx, dice_ast)

        # -mi # (#527)
        if mi_arg:
            dice_ast = d20.utils.tree_map(utils.mi_mapper(mi_arg), dice_ast)

        # -d #
        for d_arg in d_args:
            d_ast = d20.parse(d_arg)
            dice_ast.roll = d20.ast.BinOp(dice_ast.roll, "+", d_ast.roll)

        # crit
        # nocrit (#1216)
        # Disable critical damage in saves (#1556)
        in_crit = (autoctx.in_crit or crit_arg) and not (nocrit or autoctx.in_save)
        if in_crit:
            dice_ast = d20.utils.tree_map(utils.crit_mapper, dice_ast)
            if critdice and not autoctx.is_spell:
                utils.critdice_tree_update(dice_ast, int(critdice))

        # -c #
        if in_crit:
            for c_arg in c_args:
                c_ast = d20.parse(c_arg)
                dice_ast.roll = d20.ast.BinOp(dice_ast.roll, "+", c_ast.roll)

        # max
        if max_arg:
            dice_ast = d20.utils.tree_map(utils.max_mapper, dice_ast)

        # evaluate damage
        dmgroll = d20.roll(dice_ast)

        # magic arg (#853), magical effect (#1063)
        # silvered arg (#1544)
        always = set()
        magical_effect = autoctx.combatant and autoctx.combatant.active_effects(
            "magical"
        )
        if magical_effect or autoctx.is_spell or magic_arg:
            always.add("magical")
        silvered_effect = autoctx.combatant and autoctx.combatant.active_effects(
            "silvered"
        )
        if silvered_effect or silvered_arg:
            always.add("silvered")
        # dtype transforms/overrides (#876)
        transforms = {}
        for dtype in dtype_args:
            if ">" in dtype:
                *froms, to = dtype.split(">")
                for frm in froms:
                    transforms[frm.strip()] = to.strip()
            else:
                transforms[None] = dtype
        # display damage transforms (#1103)
        if None in transforms:
            autoctx.meta_queue(f"**Damage Type**: {transforms[None]}")
        elif transforms:
            for frm in transforms:
                autoctx.meta_queue(f"**Damage Change**: {frm} > {transforms[frm]}")

        # evaluate resistances
        do_resistances(dmgroll.expr, resistances, always, transforms)

        # determine healing/damage, stringify expr
        result = d20.MarkdownStringifier().stringify(dmgroll.expr)
        if dmgroll.total < 0:
            roll_for = "Healing"
        else:
            roll_for = "Damage"

        # output
        roll_for = roll_for if not in_crit else f"{roll_for} (CRIT!)"
        if not hide:
            autoctx.queue(f"**{roll_for}**: {result}")
        else:
            d20.utils.simplify_expr(dmgroll.expr)
            autoctx.queue(
                f"**{roll_for}**: {d20.MarkdownStringifier().stringify(dmgroll.expr)}"
            )
            autoctx.add_pm(str(autoctx.ctx.author.id), f"**{roll_for}**: {result}")

        autoctx.target.damage(autoctx, dmgroll.total, allow_overheal=self.overheal)

        # #1335
        autoctx.metavars["lastDamage"] = dmgroll.total
        return DamageResult(damage=dmgroll.total, damage_roll=dmgroll, in_crit=in_crit)

    def is_meta(self, autoctx):
        """Check if the damage string is completely a metavar sub."""
        return any(f"{{{v}}}" == self.damage for v in autoctx.metavars)

    def contains_roll_meta(self, autoctx):
        """Check if the damage string contains the result of a Roll effect."""
        return any(
            f"{{{k}}}" in self.damage
            for k, v in autoctx.metavars.items()
            if isinstance(v, RollEffectMetaVar)
        )

    def build_str(self, caster, evaluator):
        super().build_str(caster, evaluator)
        try:
            damage = evaluator.transformed_str(self.damage)
            evaluator.builtins["lastDamage"] = damage
        except draconic.DraconicException:
            damage = self.damage
            evaluator.builtins["lastDamage"] = 0

        # damage/healing
        if damage.startswith("-"):
            return f"{damage[1:].strip()} healing"
        return f"{damage} damage"
