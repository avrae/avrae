import copy
import logging

import d20
from d20 import roll

from cogs5e.models import initiative as init
from cogs5e.models.errors import InvalidArgument, InvalidSaveType
from cogs5e.models.sheet.resistance import Resistances, do_resistances
from utils.dice import RerollableStringifier
from utils.functions import maybe_mod
from .errors import *
from .results import *
from .runtime import AutomationContext, AutomationTarget
from .utils import FeatureReference, SpellSlotReference, crit_mapper, deserialize_usecounter_target, max_mapper, \
    maybe_alias_statblock, mi_mapper, upcast_scaled_dice

log = logging.getLogger(__name__)

__all__ = (
    'Effect', 'Target', 'Attack', 'Save', 'Damage', 'TempHP', 'IEffect', 'Roll', 'Text', 'SetVariable', 'Condition',
    'UseCounter'
)


class Effect:
    def __init__(self, type_, meta=None, **_):  # ignore bad kwargs
        self.type = type_
        if meta:  # meta is deprecated
            meta = Effect.deserialize(meta)
        else:
            meta = []
        self.meta = meta

    @staticmethod
    def deserialize(data):
        return [EFFECT_MAP[e['type']].from_data(e) for e in data]

    @staticmethod
    def serialize(obj_list):
        return [e.to_dict() for e in obj_list]

    @staticmethod
    def run_children(child, autoctx):
        results = []
        for effect in child:
            try:
                result = effect.run(autoctx)
                if result is not None:
                    results.append(result)
            except StopExecution:
                raise
            except AutomationException as e:
                autoctx.meta_queue(f"**Error**: {e}")
        return results

    # required methods
    @classmethod
    def from_data(cls, data):  # catch-all
        data.pop('type')
        return cls(**data)

    def to_dict(self):
        meta = Effect.serialize(self.meta or [])
        return {"type": self.type, "meta": meta}

    def run(self, autoctx):
        log.debug(f"Running {self.type}")
        if self.meta:
            for metaeffect in self.meta:
                metaeffect.run(autoctx)

    def build_str(self, caster, evaluator):
        if self.meta:
            for metaeffect in self.meta:
                # metaeffects shouldn't add anything to a str - they should set up annostrs
                metaeffect.build_str(caster, evaluator)
        return "I do something (you shouldn't see this)"

    @staticmethod
    def build_child_str(child, caster, evaluator):
        out = []
        for effect in child:
            effect_str = effect.build_str(caster, evaluator)
            if effect_str:
                out.append(effect_str)
        return ', '.join(out)

    @property
    def children(self):
        """Returns the child effects of this effect."""
        return self.meta


class Target(Effect):
    def __init__(self, target, effects: list, **kwargs):
        super(Target, self).__init__("target", **kwargs)
        self.target = target
        self.effects = effects

    @classmethod
    def from_data(cls, data):
        data['effects'] = Effect.deserialize(data['effects'])
        return super(Target, cls).from_data(data)

    def to_dict(self):
        out = super(Target, self).to_dict()
        effects = [e.to_dict() for e in self.effects]
        out.update({"type": "target", "target": self.target, "effects": effects})
        return out

    def run(self, autoctx):
        super(Target, self).run(autoctx)
        # WEB-038 (.io #121) - this will semantically work correctly, but will make the display really weird
        previous_target = autoctx.target
        result_pairs = []

        if self.target in ('all', 'each'):
            for target in autoctx.targets:
                autoctx.target = AutomationTarget(target)
                autoctx.metavars['target'] = maybe_alias_statblock(target)  # #1335
                for iteration_result in self.run_effects(autoctx):
                    result_pairs.append((target, iteration_result))
        elif self.target == 'self':
            target = autoctx.caster
            autoctx.target = AutomationTarget(target)
            autoctx.metavars['target'] = maybe_alias_statblock(target)  # #1335
            for iteration_result in self.run_effects(autoctx):
                result_pairs.append((target, iteration_result))
        else:
            try:
                target = autoctx.targets[self.target - 1]
                autoctx.target = AutomationTarget(target)
                autoctx.metavars['target'] = maybe_alias_statblock(target)  # #1335
            except IndexError:
                return TargetResult()
            for iteration_result in self.run_effects(autoctx):
                result_pairs.append((target, iteration_result))

        autoctx.target = previous_target
        autoctx.metavars['target'] = maybe_alias_statblock(previous_target)  # #1335

        targets, results = zip(*result_pairs)  # convenient unzipping :D
        return TargetResult(targets, results)

    def run_effects(self, autoctx):
        args = autoctx.args
        args.set_context(autoctx.target.target)
        rr = min(args.last('rr', 1, int), 25)

        in_target = autoctx.target.target is not None
        results = []

        # #1335
        autoctx.metavars['targetIteration'] = 1

        # 2 binary attributes: (rr?, target?)
        # each case must end with a push_embed_field()
        if rr > 1:
            total_damage = 0
            for iteration in range(rr):
                if len(self.effects) == 1:
                    iter_title = f"{type(self.effects[0]).__name__} {iteration + 1}"
                else:
                    iter_title = f"Iteration {iteration + 1}"

                # #1335
                autoctx.metavars['targetIteration'] = iteration + 1

                # target, rr
                if in_target:
                    autoctx.queue(f"\n**__{iter_title}__**")

                iteration_results = self.run_children(self.effects, autoctx)
                total_damage += sum(r.get_damage() for r in iteration_results)
                results.append(iteration_results)

                # no target, rr
                if not in_target:
                    autoctx.push_embed_field(iter_title)

            if in_target:  # target, rr
                if total_damage:
                    autoctx.queue(f"\n**__Total Damage__**: {total_damage}")

                autoctx.push_embed_field(autoctx.target.name)
            else:  # no target, rr
                if total_damage:
                    autoctx.queue(f"{total_damage}")
                    autoctx.push_embed_field("Total Damage", inline=True)
        else:
            results.append(self.run_children(self.effects, autoctx))
            if in_target:  # target, no rr
                autoctx.push_embed_field(autoctx.target.name)
            else:  # no target, no rr
                autoctx.push_embed_field(None, to_meta=True)

        return results

    def build_str(self, caster, evaluator):
        super(Target, self).build_str(caster, evaluator)
        return self.build_child_str(self.effects, caster, evaluator)

    @property
    def children(self):
        return super().children + self.effects


class Attack(Effect):
    def __init__(self, hit: list, miss: list, attackBonus: str = None, **kwargs):
        super(Attack, self).__init__("attack", **kwargs)
        self.hit = hit
        self.miss = miss
        self.bonus = attackBonus

    @classmethod
    def from_data(cls, data):
        data['hit'] = Effect.deserialize(data['hit'])
        data['miss'] = Effect.deserialize(data['miss'])
        return super(Attack, cls).from_data(data)

    def to_dict(self):
        out = super(Attack, self).to_dict()
        hit = Effect.serialize(self.hit)
        miss = Effect.serialize(self.miss)
        out.update({"hit": hit, "miss": miss})
        if self.bonus is not None:
            out["attackBonus"] = self.bonus
        return out

    def run(self, autoctx: AutomationContext):
        super(Attack, self).run(autoctx)
        # arguments
        args = autoctx.args
        adv = args.adv(ea=True, ephem=True)
        crit = args.last('crit', None, bool, ephem=True) and 1
        nocrit = args.last('nocrit', default=False, type_=bool, ephem=True)
        hit = args.last('hit', None, bool, ephem=True) and 1
        miss = (args.last('miss', None, bool, ephem=True) and not hit) and 1
        b = args.join('b', '+', ephem=True)
        hide = args.last('h', type_=bool)

        reroll = args.last('reroll', 0, int)
        criton = args.last('criton', 20, int)
        ac = args.last('ac', None, int)

        # character-specific arguments
        if autoctx.character:
            if 'reroll' not in args:
                reroll = autoctx.character.get_setting('reroll', 0)
            if 'criton' not in args:
                criton = autoctx.character.get_setting('criton', 20)

        # check for combatant IEffect bonus (#224)
        if autoctx.combatant:
            effect_b = '+'.join(autoctx.combatant.active_effects('b'))
            if effect_b and b:
                b = f"{b}+{effect_b}"
            elif effect_b:
                b = effect_b

        attack_bonus = autoctx.ab_override or autoctx.caster.spellbook.sab

        # explicit bonus
        if self.bonus:
            try:
                attack_bonus = autoctx.parse_intexpression(self.bonus)
            except Exception:
                raise AutomationException(f"{self.bonus!r} cannot be interpreted as an attack bonus.")

        if attack_bonus is None and b is None:
            raise NoAttackBonus("No spell attack bonus found. Use the `-b` argument to specify one!")

        # reset metavars (#1335)
        autoctx.metavars['lastAttackDidHit'] = False
        autoctx.metavars['lastAttackDidCrit'] = False
        autoctx.metavars['lastAttackRollTotal'] = 0  # 1362
        did_hit = True
        did_crit = False
        to_hit_roll = None

        # roll attack against autoctx.target
        if not (hit or miss):
            # reroll before kh/kl (#1199)
            reroll_str = ''
            if reroll:
                reroll_str = f"ro{reroll}"

            if adv == 1:
                formatted_d20 = f'2d20{reroll_str}kh1'
            elif adv == 2:
                formatted_d20 = f'3d20{reroll_str}kh1'
            elif adv == -1:
                formatted_d20 = f'2d20{reroll_str}kl1'
            else:
                formatted_d20 = f'1d20{reroll_str}'

            to_hit_message = 'To Hit'
            if ac:
                to_hit_message = f'To Hit (AC {ac})'

            if b:
                to_hit_roll = roll(f"{formatted_d20}+{attack_bonus}+{b}")
            else:
                to_hit_roll = roll(f"{formatted_d20}+{attack_bonus}")

            # hit/miss/crit processing
            # leftmost roll value - -criton
            left = to_hit_roll.expr
            while left.children:
                left = left.children[0]
            d20_value = left.total

            # -ac #
            target_has_ac = not autoctx.target.is_simple and autoctx.target.ac is not None
            if target_has_ac:
                ac = ac or autoctx.target.ac

            # assign hit values
            if d20_value >= criton or to_hit_roll.crit == d20.CritType.CRIT or (crit and not nocrit):  # crit
                did_crit = True if not nocrit else False
            elif to_hit_roll.crit == d20.CritType.FAIL:  # crit fail
                did_hit = False
            elif ac and to_hit_roll.total < ac:  # miss
                did_hit = False

            autoctx.metavars['lastAttackRollTotal'] = to_hit_roll.total  # 1362

            # output
            if not hide:  # not hidden
                autoctx.queue(f"**{to_hit_message}**: {to_hit_roll.result}")
            elif target_has_ac:  # hidden
                if not did_hit:
                    hit_type = 'MISS'
                elif did_crit:
                    hit_type = 'CRIT'
                else:
                    hit_type = 'HIT'
                autoctx.queue(f"**To Hit**: {formatted_d20}... = `{hit_type}`")
                autoctx.add_pm(str(autoctx.ctx.author.id), f"**{to_hit_message}**: {to_hit_roll.result}")
            else:  # hidden, no ac
                autoctx.queue(f"**To Hit**: {formatted_d20}... = `{to_hit_roll.total}`")
                autoctx.add_pm(str(autoctx.ctx.author.id), f"**{to_hit_message}**: {to_hit_roll.result}")

            if not did_hit:
                children = self.on_miss(autoctx)
            elif did_crit:
                children = self.on_crit(autoctx)
            else:
                children = self.on_hit(autoctx)
        elif hit:
            autoctx.queue(f"**To Hit**: Automatic hit!")
            # nocrit and crit cancel out
            if crit and not nocrit:
                did_crit = True
                children = self.on_crit(autoctx)
            else:
                children = self.on_hit(autoctx)
        else:
            did_hit = False
            autoctx.queue(f"**To Hit**: Automatic miss!")
            children = self.on_miss(autoctx)

        return AttackResult(
            attack_bonus=attack_bonus, ac=ac, to_hit_roll=to_hit_roll, adv=adv, did_hit=did_hit, did_crit=did_crit,
            children=children
        )

    def on_hit(self, autoctx):
        # assign metavars (#1335)
        autoctx.metavars['lastAttackDidHit'] = True
        return self.run_children(self.hit, autoctx)

    def on_crit(self, autoctx):
        original = autoctx.in_crit
        autoctx.in_crit = True
        autoctx.metavars['lastAttackDidCrit'] = True
        result = self.on_hit(autoctx)
        autoctx.in_crit = original
        return result

    def on_miss(self, autoctx):
        autoctx.queue("**Miss!**")
        return self.run_children(self.miss, autoctx)

    def build_str(self, caster, evaluator):
        super(Attack, self).build_str(caster, evaluator)
        attack_bonus = caster.spellbook.sab
        if self.bonus:
            try:
                explicit_bonus = evaluator.eval(self.bonus)
                attack_bonus = int(explicit_bonus)
            except Exception:
                attack_bonus = float('nan')

        out = f"Attack: {attack_bonus:+} to hit"
        if self.hit:
            hit_out = self.build_child_str(self.hit, caster, evaluator)
            if hit_out:
                out += f". Hit: {hit_out}"
        if self.miss:
            miss_out = self.build_child_str(self.miss, caster, evaluator)
            if miss_out:
                out += f". Miss: {', '.join(miss_out)}"
        return out

    @property
    def children(self):
        return super().children + self.hit + self.miss


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

        autoctx.meta_queue(f"**DC**: {dc}")
        autoctx.metavars['lastSaveRollTotal'] = 0
        if not autoctx.target.is_simple:
            save_blurb = f'{save_skill[:3].upper()} Save'
            if auto_pass:
                is_success = True
                autoctx.queue(f"**{save_blurb}:** Automatic success!")
            elif auto_fail:
                is_success = False
                autoctx.queue(f"**{save_blurb}:** Automatic failure!")
            else:
                saveroll = autoctx.target.get_save_dice(save_skill, adv=adv)
                save_roll = roll(saveroll)
                is_success = save_roll.total >= dc
                autoctx.metavars['lastSaveRollTotal'] = save_roll.total  # 1362
                success_str = ("; Success!" if is_success else "; Failure!")
                out = f"**{save_blurb}**: {save_roll.result}{success_str}"
                if not hide:
                    autoctx.queue(out)
                else:
                    autoctx.add_pm(str(autoctx.ctx.author.id), out)
                    autoctx.queue(f"**{save_blurb}**: 1d20...{success_str}")
        else:
            autoctx.meta_queue('{} Save'.format(save_skill[:3].upper()))
            is_success = False

        if is_success:
            children = self.on_success(autoctx)
        else:
            children = self.on_fail(autoctx)
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


class Damage(Effect):
    def __init__(self, damage: str, overheal: bool = False, higher: dict = None, cantripScale: bool = None, **kwargs):
        super(Damage, self).__init__("damage", **kwargs)
        self.damage = damage
        self.overheal = overheal
        # common
        self.higher = higher
        self.cantripScale = cantripScale

    def to_dict(self):
        out = super(Damage, self).to_dict()
        out.update({
            "damage": self.damage, "overheal": self.overheal
        })
        if self.higher is not None:
            out['higher'] = self.higher
        if self.cantripScale is not None:
            out['cantripScale'] = self.cantripScale
        return out

    def run(self, autoctx):
        super(Damage, self).run(autoctx)
        # general arguments
        args = autoctx.args
        damage = self.damage
        resistances = Resistances()
        d_args = args.get('d', [], ephem=True)
        c_args = args.get('c', [], ephem=True)
        crit_arg = args.last('crit', None, bool, ephem=True)
        nocrit = args.last('nocrit', default=False, type_=bool, ephem=True)
        max_arg = args.last('max', None, bool, ephem=True)
        magic_arg = args.last('magical', None, bool, ephem=True)
        mi_arg = args.last('mi', None, int)
        dtype_args = args.get('dtype', [], ephem=True)
        critdice = args.last('critdice', 0, int)
        hide = args.last('h', type_=bool)

        # character-specific arguments
        if autoctx.character:
            critdice = autoctx.character.get_setting('critdice') or critdice

        # combat-specific arguments
        if not autoctx.target.is_simple:
            resistances = autoctx.target.get_resists().copy()
        resistances.update(Resistances.from_args(args, ephem=True))

        # check if we actually need to run this damage roll (not in combat and roll is redundant)
        if autoctx.target.is_simple and self.is_meta(autoctx, True):
            return

        # add on combatant damage effects (#224)
        if autoctx.combatant:
            d_args.extend(autoctx.combatant.active_effects('d'))

        # check if we actually need to care about the -d tag
        if self.is_meta(autoctx):
            d_args = []  # d was likely applied in the Roll effect already

        # set up damage AST
        damage = autoctx.parse_annostr(damage)
        dice_ast = copy.copy(d20.parse(damage))
        dice_ast = upcast_scaled_dice(self, autoctx, dice_ast)

        # -mi # (#527)
        if mi_arg:
            dice_ast = d20.utils.tree_map(mi_mapper(mi_arg), dice_ast)

        # -d #
        for d_arg in d_args:
            d_ast = d20.parse(d_arg)
            dice_ast.roll = d20.ast.BinOp(dice_ast.roll, '+', d_ast.roll)

        # crit
        # nocrit (#1216)
        in_crit = (autoctx.in_crit or crit_arg) and not nocrit
        roll_for = "Damage" if not in_crit else "Damage (CRIT!)"
        if in_crit:
            dice_ast = d20.utils.tree_map(crit_mapper, dice_ast)
            if critdice and not autoctx.is_spell:
                # add X critdice to the leftmost node if it's dice
                left = d20.utils.leftmost(dice_ast)
                if isinstance(left, d20.ast.Dice):
                    left.num += int(critdice)

        # -c #
        if in_crit:
            for c_arg in c_args:
                c_ast = d20.parse(c_arg)
                dice_ast.roll = d20.ast.BinOp(dice_ast.roll, '+', c_ast.roll)

        # max
        if max_arg:
            dice_ast = d20.utils.tree_map(max_mapper, dice_ast)

        # evaluate damage
        dmgroll = roll(dice_ast)

        # magic arg (#853), magical effect (#1063)
        magical_effect = autoctx.combatant and autoctx.combatant.active_effects('magical')
        always = {'magical'} if (magical_effect or autoctx.is_spell or magic_arg) else None
        # dtype transforms/overrides (#876)
        transforms = {}
        for dtype in dtype_args:
            if '>' in dtype:
                *froms, to = dtype.split('>')
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

        # generate output
        result = d20.MarkdownStringifier().stringify(dmgroll.expr)

        # output
        if not hide:
            autoctx.queue(f"**{roll_for}**: {result}")
        else:
            d20.utils.simplify_expr(dmgroll.expr)
            autoctx.queue(f"**{roll_for}**: {d20.MarkdownStringifier().stringify(dmgroll.expr)}")
            autoctx.add_pm(str(autoctx.ctx.author.id), f"**{roll_for}**: {result}")

        autoctx.target.damage(autoctx, dmgroll.total, allow_overheal=self.overheal)

        # #1335
        autoctx.metavars['lastDamage'] = dmgroll.total
        return DamageResult(damage=dmgroll.total, damage_roll=dmgroll, in_crit=in_crit)

    def is_meta(self, autoctx, strict=False):
        if not strict:
            return any(f"{{{v}}}" in self.damage for v in autoctx.metavars)
        return any(f"{{{v}}}" == self.damage for v in autoctx.metavars)

    def build_str(self, caster, evaluator):
        super(Damage, self).build_str(caster, evaluator)
        try:
            damage = evaluator.transformed_str(self.damage)
            evaluator.builtins['lastDamage'] = damage
        except Exception:
            damage = self.damage
            evaluator.builtins['lastDamage'] = 0
        return f"{damage} damage"


class TempHP(Effect):
    def __init__(self, amount: str, higher: dict = None, cantripScale: bool = None, **kwargs):
        super(TempHP, self).__init__("temphp", **kwargs)
        self.amount = amount
        self.higher = higher
        self.cantripScale = cantripScale

    def to_dict(self):
        out = super(TempHP, self).to_dict()
        out.update({"amount": self.amount})
        if self.higher is not None:
            out['higher'] = self.higher
        if self.cantripScale is not None:
            out['cantripScale'] = self.cantripScale
        return out

    def run(self, autoctx):
        super(TempHP, self).run(autoctx)
        args = autoctx.args
        amount = self.amount
        maxdmg = args.last('max', None, bool, ephem=True)

        # check if we actually need to run this damage roll (not in combat and roll is redundant)
        if autoctx.target.is_simple and self.is_meta(autoctx, True):
            return

        amount = autoctx.parse_annostr(amount)
        dice_ast = copy.copy(d20.parse(amount))
        dice_ast = upcast_scaled_dice(self, autoctx, dice_ast)

        if maxdmg:
            dice_ast = d20.utils.tree_map(max_mapper, dice_ast)

        dmgroll = roll(dice_ast)
        thp_amount = max(dmgroll.total, 0)
        autoctx.queue(f"**THP**: {dmgroll.result}")
        autoctx.metavars['lastTempHp'] = thp_amount  # #1335

        if autoctx.target.combatant:
            autoctx.target.combatant.temp_hp = thp_amount
            autoctx.footer_queue(
                "{}: {}".format(autoctx.target.combatant.name, autoctx.target.combatant.hp_str()))
        elif autoctx.target.character:
            autoctx.target.character.temp_hp = thp_amount
            autoctx.footer_queue(
                "{}: {}".format(autoctx.target.character.name, autoctx.target.character.hp_str()))

        return TempHPResult(amount=thp_amount, amount_roll=dmgroll)

    def is_meta(self, autoctx, strict=False):
        if not strict:
            return any(f"{{{v}}}" in self.amount for v in autoctx.metavars)
        return any(f"{{{v}}}" == self.amount for v in autoctx.metavars)

    def build_str(self, caster, evaluator):
        super(TempHP, self).build_str(caster, evaluator)
        try:
            amount = evaluator.transformed_str(self.amount)
            evaluator.builtins['lastTempHp'] = amount
        except Exception:
            amount = self.amount
            evaluator.builtins['lastTempHp'] = 0
        return f"{amount} temp HP"


class IEffect(Effect):
    def __init__(self, name: str, duration: int, effects: str, end: bool = False, conc: bool = False,
                 desc: str = None, **kwargs):
        super(IEffect, self).__init__("ieffect", **kwargs)
        self.name = name
        self.duration = duration
        self.effects = effects
        self.tick_on_end = end
        self.concentration = conc
        self.desc = desc

    def to_dict(self):
        out = super(IEffect, self).to_dict()
        out.update({"name": self.name, "duration": self.duration, "effects": self.effects, "end": self.tick_on_end,
                    "conc": self.concentration, "desc": self.desc})
        return out

    def run(self, autoctx):
        super(IEffect, self).run(autoctx)
        if isinstance(self.duration, str):
            try:
                duration = autoctx.parse_intexpression(self.duration)
            except Exception:
                raise AutomationException(f"{self.duration} is not an integer (in effect duration)")
        else:
            duration = self.duration

        if self.desc:
            desc = autoctx.parse_annostr(self.desc)
            if len(desc) > 500:
                desc = f"{desc[:500]}..."
        else:
            desc = None

        duration = autoctx.args.last('dur', duration, int)
        conc_conflict = []
        if isinstance(autoctx.target.target, init.Combatant):
            effect = init.Effect.new(autoctx.target.target.combat, autoctx.target.target, self.name,
                                     duration, autoctx.parse_annostr(self.effects), tick_on_end=self.tick_on_end,
                                     concentration=self.concentration, desc=desc)
            if autoctx.conc_effect:
                if autoctx.conc_effect.combatant is autoctx.target.target and self.concentration:
                    raise InvalidArgument("Concentration spells cannot add concentration effects to the caster.")
                effect.set_parent(autoctx.conc_effect)
            effect_result = autoctx.target.target.add_effect(effect)
            autoctx.queue(f"**Effect**: {effect.get_str(description=False)}")
            if conc_conflict := effect_result['conc_conflict']:
                autoctx.queue(f"**Concentration**: dropped {', '.join([e.name for e in conc_conflict])}")
        else:
            effect = init.Effect.new(None, None, self.name, duration, autoctx.parse_annostr(self.effects),
                                     tick_on_end=self.tick_on_end, concentration=self.concentration, desc=desc)
            autoctx.queue(f"**Effect**: {effect.get_str(description=False)}")

        return IEffectResult(effect=effect, conc_conflict=conc_conflict)

    def build_str(self, caster, evaluator):
        super(IEffect, self).build_str(caster, evaluator)
        return self.name


class Roll(Effect):
    def __init__(self, dice: str, name: str, higher: dict = None, cantripScale: bool = None, hidden: bool = False,
                 **kwargs):
        super(Roll, self).__init__("roll", **kwargs)
        self.dice = dice
        self.name = name
        self.higher = higher
        self.cantripScale = cantripScale
        self.hidden = hidden

    def to_dict(self):
        out = super(Roll, self).to_dict()
        out.update({
            "dice": self.dice, "name": self.name, "hidden": self.hidden
        })
        if self.higher is not None:
            out['higher'] = self.higher
        if self.cantripScale is not None:
            out['cantripScale'] = self.cantripScale
        return out

    def run(self, autoctx):
        super(Roll, self).run(autoctx)
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
        dice_ast = upcast_scaled_dice(self, autoctx, dice_ast)

        if not self.hidden:
            # -mi # (#527)
            if mi:
                dice_ast = d20.utils.tree_map(mi_mapper(mi), dice_ast)

            if d:
                d_ast = d20.parse(d)
                dice_ast.roll = d20.ast.BinOp(dice_ast.roll, '+', d_ast.roll)

            if maxdmg:
                dice_ast = d20.utils.tree_map(max_mapper, dice_ast)

        rolled = roll(dice_ast)
        if not self.hidden:
            autoctx.meta_queue(f"**{self.name.title()}**: {rolled.result}")

        simplified_expr = copy.deepcopy(rolled.expr)
        d20.utils.simplify_expr(simplified_expr)
        simplified = RerollableStringifier().stringify(simplified_expr.roll)
        autoctx.metavars[self.name] = simplified
        autoctx.metavars['lastRoll'] = rolled.total  # #1335
        return RollResult(result=rolled.total, roll=rolled, simplified=simplified, hidden=self.hidden)

    def build_str(self, caster, evaluator):
        super(Roll, self).build_str(caster, evaluator)
        evaluator.builtins[self.name] = self.dice
        evaluator.builtins['lastRoll'] = 0
        return ""


class Text(Effect):
    def __init__(self, text: str, **kwargs):
        super(Text, self).__init__("text", **kwargs)
        self.text = text
        self.added = False

    def to_dict(self):
        out = super(Text, self).to_dict()
        out.update({"text": self.text})
        return out

    def run(self, autoctx):
        super(Text, self).run(autoctx)
        hide = autoctx.args.last('h', type_=bool)

        if self.text:
            text = autoctx.parse_annostr(self.text)
            if len(text) > 1020:
                text = f"{text[:1020]}..."
            if not hide:
                autoctx.effect_queue(text)
            else:
                autoctx.add_pm(str(autoctx.ctx.author.id), text)

            return TextResult(text=text)

    def build_str(self, caster, evaluator):
        super(Text, self).build_str(caster, evaluator)
        return ""


class SetVariable(Effect):
    def __init__(self, name: str, value: str, higher: dict = None, onError: str = None, **kwargs):
        super().__init__('variable', **kwargs)
        self.name = name
        self.value = value
        self.higher = higher
        self.on_error = onError

    def to_dict(self):
        out = super().to_dict()
        out.update({"name": self.name, "value": self.value})
        if self.higher is not None:
            out['higher'] = self.higher
        if self.on_error is not None:
            out['onError'] = self.on_error
        return out

    def run(self, autoctx):
        super().run(autoctx)
        level_value = self.value
        # handle upcast
        if autoctx.is_spell and self.higher and autoctx.get_cast_level() != autoctx.spell.level:
            higher = self.higher.get(str(autoctx.get_cast_level()))
            if higher:
                level_value = higher

        did_error = False

        # parse value
        try:
            value = autoctx.parse_annostr(level_value, is_full_expression=True)
        except AutomationEvaluationException as e:
            did_error = True
            if self.on_error is not None:
                value = autoctx.parse_annostr(self.on_error, is_full_expression=True)
            else:
                raise StopExecution(f"Error in SetVariable (`{self.name} = {level_value}`):\n{e}")

        # cast to int
        try:
            final_value = int(value)
        except (TypeError, ValueError):
            raise AutomationException(f"{value} cannot be interpreted as an integer "
                                      f"(in `{self.name} = {level_value}`).")

        # bind
        autoctx.metavars[self.name] = final_value
        return SetVariableResult(value=value, did_error=did_error)

    def build_str(self, caster, evaluator):
        super().build_str(caster, evaluator)
        try:
            value = evaluator.eval(self.value)
        except Exception:
            try:
                value = evaluator.eval(self.on_error)
            except Exception:
                value = self.value
        evaluator.builtins[self.name] = value
        return ""


class Condition(Effect):
    def __init__(self, condition: str, onTrue: list, onFalse: list, errorBehaviour: str = 'false', **kwargs):
        super().__init__('condition', **kwargs)
        self.condition = condition
        self.on_true = onTrue
        self.on_false = onFalse
        self.error_behaviour = errorBehaviour

    @classmethod
    def from_data(cls, data):
        data['onTrue'] = Effect.deserialize(data['onTrue'])
        data['onFalse'] = Effect.deserialize(data['onFalse'])
        return super().from_data(data)

    def to_dict(self):
        out = super().to_dict()
        on_true = Effect.serialize(self.on_true)
        on_false = Effect.serialize(self.on_false)
        out.update({'condition': self.condition, 'onTrue': on_true, 'onFalse': on_false,
                    'errorBehaviour': self.error_behaviour})
        return out

    def run(self, autoctx):
        super().run(autoctx)
        did_error = False
        do_true = False
        do_false = False
        try:
            condition_result = autoctx.parse_annostr(self.condition, is_full_expression=True)
        except AutomationEvaluationException as e:
            did_error = True
            if self.error_behaviour == 'true':
                do_true = True
            elif self.error_behaviour == 'false':
                do_false = True
            elif self.error_behaviour == 'both':
                do_true = True
                do_false = True
            elif self.error_behaviour == 'neither':
                pass
            else:  # raise
                raise StopExecution(f"Error when evaluating condition `{self.condition}`:\n{e}")
        else:
            if condition_result:
                do_true = True
            else:
                do_false = True

        children = []
        if do_true:
            children += self.run_children(self.on_true, autoctx)
        if do_false:
            children += self.run_children(self.on_false, autoctx)

        return ConditionResult(did_true=do_true, did_false=do_false, did_error=did_error, children=children)

    def build_str(self, caster, evaluator):
        super().build_str(caster, evaluator)

        on_true = self.build_child_str(self.on_true, caster, evaluator)
        on_false = self.build_child_str(self.on_false, caster, evaluator)

        # neither: do nothing
        if not (on_true or on_false):
            return ""

        # one: return "maybe X".
        elif on_true and not on_false:
            return f"maybe {on_true}"
        elif on_false and not on_true:
            return f"maybe {on_false}"

        # both: return "X or Y".
        else:
            return f"{on_true} or {on_false}"

    @property
    def children(self):
        return super().children + self.on_false + self.on_true


class UseCounter(Effect):
    def __init__(self, counter, amount: str, allowOverflow: bool = False, errorBehaviour: str = 'warn', **kwargs):
        """
        :type counter: str or SpellSlotReference or FeatureReference
        """
        super().__init__('counter', **kwargs)
        self.counter = counter
        self.amount = amount
        self.allow_overflow = allowOverflow
        self.error_behaviour = errorBehaviour

    @classmethod
    def from_data(cls, data):
        if not isinstance(data['counter'], str):
            data['counter'] = deserialize_usecounter_target(data['counter'])
        return super().from_data(data)

    def to_dict(self):
        out = super().to_dict()
        counter = self.counter if isinstance(self.counter, str) else self.counter.to_dict()
        out.update({
            'counter': counter,
            'amount': self.amount,
            'allowOverflow': self.allow_overflow,
            'errorBehaviour': self.error_behaviour
        })
        return out

    def run(self, autoctx):
        super().run(autoctx)

        # set to default values in case of error
        autoctx.metavars['lastCounterName'] = None
        autoctx.metavars['lastCounterRemaining'] = 0
        autoctx.metavars['lastCounterUsedAmount'] = 0

        # handle -amt, -l, -i
        amt = autoctx.args.last('amt', None, int, ephem=True)
        i = autoctx.args.last('i')
        # -l handled in use_spell_slot

        if i:
            return UseCounterResult(skipped=True)  # skipped

        try:
            amount = amt or autoctx.parse_intexpression(self.amount)
        except Exception:
            raise AutomationException(f"{self.amount!r} cannot be interpreted as an amount (in Use Counter)")

        try:
            if isinstance(self.counter, SpellSlotReference):  # spell slot
                result = self.use_spell_slot(autoctx, amount)
            else:
                result = self.get_and_use_counter(autoctx, amount)
            autoctx.caster_needs_commit = True
        except Exception as e:
            result = UseCounterResult(skipped=True)
            if self.error_behaviour == 'warn':
                autoctx.meta_queue(f"**Warning**: Could not use counter - {e}")
            elif self.error_behaviour == 'raise':
                raise StopExecution(f"Could not use counter: {e}")

        autoctx.metavars['lastCounterName'] = result.counter_name
        autoctx.metavars['lastCounterRemaining'] = result.counter_remaining
        autoctx.metavars['lastCounterUsedAmount'] = result.used_amount
        return result

    def get_and_use_counter(self, autoctx, amount):  # this is not in run() because indentation
        if autoctx.character is None:
            raise NoCounterFound("The caster does not have custom counters.")

        if isinstance(self.counter, FeatureReference):
            raise NoCounterFound("This feature is not yet implemented")  # todo
        else:  # str - get counter by match
            counter = autoctx.character.get_consumable(self.counter)
            if counter is None:
                raise NoCounterFound(f"No counter with the name {self.counter!r} was found.")

        return self.use_custom_counter(autoctx, counter, amount)

    def use_spell_slot(self, autoctx, amount):
        level = autoctx.args.last('l', self.counter.slot, int)

        old_value = autoctx.caster.spellbook.get_slots(level)
        target_value = new_value = old_value - amount

        # if allow overflow is on, clip to bounds
        if self.allow_overflow:
            new_value = max(min(target_value, autoctx.caster.spellbook.get_max_slots(level)), 0)

        # use the slot(s) and output
        autoctx.caster.spellbook.set_slots(level, new_value)
        delta = new_value - old_value
        overflow = abs(new_value - target_value)
        slots_str = autoctx.caster.spellbook.slots_str(level)

        # queue resource usage in own field
        overflow_str = f"\n({overflow} overflow)" if overflow else ""
        autoctx.postflight_queue_field(name="Spell Slots", value=f"{slots_str} ({delta:+}){overflow_str}")

        return UseCounterResult(counter_name=str(level),
                                counter_remaining=new_value,
                                used_amount=old_value - new_value)

    def use_custom_counter(self, autoctx, counter, amount):
        old_value = counter.value
        target_value = old_value - amount

        # use the charges and output
        final_value = counter.set(target_value, strict=not self.allow_overflow)
        delta = final_value - old_value
        overflow = abs(final_value - target_value)

        # queue resource usage in own field
        overflow_str = f"\n({overflow} overflow)" if overflow else ""
        autoctx.postflight_queue_field(name=counter.name, value=f"{str(counter)} ({delta:+}){overflow_str}")

        return UseCounterResult(counter_name=counter.name,
                                counter_remaining=final_value,
                                used_amount=-delta)

    def build_str(self, caster, evaluator):
        super().build_str(caster, evaluator)
        # amount
        try:
            amount = int(evaluator.eval(self.amount))
        except Exception:
            amount = float('nan')
        charges = 'charge' if amount == 1 else 'charges'

        # counter name
        if isinstance(self.counter, str):
            counter_name = f"{charges} of {self.counter}"
        else:
            counter_name = self.counter.build_str(plural=amount != 1)
        return f"uses {amount} {counter_name}"


EFFECT_MAP = {
    "target": Target,
    "attack": Attack,
    "save": Save,
    "damage": Damage,
    "temphp": TempHP,
    "ieffect": IEffect,
    "roll": Roll,
    "text": Text,
    "variable": SetVariable,
    "condition": Condition,
    "counter": UseCounter,
}
