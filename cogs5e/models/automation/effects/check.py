from typing import TYPE_CHECKING, Tuple, Union

import d20

from utils import constants, enums
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
        contestAbility: str | list[str] = None,
        dc: str = None,
        success: list[Effect] = None,
        fail: list[Effect] = None,
        contestTie: str = None,
        adv: enums.AdvantageType = None,
        **kwargs,
    ):
        super().__init__("check", **kwargs)
        self.ability = ability
        self.contest_ability = contestAbility
        self.dc = dc
        self.success = success
        self.fail = fail
        self.contest_tie_behaviour = contestTie
        self.adv = adv

    @classmethod
    def from_data(cls, data):
        if data.get("success"):
            data["success"] = Effect.deserialize(data["success"])
        if data.get("fail"):
            data["fail"] = Effect.deserialize(data["fail"])
        if data.get("adv") is not None:
            data["adv"] = enums.AdvantageType(data["adv"])
        return super().from_data(data)

    def to_dict(self):
        out = super().to_dict()
        out.update({"ability": self.ability})
        if self.contest_ability is not None:
            out["contestAbility"] = self.contest_ability
        if self.dc is not None:
            out["dc"] = self.dc
        if self.success:
            out["success"] = Effect.serialize(self.success)
        if self.fail:
            out["fail"] = Effect.serialize(self.fail)
        if self.contest_tie_behaviour:
            out["contestTie"] = self.contest_tie_behaviour
        if self.adv:
            out["adv"] = self.adv.value
        return out

    def run(self, autoctx: "AutomationContext"):
        super().run(autoctx)

        # ==== checks ====
        # must be in target
        if autoctx.target is None:
            raise TargetException(
                "Tried to make a check without a target! Make sure all Check effects are inside of a Target effect."
            )

        # dc and ability contest are mutually exclusive
        if self.dc is not None and self.contest_ability is not None:
            raise AutomationException("Cannot specify both a check's DC and a contest ability.")

        # ==== args ====
        ability_list = autoctx.args.get("ability") or self.ability_list
        auto_pass = autoctx.args.last("cpass", type_=bool, ephem=True)
        auto_fail = autoctx.args.last("cfail", type_=bool, ephem=True)
        check_bonus = autoctx.args.get("cb", ephem=True)
        base_adv = reconcile_adv(
            adv=autoctx.args.last("cadv", type_=bool, ephem=True) or self.adv == enums.AdvantageType.ADV,
            dis=autoctx.args.last("cdis", type_=bool, ephem=True) or self.adv == enums.AdvantageType.DIS,
        )
        min_check = autoctx.args.last("mc", type_=int, ephem=True)
        hide = autoctx.args.last("h", type_=bool)

        if not ability_list:
            raise AutomationException("No ability passed to Check node!")
        if invalid_abilities := set(ability_list).difference(constants.SKILL_NAMES):
            raise AutomationException(f"Invalid skill names in check node: {', '.join(invalid_abilities)}")

        # ==== setup ====
        skill_name = natural_join([camel_to_title(a) for a in ability_list], "or")
        check_roll = None
        is_success = None
        autoctx.metavars["lastCheckRollTotal"] = 0
        autoctx.metavars["lastCheckNaturalRoll"] = 0
        autoctx.metavars["lastCheckAbility"] = skill_name
        autoctx.metavars["lastCheckDidPass"] = None
        autoctx.metavars["lastContestRollTotal"] = None
        autoctx.metavars["lastContestNaturalRoll"] = None
        autoctx.metavars["lastContestAbility"] = None
        autoctx.metavars["lastContestDidTie"] = False

        # ==== dc ====
        check_dc = None
        if self.dc:
            try:
                check_dc = autoctx.parse_intexpression(self.dc)
            except InvalidIntExpression:
                raise AutomationException(f"{self.dc!r} cannot be interpreted as a DC.")

        if "cdc" in autoctx.args:
            check_dc = maybe_mod(autoctx.args.last("cdc"), base=check_dc or 0)

        if check_dc is not None:
            autoctx.meta_queue(f"**Check DC**: {check_dc}")

        autoctx.metavars["lastCheckDC"] = check_dc

        # ==== contest ====
        contest_skill_name = None
        contest_roll = None
        if self.contest_ability is not None:
            contest_skill, contest_skill_key = get_highest_skill(autoctx.caster, self.contest_ability_list)
            contest_skill_name = camel_to_title(contest_skill_key)
            contest_dice = get_check_dice_for_statblock(
                autoctx, statblock_holder=autoctx, skill=contest_skill, skill_key=contest_skill_key
            )
            contest_roll = d20.roll(contest_dice)

            autoctx.metavars["lastContestRollTotal"] = contest_roll.total
            autoctx.metavars["lastContestNaturalRoll"] = d20.utils.leftmost(contest_roll.expr).total
            autoctx.metavars["lastContestAbility"] = contest_skill_name

            autoctx.queue(f"**{contest_skill_name} Contest ({autoctx.caster.name})**: {contest_roll.result}")

        # ==== execution ====
        if auto_pass:
            is_success = True
            autoctx.queue(f"**{skill_name} Check:** Automatic success!")
        elif auto_fail:
            is_success = False
            autoctx.queue(f"**{skill_name} Check:** Automatic failure!")
        elif not autoctx.target.is_simple:
            # roll for the target
            skill, skill_key = get_highest_skill(autoctx.target.target, ability_list)
            skill_name = camel_to_title(skill_key)
            check_dice = get_check_dice_for_statblock(
                autoctx,
                statblock_holder=autoctx.target,
                skill=skill,
                skill_key=skill_key,
                bonus=check_bonus,
                base_adv=base_adv,
                min_check=min_check,
            )
            check_roll = d20.roll(check_dice)

            autoctx.metavars["lastCheckRollTotal"] = check_roll.total
            autoctx.metavars["lastCheckNaturalRoll"] = d20.utils.leftmost(check_roll.expr).total
            autoctx.metavars["lastCheckAbility"] = skill_name

            success_str = ""
            if check_dc is not None:
                is_success = check_roll.total >= check_dc
                success_str = "; Success!" if is_success else "; Failure!"
            elif contest_roll is not None:
                if check_roll.total > contest_roll.total:
                    is_success = True
                    success_str = "; Success!"
                elif check_roll.total == contest_roll.total:
                    success_str = "; Tie!"
                    autoctx.metavars["lastContestDidTie"] = True
                    if self.contest_tie_behaviour == "fail" or self.contest_tie_behaviour is None:
                        is_success = False
                    elif self.contest_tie_behaviour == "success":
                        is_success = True
                else:
                    is_success = False
                    success_str = "; Failure!"

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
        if is_success is True:  # this is a literal comp because it can be None, in which case we do not want to run
            children = self.on_success(autoctx)
        elif is_success is False:
            children = self.on_fail(autoctx)

        return CheckResult(
            skill_name=skill_name,
            check_roll=check_roll,
            dc=check_dc,
            did_succeed=is_success,
            children=children,
            contest_skill_name=contest_skill_name,
            contest_roll=contest_roll,
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
        if self.dc is not None:
            dc = stringify_intexpr(evaluator, self.dc)
            out = f"DC {dc} {skill_name} Check"
        elif self.contest_ability is not None:
            contest_skill_name = natural_join([camel_to_title(a) for a in self.contest_ability_list], "or")
            out = f"{skill_name} Check vs. caster's {contest_skill_name} Check"
        else:
            return f"{skill_name} Check"

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

    @property
    def contest_ability_list(self) -> list[str] | None:
        if isinstance(self.contest_ability, str):
            return [self.contest_ability]
        return self.contest_ability


def get_highest_skill(statblock: "StatBlock", skill_keys: list[str]) -> Tuple["Skill", str]:
    """Returns a pair of (skill, skill_key) that has the highest mod for the given statblock out of the given keys."""
    return max(((statblock.skills[ability], ability) for ability in skill_keys), key=lambda pair: pair[0].value)


def get_check_dice_for_statblock(
    autoctx: "AutomationContext",
    statblock_holder: Union["AutomationContext", "AutomationTarget"],
    skill: "Skill",
    skill_key: str,
    bonus: list[str] = None,
    base_adv: enums.AdvantageType = None,
    min_check: int = None,
) -> str:
    """
    Resolves the check dice for the given skill, taking into account character settings and ieffects.
    """

    # ==== options / ieffects ====
    # reliable talent, halfling luck
    reroll = None
    if statblock_holder.character:
        char_options = statblock_holder.character.options
        has_talent = bool(char_options.talent and (skill and skill.prof >= 1))
        min_check = min_check or 10 * has_talent
        reroll = char_options.reroll

    # ieffects
    cb = bonus or []
    if statblock_holder.combatant and autoctx.allow_target_ieffects:
        combatant = statblock_holder.combatant
        base_ability_key = constants.SKILL_MAP[skill_key]
        # -cb
        cb.extend(combatant.active_effects(mapper=lambda effect: effect.effects.check_bonus, default=[]))

        # -cadv, -cdis
        cadv_effects = combatant.active_effects(
            mapper=lambda effect: effect.effects.check_adv, reducer=lambda checks: set().union(*checks), default=set()
        )
        cdis_effects = combatant.active_effects(
            mapper=lambda effect: effect.effects.check_dis, reducer=lambda checks: set().union(*checks), default=set()
        )

        base_adv = reconcile_adv(
            adv=base_adv == enums.AdvantageType.ADV or skill_key in cadv_effects or base_ability_key in cadv_effects,
            dis=base_adv == enums.AdvantageType.DIS or skill_key in cdis_effects or base_ability_key in cdis_effects,
        )

    # build final dice
    if base_adv == enums.AdvantageType.ADV:
        boolwise_adv = True
    elif base_adv == enums.AdvantageType.DIS:
        boolwise_adv = False
    else:
        boolwise_adv = None
    check_dice = skill.d20(base_adv=boolwise_adv, reroll=reroll, min_val=min_check)
    if cb:
        check_dice = f"{check_dice}+{'+'.join(cb)}"
    return check_dice
