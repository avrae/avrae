import d20

from utils.functions import reconcile_adv
from . import Effect
from ..errors import AutomationException, NoAttackBonus, TargetException
from ..results import AttackResult


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

    def run(self, autoctx):
        super(Attack, self).run(autoctx)
        if autoctx.target is None:
            raise TargetException("Tried to make an attack without a target! Make sure all Attack effects are inside "
                                  "of a Target effect.")

        # ==== arguments ====
        args = autoctx.args
        crit = args.last('crit', None, bool, ephem=True) and 1
        nocrit = args.last('nocrit', default=False, type_=bool, ephem=True)
        hit = args.last('hit', None, bool, ephem=True) and 1
        miss = (args.last('miss', None, bool, ephem=True) and not hit) and 1
        b = args.join('b', '+', ephem=True)
        hide = args.last('h', type_=bool)

        reroll = args.last('reroll', 0, int)
        criton = args.last('criton', 20, int)
        ac = args.last('ac', None, int)

        # ==== caster options ====
        # character-specific arguments
        if autoctx.character:
            if 'reroll' not in args:
                reroll = autoctx.character.get_setting('reroll', 0)
            if 'criton' not in args:
                criton = autoctx.character.get_setting('criton', 20)

        # check for combatant IEffects
        if autoctx.combatant:
            # bonus (#224)
            effect_b = '+'.join(autoctx.combatant.active_effects('b'))
            if effect_b and b:
                b = f"{b}+{effect_b}"
            elif effect_b:
                b = effect_b
            # Combine args/ieffect advantages - adv/dis (#1552)
            adv = reconcile_adv(
                adv=args.last('adv', type_=bool, ephem=True) or autoctx.combatant.active_effects('adv'),
                dis=args.last('dis', type_=bool, ephem=True) or autoctx.combatant.active_effects('dis'),
                ea=args.last('ea', type_=bool, ephem=True) or autoctx.combatant.active_effects('ea')
            )
        else:
            adv = args.adv(ea=True, ephem=True)

        # ==== target options ====
        if autoctx.target.character:
            # 1556
            nocrit = nocrit or autoctx.target.character.get_setting("ignorecrit", False)

        # ==== execution ====
        attack_bonus = autoctx.ab_override or autoctx.caster.spellbook.sab

        # explicit bonus
        if self.bonus:
            try:
                attack_bonus = autoctx.parse_intexpression(self.bonus)
            except Exception:
                raise AutomationException(f"{self.bonus!r} cannot be interpreted as an attack bonus.")

        if attack_bonus is None:
            # if there is no attack bonus specified (i.e. use SAB), and no SAB, use -b arg to specify the to hit bonus
            if b is None:
                raise NoAttackBonus("No spell attack bonus found. Use the `-b` argument to specify one!")
            # #1463
            attack_bonus = b
            b = None

        # reset metavars (#1335)
        autoctx.metavars['lastAttackDidHit'] = False
        autoctx.metavars['lastAttackDidCrit'] = False
        autoctx.metavars['lastAttackRollTotal'] = 0  # 1362
        autoctx.metavars['lastAttackNaturalRoll'] = 0  # 1495
        did_hit = True
        did_crit = False
        to_hit_roll = None

        # Disable critical damage state for children (#1556)
        original = autoctx.in_save
        autoctx.in_save = False

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
                to_hit_roll = d20.roll(f"{formatted_d20}+{attack_bonus}+{b}")
            else:
                to_hit_roll = d20.roll(f"{formatted_d20}+{attack_bonus}")

            # hit/miss/crit processing
            # leftmost roll value - -criton
            d20_value = d20.utils.leftmost(to_hit_roll.expr).total

            # -ac #
            target_has_ac = not autoctx.target.is_simple and autoctx.target.ac is not None
            if target_has_ac:
                ac = ac or autoctx.target.ac

            # assign hit values
            if d20_value >= criton or to_hit_roll.crit == d20.CritType.CRIT:  # natural crit
                did_crit = True if not nocrit else False
            elif to_hit_roll.crit == d20.CritType.FAIL:  # crit fail
                did_hit = False
            elif ac and to_hit_roll.total < ac:  # miss
                did_hit = False
            elif crit and not nocrit:  # if we did hit (#1485), set crit flag if arg passed (#1461)
                did_crit = True
            # else: normal hit

            autoctx.metavars['lastAttackRollTotal'] = to_hit_roll.total  # 1362
            autoctx.metavars['lastAttackNaturalRoll'] = d20_value  # 1495

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
            autoctx.queue("**To Hit**: Automatic hit!")
            # nocrit and crit cancel out
            if crit and not nocrit:
                did_crit = True
                children = self.on_crit(autoctx)
            else:
                children = self.on_hit(autoctx)
        else:
            did_hit = False
            autoctx.queue("**To Hit**: Automatic miss!")
            children = self.on_miss(autoctx)

        autoctx.in_save = original  # Restore proper crit state (#1556)

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
        attack_bonus = caster.spellbook.sab if caster.spellbook.sab is not None else float('nan')
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
