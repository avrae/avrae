from typing import TYPE_CHECKING, Tuple, Union

import d20

from utils import constants
from utils.functions import camel_to_title, maybe_mod, natural_join, reconcile_adv
from . import Effect
from ..errors import AutomationException, InvalidIntExpression, TargetException
from ..results import CheckResult
from ..utils import stringify_intexpr

if TYPE_CHECKING:
    from ..runtime import AutomationContext, AutomationTarget
    from cogs5e.models.sheet.statblock import StatBlock
    from cogs5e.models.sheet.base import Skill


class Check(Effect):
    def __init__(
        self,
        ability: str | list[str],
        dc: str = None,
        success: list[Effect] = None,
        fail: list[Effect] = None,
        **kwargs,
    ):
        super().__init__("check", **kwargs)
        self.ability = ability
        self.dc = dc
        self.success = success
        self.fail = fail

    @classmethod
    def from_data(cls, data):
        if data.get("success"):
            data["success"] = Effect.deserialize(data["success"])
        if data.get("fail"):
            data["fail"] = Effect.deserialize(data["fail"])
        return super().from_data(data)

    def to_dict(self):
        out = super().to_dict()
        out.update({"ability": self.ability})
        if self.dc is not None:
            out["dc"] = self.dc
        if self.success:
            out["success"] = Effect.serialize(self.success)
        if self.fail:
            out["fail"] = Effect.serialize(self.fail)
        return out

    def run(self, autoctx: "AutomationContext"):
        super().run(autoctx)
        if autoctx.target is None:
            raise TargetException(
                "Tried to make a check without a target! Make sure all Check effects are inside of a Target effect."
            )

        # ==== args ====
        ability_list = autoctx.args.get("ability") or self.ability_list
        auto_pass = autoctx.args.last("cpass", type_=bool, ephem=True)
        auto_fail = autoctx.args.last("cfail", type_=bool, ephem=True)
        hide = autoctx.args.last("h", type_=bool)

        if not ability_list:
            raise AutomationException("No ability passed to Check node!")
        if invalid_abilities := set(ability_list).difference(constants.SKILL_NAMES):
            raise AutomationException(f"Invalid skill names in check node: {', '.join(invalid_abilities)}")

        # ==== dc ====
        check_dc = None
        if self.dc:
            try:
                check_dc = autoctx.parse_intexpression(self.dc)
            except InvalidIntExpression:
                raise AutomationException(f"{self.dc!r} cannot be interpreted as a DC.")

        if "cdc" in autoctx.args:
            check_dc = maybe_mod(autoctx.args.last("cdc"), base=check_dc or 0)

        # ==== execution ====
        skill_name = natural_join([camel_to_title(a) for a in ability_list], "or")
        check_roll = None
        is_success = None
        autoctx.metavars["lastCheckRollTotal"] = 0
        autoctx.metavars["lastCheckNaturalRoll"] = 0
        autoctx.metavars["lastCheckAbility"] = skill_name
        autoctx.metavars["lastCheckDidPass"] = None
        autoctx.metavars["lastCheckDC"] = check_dc

        if check_dc is not None:
            autoctx.meta_queue(f"**Check DC**: {check_dc}")

        if not autoctx.target.is_simple:
            if auto_pass:
                is_success = True
                autoctx.queue(f"**{skill_name} Check:** Automatic success!")
            elif auto_fail:
                is_success = False
                autoctx.queue(f"**{skill_name} Check:** Automatic failure!")
            else:
                skill, skill_key = get_highest_skill(autoctx.target.target, ability_list)
                skill_name = camel_to_title(skill_key)
                check_dice = get_check_dice_for_statblock(autoctx, statblock_holder=autoctx, skill=skill)
                check_roll = d20.roll(check_dice)

                # get natural roll
                d20_value = d20.utils.leftmost(check_roll.expr).total

                autoctx.metavars["lastCheckRollTotal"] = check_roll.total
                autoctx.metavars["lastCheckNaturalRoll"] = d20_value
                autoctx.metavars["lastCheckAbility"] = skill_name

                if check_dc is not None:
                    is_success = check_roll.total >= check_dc
                    success_str = "; Success!" if is_success else "; Failure!"
                else:
                    success_str = ""

                out = f"**{skill_name} Check**: {check_roll.result}{success_str}"

                if not hide:
                    autoctx.queue(out)
                else:
                    autoctx.add_pm(str(autoctx.ctx.author.id), out)
                    autoctx.queue(f"**{skill_name} Check**: 1d20...{success_str}")
        else:
            autoctx.meta_queue(f"{skill_name} Check")
            is_success = True

        children = []
        if check_dc is not None:
            if is_success:
                children = self.on_success(autoctx)
            else:
                children = self.on_fail(autoctx)

        return CheckResult(
            skill_name=skill_name, check_roll=check_roll, dc=check_dc, did_succeed=is_success, children=children
        )

    def on_success(self, autoctx):
        autoctx.metavars["lastCheckDidPass"] = True
        if self.success:
            return self.run_children(self.success, autoctx)
        return []

    def on_fail(self, autoctx):
        autoctx.metavars["lastCheckDidPass"] = False
        if self.fail:
            return self.run_children(self.fail, autoctx)
        return []

    def build_str(self, caster, evaluator):
        super().build_str(caster, evaluator)
        skill_name = natural_join([camel_to_title(a) for a in self.ability_list], "or")
        if self.dc is None:
            return f"{skill_name} Check"

        dc = stringify_intexpr(evaluator, self.dc)
        out = f"DC {dc} {skill_name} Check"
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
        return super().children + (self.fail or []) + (self.success or [])

    # ==== helpers ====
    @property
    def ability_list(self) -> list[str]:
        if isinstance(self.ability, str):
            return [self.ability]
        return self.ability


def get_highest_skill(statblock: "StatBlock", skill_keys: list[str]) -> Tuple["Skill", str]:
    """Returns a pair of (skill, skill_key) that has the highest mod for the given statblock out of the given keys."""
    return max(((statblock.skills[ability], ability) for ability in skill_keys), key=lambda pair: pair[0].value)


def get_check_dice_for_statblock(
    autoctx: "AutomationContext", statblock_holder: Union["AutomationContext", "AutomationTarget"], skill: "Skill"
) -> str:
    """
    Resolves the check dice for the given skill, taking into account character settings and ieffects.

    Consumed arguments: -cb, cadv, cdis, -mc
    """

    # ==== ieffects ====
    # todo
    # sadv_effects = autoctx.target_active_effects(
    #     mapper=lambda effect: effect.effects.save_adv, reducer=lambda saves: set().union(*saves), default=set()
    # )
    # sdis_effects = autoctx.target_active_effects(
    #     mapper=lambda effect: effect.effects.save_dis, reducer=lambda saves: set().union(*saves), default=set()
    # )
    # sadv = stat in sadv_effects
    # sdis = stat in sdis_effects

    # ==== options / ieffects ====
    # reliable talent, halfling luck
    reroll = None
    min_check = None
    if statblock_holder.character:
        char_options = statblock_holder.character.options
        has_talent = bool(char_options.talent and (skill and skill.prof >= 1))
        min_check = 10 * has_talent
        reroll = char_options.reroll

    # ieffects
    cb = []
    if statblock_holder.combatant and autoctx.allow_target_ieffects:
        cb = statblock_holder.combatant.active_effects(mapper=lambda effect: effect.effects.check_bonus, default=[])

    # ==== args ====
    cb.extend(autoctx.args.get("cb", default=[], ephem=True))
    base_adv = reconcile_adv(
        adv=autoctx.args.last("cadv", type_=bool, ephem=True),
        dis=autoctx.args.last("cdis", type_=bool, ephem=True),
    )
    min_check = autoctx.args.last("mc", default=min_check, type_=int, ephem=True)

    # build final dice
    check_dice = skill.d20(base_adv=base_adv, reroll=reroll, min_val=min_check)
    if cb:
        check_dice = f"{check_dice}+{'+'.join(cb)}"
    return check_dice
