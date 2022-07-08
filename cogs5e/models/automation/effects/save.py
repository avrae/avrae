import d20

from cogs5e.models.errors import InvalidSaveType
from utils import enums
from utils.functions import maybe_mod, reconcile_adv, verbose_stat
from . import Effect
from ..errors import AutomationException, NoSpellDC, TargetException
from ..results import SaveResult
from ..utils import stringify_intexpr


class Save(Effect):
    def __init__(self, stat: str, fail: list, success: list, dc: str = None, adv: enums.AdvantageType = None, **kwargs):
        super().__init__("save", **kwargs)
        self.stat = stat
        self.fail = fail
        self.success = success
        self.dc = dc
        self.adv = adv

    @classmethod
    def from_data(cls, data):
        data["fail"] = Effect.deserialize(data["fail"])
        data["success"] = Effect.deserialize(data["success"])
        if data.get("adv") is not None:
            data["adv"] = enums.AdvantageType(data["adv"])
        return super().from_data(data)

    def to_dict(self):
        out = super().to_dict()
        fail = Effect.serialize(self.fail)
        success = Effect.serialize(self.success)
        out.update({"stat": self.stat, "fail": fail, "success": success})
        if self.dc is not None:
            out["dc"] = self.dc
        if self.adv is not None:
            out["adv"] = self.adv.value
        return out

    def run(self, autoctx):
        super().run(autoctx)
        if autoctx.target is None:
            raise TargetException(
                "Tried to make a save without a target! Make sure all Save effects are inside of a Target effect."
            )

        # ==== args ====
        save = autoctx.args.last("save") or self.stat
        sb = autoctx.args.get("sb", ephem=True)
        auto_pass = autoctx.args.last("pass", type_=bool, ephem=True)
        auto_fail = autoctx.args.last("fail", type_=bool, ephem=True)
        hide = autoctx.args.last("h", type_=bool)

        # ==== dc ====
        dc_override = None
        if self.dc:
            try:
                dc_override = autoctx.parse_intexpression(self.dc)
            except Exception:
                raise AutomationException(f"{self.dc!r} cannot be interpreted as a DC.")

        # dc hierarchy: arg > self.dc > spell cast override > spellbook dc
        dc = autoctx.caster.spellbook.dc
        if dc_override:
            dc = dc_override
        elif autoctx.dc_override is not None:
            dc = autoctx.dc_override

        if "dc" in autoctx.args:
            dc = maybe_mod(autoctx.args.last("dc"), dc)

        if dc is None:
            raise NoSpellDC("No spell save DC found. Use the `-dc` argument to specify one!")
        try:
            save_skill = next(
                s
                for s in (
                    "strengthSave",
                    "dexteritySave",
                    "constitutionSave",
                    "intelligenceSave",
                    "wisdomSave",
                    "charismaSave",
                )
                if save.lower() in s.lower()
            )
            stat = save_skill[:3]
        except StopIteration:
            raise InvalidSaveType()

        # ==== ieffects ====
        # Combine args/ieffect advantages - adv/dis (#1552)
        sadv_effects = autoctx.target_active_effects(
            mapper=lambda effect: effect.effects.save_adv, reducer=lambda saves: set().union(*saves), default=set()
        )
        sdis_effects = autoctx.target_active_effects(
            mapper=lambda effect: effect.effects.save_dis, reducer=lambda saves: set().union(*saves), default=set()
        )
        sadv = stat in sadv_effects
        sdis = stat in sdis_effects

        # ==== adv ====
        adv = reconcile_adv(
            adv=autoctx.args.last("sadv", type_=bool, ephem=True) or sadv or self.adv == enums.AdvantageType.ADV,
            dis=autoctx.args.last("sdis", type_=bool, ephem=True) or sdis or self.adv == enums.AdvantageType.DIS,
        )

        # ==== execution ====
        save_roll = None
        autoctx.metavars["lastSaveRollTotal"] = 0
        autoctx.metavars["lastSaveNaturalRoll"] = 0  # 1495
        autoctx.metavars["lastSaveDC"] = dc
        autoctx.metavars["lastSaveAbility"] = verbose_stat(stat)
        autoctx.meta_queue(f"**DC**: {dc}")

        if not autoctx.target.is_simple:
            save_blurb = f"{stat.upper()} Save"
            if auto_pass:
                is_success = True
                autoctx.queue(f"**{save_blurb}:** Automatic success!")
            elif auto_fail:
                is_success = False
                autoctx.queue(f"**{save_blurb}:** Automatic failure!")
            else:
                save_dice = autoctx.target.get_save_dice(save_skill, adv=adv, sb=sb)
                save_roll = d20.roll(save_dice)
                is_success = save_roll.total >= dc

                # get natural roll
                d20_value = d20.utils.leftmost(save_roll.expr).total

                autoctx.metavars["lastSaveRollTotal"] = save_roll.total  # 1362
                autoctx.metavars["lastSaveNaturalRoll"] = d20_value  # 1495

                success_str = "; Success!" if is_success else "; Failure!"
                out = f"**{save_blurb}**: {save_roll.result}{success_str}"
                if not hide:
                    autoctx.queue(out)
                else:
                    autoctx.add_pm(str(autoctx.ctx.author.id), out)
                    autoctx.queue(f"**{save_blurb}**: 1d20...{success_str}")
        else:
            autoctx.meta_queue(f"{stat.upper()} Save")
            is_success = False

        # Disable critical damage state for children (#1556)
        original = autoctx.in_save
        autoctx.in_save = True

        if is_success:
            children = self.on_success(autoctx)
        else:
            children = self.on_fail(autoctx)

        autoctx.in_save = original  # Restore proper crit state (#1556)

        return SaveResult(
            dc=dc, ability=save_skill, save_roll=save_roll, adv=adv, did_save=is_success, children=children
        )

    def on_success(self, autoctx):
        autoctx.metavars["lastSaveDidPass"] = True
        return self.run_children(self.success, autoctx)

    def on_fail(self, autoctx):
        autoctx.metavars["lastSaveDidPass"] = False
        return self.run_children(self.fail, autoctx)

    def build_str(self, caster, evaluator):
        super().build_str(caster, evaluator)
        dc = caster.spellbook.dc
        if self.dc:
            dc = stringify_intexpr(evaluator, self.dc)

        out = f"DC {dc} {self.stat[:3].upper()} Save"
        if self.fail:
            fail_out = self.build_child_str(self.fail, caster, evaluator)
            if fail_out:
                out += f". Fail: {fail_out}"
        if self.success:
            success_out = self.build_child_str(self.success, caster, evaluator)
            if success_out:
                out += f". Success: {success_out}"
        return out

    @property
    def children(self):
        return super().children + self.fail + self.success
