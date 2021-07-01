import d20

from cogs5e.models.errors import InvalidSaveType
from utils.functions import maybe_mod
from . import Effect
from ..errors import AutomationException, NoSpellDC, TargetException
from ..results import SaveResult


class Save(Effect):
    def __init__(self, stat: str, fail: list, success: list, dc: str = None, **kwargs):
        super(Save, self).__init__("save", **kwargs)
        self.stat = stat
        self.fail = fail
        self.success = success
        self.dc = dc

    @classmethod
    def from_data(cls, data):
        data['fail'] = Effect.deserialize(data['fail'])
        data['success'] = Effect.deserialize(data['success'])
        return super(Save, cls).from_data(data)

    def to_dict(self):
        out = super(Save, self).to_dict()
        fail = Effect.serialize(self.fail)
        success = Effect.serialize(self.success)
        out.update({"stat": self.stat, "fail": fail, "success": success})
        if self.dc is not None:
            out["dc"] = self.dc
        return out

    def run(self, autoctx):
        super(Save, self).run(autoctx)
        if autoctx.target is None:
            raise TargetException("Tried to make a save without a target! Make sure all Save effects are inside "
                                  "of a Target effect.")

        save = autoctx.args.last('save') or self.stat
        auto_pass = autoctx.args.last('pass', type_=bool, ephem=True)
        auto_fail = autoctx.args.last('fail', type_=bool, ephem=True)
        hide = autoctx.args.last('h', type_=bool)
        adv = autoctx.args.adv(custom={'adv': 'sadv', 'dis': 'sdis'})

        dc_override = None
        if self.dc:
            try:
                dc_override = autoctx.parse_intexpression(self.dc)
            except Exception:
                raise AutomationException(f"{self.dc!r} cannot be interpreted as a DC.")

        # dc hierarchy: arg > self.dc > spell cast override > spellbook dc
        dc = dc_override or autoctx.dc_override or autoctx.caster.spellbook.dc
        if 'dc' in autoctx.args:
            dc = maybe_mod(autoctx.args.last('dc'), dc)

        if dc is None:
            raise NoSpellDC("No spell save DC found. Use the `-dc` argument to specify one!")
        try:
            save_skill = next(s for s in ('strengthSave', 'dexteritySave', 'constitutionSave',
                                          'intelligenceSave', 'wisdomSave', 'charismaSave') if
                              save.lower() in s.lower())
        except StopIteration:
            raise InvalidSaveType()

        save_roll = None
        autoctx.metavars['lastSaveRollTotal'] = 0
        autoctx.metavars['lastSaveNaturalRoll'] = 0  # 1495
        autoctx.metavars['lastSaveDC'] = dc

        autoctx.meta_queue(f"**DC**: {dc}")
        stat = save_skill[:3]
        if not autoctx.target.is_simple:
            save_blurb = f'{stat.upper()} Save'
            if auto_pass:
                is_success = True
                autoctx.queue(f"**{save_blurb}:** Automatic success!")
            elif auto_fail:
                is_success = False
                autoctx.queue(f"**{save_blurb}:** Automatic failure!")
            else:
                save_dice = autoctx.target.get_save_dice(save_skill, adv=adv)
                save_roll = d20.roll(save_dice)
                is_success = save_roll.total >= dc

                # get natural roll
                d20_value = d20.utils.leftmost(save_roll.expr).total

                autoctx.metavars['lastSaveRollTotal'] = save_roll.total  # 1362
                autoctx.metavars['lastSaveNaturalRoll'] = d20_value  # 1495

                success_str = ("; Success!" if is_success else "; Failure!")
                out = f"**{save_blurb}**: {save_roll.result}{success_str}"
                if not hide:
                    autoctx.queue(out)
                else:
                    autoctx.add_pm(str(autoctx.ctx.author.id), out)
                    autoctx.queue(f"**{save_blurb}**: 1d20...{success_str}")
        else:
            autoctx.meta_queue('{} Save'.format(stat.upper()))
            is_success = False

        # Disable critical damage state for children #1556
        old_in_crit = autoctx.in_crit
        autoctx.in_crit = False

        if is_success:
            children = self.on_success(autoctx)
        else:
            children = self.on_fail(autoctx)
        
        autoctx.in_crit = old_in_crit  # Restore proper crit state #1556

        return SaveResult(dc=dc, ability=save_skill, save_roll=save_roll, adv=adv, did_save=is_success,
                          children=children)

    def on_success(self, autoctx):
        autoctx.metavars['lastSaveDidPass'] = True
        return self.run_children(self.success, autoctx)

    def on_fail(self, autoctx):
        autoctx.metavars['lastSaveDidPass'] = False
        return self.run_children(self.fail, autoctx)

    def build_str(self, caster, evaluator):
        super(Save, self).build_str(caster, evaluator)
        dc = caster.spellbook.dc
        if self.dc:
            try:
                dc_override = evaluator.eval(self.dc)
                dc = int(dc_override)
            except Exception:
                dc = float('nan')

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
