import copy
import logging

import d20
from d20 import roll

import aliasing.evaluators
import cogs5e.models.character as character_api
import cogs5e.models.initiative as init
from aliasing.errors import EvaluationError
from cogs5e.models import embeds
from cogs5e.models.errors import AvraeException, InvalidArgument, InvalidSaveType
from cogs5e.models.sheet.resistance import Resistances, do_resistances
from utils.dice import RerollableStringifier
from utils.functions import maybe_mod

log = logging.getLogger(__name__)


class Automation:
    def __init__(self, effects: list):
        self.effects = effects

    @classmethod
    def from_data(cls, data: list):
        if data is not None:
            effects = Effect.deserialize(data)
            return cls(effects)
        return None

    def to_dict(self):
        return [e.to_dict() for e in self.effects]

    async def run(self, ctx, embed, caster, targets, args, combat=None, spell=None, conc_effect=None, ab_override=None,
                  dc_override=None, spell_override=None, title=None, before=None, after=None):
        """
        Runs automation.

        :param ctx: The discord context the automation is being run in.
        :type ctx: discord.ext.commands.Context
        :param embed: The embed to add automation fields to.
        :type embed: discord.Embed
        :param caster: The StatBlock casting this automation.
        :type caster: cogs5e.models.sheet.statblock.StatBlock
        :param targets: A list of str or StatBlock or None hit by this automation.
        :type targets: list of str or list of cogs5e.models.sheet.statblock.StatBlock
        :param args: ParsedArguments.
        :type args: utils.argparser.ParsedArguments
        :param combat: The combat this automation is being run in.
        :type combat: cogs5e.models.initiative.Combat
        :param spell: The spell being cast that is running this automation.
        :type spell: cogs5e.models.spell.Spell
        :param conc_effect: The initiative effect that is used to track concentration caused by running this.
        :type conc_effect: cogs5e.models.initiative.Effect
        :param ab_override: Forces a default attack bonus.
        :type ab_override: int
        :param dc_override: Forces a default DC.
        :type dc_override: int
        :param spell_override: Forces a default spell modifier.
        :type spell_override: int
        :param title: The title of the action.
        :type title: str
        :param before: A function, taking in the AutomationContext, to run before automation runs.
        :type before: function
        :param after: A function, taking in the AutomationContext, to run after automation runs.
        :type after: function
        """
        if not targets:
            targets = [None]  # outputs a single iteration of effects in a generic meta field
        autoctx = AutomationContext(ctx, embed, caster, targets, args, combat, spell, conc_effect, ab_override,
                                    dc_override, spell_override)

        if before is not None:
            before(autoctx)

        for effect in self.effects:
            effect.run(autoctx)

        if after is not None:
            after(autoctx)

        autoctx.build_embed()
        for user, msgs in autoctx.pm_queue.items():
            try:
                user = ctx.guild.get_member(int(user))
                if title:
                    await user.send(f"{title}\n" + '\n'.join(msgs))
                else:
                    await user.send('\n'.join(msgs))
            except:
                pass

    def build_str(self, caster):
        """
        :type caster: :class:`~cogs5e.models.sheet.statblock.StatBlock
        """
        evaluator = aliasing.evaluators.SpellEvaluator.with_caster(caster)
        return f"{Effect.build_child_str(self.effects, caster, evaluator)}."

    def __str__(self):
        return f"Automation ({len(self.effects)} effects)"


class AutomationContext:
    def __init__(self, ctx, embed, caster, targets, args, combat, spell=None, conc_effect=None, ab_override=None,
                 dc_override=None, spell_override=None):
        self.ctx = ctx
        self.embed = embed
        self.caster = caster
        self.targets = targets
        self.args = args
        self.combat = combat

        self.spell = spell
        self.is_spell = spell is not None
        self.conc_effect = conc_effect
        self.ab_override = ab_override
        self.dc_override = dc_override

        self.metavars = {}
        self.target = None
        self.in_crit = False

        self._embed_queue = []
        self._meta_queue = []
        self._effect_queue = []
        self._field_queue = []
        self._footer_queue = []
        self.pm_queue = {}

        self.character = None
        if isinstance(caster, init.PlayerCombatant):
            self.character = caster.character
        elif isinstance(caster, character_api.Character):
            self.character = caster

        self.evaluator = aliasing.evaluators.SpellEvaluator.with_caster(caster, spell_override=spell_override)

        self.combatant = None
        if isinstance(caster, init.Combatant):
            self.combatant = caster

    def queue(self, text):
        self._embed_queue.append(text)

    def meta_queue(self, text):
        if text not in self._meta_queue:
            self._meta_queue.append(text)

    def footer_queue(self, text):
        self._footer_queue.append(text)

    def effect_queue(self, text):
        if text not in self._effect_queue:
            self._effect_queue.append(text)

    def push_embed_field(self, title, inline=False, to_meta=False):
        if not self._embed_queue:
            return
        if to_meta:
            self._meta_queue.extend(self._embed_queue)
        else:
            chunks = embeds.get_long_field_args('\n'.join(self._embed_queue), title)
            self._field_queue.extend(chunks)
        self._embed_queue = []

    def insert_meta_field(self):
        if not self._meta_queue:
            return
        self._field_queue.insert(0, {"name": "Meta", "value": '\n'.join(self._meta_queue), "inline": False})
        self._meta_queue = []

    def build_embed(self):
        # description
        phrase = self.args.join('phrase', '\n')
        if phrase:
            self.embed.description = f"*{phrase}*"

        # add fields
        self._meta_queue.extend(t for t in self._embed_queue if t not in self._meta_queue)
        self.insert_meta_field()
        for field in self._field_queue:
            self.embed.add_field(**field)
        for effect in self._effect_queue:
            self.embed.add_field(name="Effect", value=effect, inline=False)
        self.embed.set_footer(text='\n'.join(self._footer_queue))

    def add_pm(self, user, message):
        if user not in self.pm_queue:
            self.pm_queue[user] = []
        self.pm_queue[user].append(message)

    def get_cast_level(self):
        if self.is_spell:
            return self.args.last('l', self.spell.level, int)
        return 0

    def parse_annostr(self, annostr, is_full_expression=False):
        if not is_full_expression:
            return self.evaluator.transformed_str(annostr, extra_names=self.metavars)

        original_names = self.evaluator.builtins.copy()
        self.evaluator.builtins.update(self.metavars)
        expr = annostr.strip('{}')
        try:
            out = self.evaluator.eval(expr)
        except Exception as ex:
            raise AutomationEvaluationException(ex, expr)
        self.evaluator.builtins = original_names
        return out


class AutomationTarget:
    def __init__(self, target):
        #: :type: :class:`~cogs5e.models.sheet.statblock.StatBlock`
        self.target = target
        self.is_simple = isinstance(target, str) or target is None

    @property
    def name(self):
        if isinstance(self.target, str):
            return self.target
        return self.target.name

    @property
    def ac(self):
        return self.target.ac

    def get_save_dice(self, save, adv=None):
        sb = None
        save_obj = self.target.saves.get(save)

        # combatant
        if isinstance(self.target, init.Combatant):
            sb = self.target.active_effects('sb')

        saveroll = save_obj.d20(base_adv=adv)

        if sb:
            saveroll = f"{saveroll}+{'+'.join(sb)}"

        return saveroll

    def get_resists(self):
        return self.target.resistances

    def damage(self, autoctx, amount, allow_overheal=True):
        if not self.is_simple:
            result = self.target.modify_hp(-amount, overflow=allow_overheal)
            autoctx.footer_queue(f"{self.target.name}: {result}")

            if isinstance(self.target, init.Combatant):
                if self.target.is_private:
                    autoctx.add_pm(self.target.controller, f"{self.target.name}'s HP: {self.target.hp_str(True)}")

                if self.target.is_concentrating() and amount > 0:
                    autoctx.queue(f"**Concentration**: DC {int(max(amount / 2, 10))}")

    @property
    def combatant(self):
        if isinstance(self.target, init.Combatant):
            return self.target
        return None

    @property
    def character(self):
        if isinstance(self.target, init.PlayerCombatant):
            return self.target.character
        elif isinstance(self.target, character_api.Character):
            return self.target
        return None


class Effect:
    def __init__(self, type_, meta=None, **_):  # ignore bad kwargs
        self.type = type_
        if meta:
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
    def run_children_with_damage(child, autoctx):
        damage = 0
        for effect in child:
            try:
                result = effect.run(autoctx)
                if result and 'total' in result:
                    damage += result['total']
            except StopExecution:
                raise
            except AutomationException as e:
                autoctx.meta_queue(f"**Error**: {e}")
        return damage

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

        if self.target in ('all', 'each'):
            for target in autoctx.targets:
                autoctx.target = AutomationTarget(target)
                self.run_effects(autoctx)
        elif self.target == 'self':
            autoctx.target = AutomationTarget(autoctx.caster)
            self.run_effects(autoctx)
        else:
            try:
                autoctx.target = AutomationTarget(autoctx.targets[self.target - 1])
            except IndexError:
                return
            self.run_effects(autoctx)
        autoctx.target = None

    def run_effects(self, autoctx):
        args = autoctx.args
        args.set_context(autoctx.target.target)
        rr = min(args.last('rr', 1, int), 25)

        total_damage = 0
        in_target = autoctx.target.target is not None

        # 2 binary attributes: (rr?, target?)
        # each case must end with a push_embed_field()
        if rr > 1:
            for iteration in range(rr):
                if len(self.effects) == 1:
                    iter_title = f"{type(self.effects[0]).__name__} {iteration + 1}"
                else:
                    iter_title = f"Iteration {iteration + 1}"

                # target, rr
                if in_target:
                    autoctx.queue(f"\n**__{iter_title}__**")

                total_damage += self.run_children_with_damage(self.effects, autoctx)

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
            total_damage += self.run_children_with_damage(self.effects, autoctx)
            if in_target:  # target, no rr
                autoctx.push_embed_field(autoctx.target.name)
            else:  # no target, no rr
                autoctx.push_embed_field(None, to_meta=True)

    def build_str(self, caster, evaluator):
        super(Target, self).build_str(caster, evaluator)
        return self.build_child_str(self.effects, caster, evaluator)


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
            explicit_bonus = autoctx.parse_annostr(self.bonus, is_full_expression=True)
            try:
                attack_bonus = int(explicit_bonus)
            except (TypeError, ValueError):
                raise AutomationException(f"{explicit_bonus} cannot be interpreted as an attack bonus.")

        if attack_bonus is None and b is None:
            raise NoAttackBonus("No spell attack bonus found. Use the `-b` argument to specify one!")

        # tracking
        damage = 0

        # roll attack against autoctx.target
        if not (hit or miss):
            formatted_d20 = '1d20'
            if adv == 1:
                formatted_d20 = '2d20kh1'
            elif adv == 2:
                formatted_d20 = '3d20kh1'
            elif adv == -1:
                formatted_d20 = '2d20kl1'

            if reroll:
                formatted_d20 = f"{formatted_d20}ro{reroll}"

            to_hit_message = 'To Hit'
            if ac:
                to_hit_message = f'To Hit (AC {ac})'

            if b:
                to_hit_roll = roll(f"{formatted_d20}+{attack_bonus}+{b}")
            else:
                to_hit_roll = roll(f"{formatted_d20}+{attack_bonus}")

            # crit processing
            left = to_hit_roll.expr
            while left.children:
                left = left.children[0]
            d20_value = left.total

            if d20_value >= criton:
                itercrit = 1
            else:
                itercrit = to_hit_roll.crit

            # -ac #
            target_has_ac = not autoctx.target.is_simple and autoctx.target.ac is not None
            if target_has_ac:
                ac = ac or autoctx.target.ac

            if itercrit == 0 and ac:
                if to_hit_roll.total < ac:
                    itercrit = 2  # miss!

            # output
            if not hide:  # not hidden
                autoctx.queue(f"**{to_hit_message}**: {to_hit_roll.result}")
            elif target_has_ac:  # hidden
                if itercrit == 2:
                    hit_type = 'MISS'
                elif itercrit == 1:
                    hit_type = 'CRIT'
                else:
                    hit_type = 'HIT'
                autoctx.queue(f"**To Hit**: {formatted_d20}... = `{hit_type}`")
                autoctx.add_pm(str(autoctx.ctx.author.id), f"**{to_hit_message}**: {to_hit_roll.result}")
            else:  # hidden, no ac
                autoctx.queue(f"**To Hit**: {formatted_d20}... = `{to_hit_roll.total}`")
                autoctx.add_pm(str(autoctx.ctx.author.id), f"**{to_hit_message}**: {to_hit_roll.result}")

            if itercrit == 2:
                damage += self.on_miss(autoctx)
            elif itercrit == 1:
                damage += self.on_crit(autoctx)
            else:
                damage += self.on_hit(autoctx)
        elif hit:
            autoctx.queue(f"**To Hit**: Automatic hit!")
            if crit:
                damage += self.on_crit(autoctx)
            else:
                damage += self.on_hit(autoctx)
        else:
            autoctx.queue(f"**To Hit**: Automatic miss!")
            damage += self.on_miss(autoctx)

        return {"total": damage}

    def on_hit(self, autoctx):
        return self.run_children_with_damage(self.hit, autoctx)

    def on_crit(self, autoctx):
        original = autoctx.in_crit
        autoctx.in_crit = True
        result = self.on_hit(autoctx)
        autoctx.in_crit = original
        return result

    def on_miss(self, autoctx):
        autoctx.queue("**Miss!**")
        return self.run_children_with_damage(self.miss, autoctx)

    def build_str(self, caster, evaluator):
        super(Attack, self).build_str(caster, evaluator)
        attack_bonus = caster.spellbook.sab
        if self.bonus:
            try:
                explicit_bonus = evaluator.eval(self.bonus)
                attack_bonus = int(explicit_bonus)
            except:
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

        dc_override = None
        if self.dc:
            try:
                dc_override = autoctx.parse_annostr(self.dc)
                dc_override = int(dc_override)
            except (TypeError, ValueError):
                raise AutomationException(f"{dc_override} cannot be interpreted as a DC.")

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

        autoctx.meta_queue(f"**DC**: {dc}")
        if not autoctx.target.is_simple:
            save_blurb = f'{save_skill[:3].upper()} Save'
            if auto_pass:
                is_success = True
                autoctx.queue(f"**{save_blurb}:** Automatic success!")
            elif auto_fail:
                is_success = False
                autoctx.queue(f"**{save_blurb}:** Automatic failure!")
            else:
                saveroll = autoctx.target.get_save_dice(save_skill, adv=autoctx.args.adv(boolwise=True))
                save_roll = roll(saveroll)
                is_success = save_roll.total >= dc
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
            damage = self.on_success(autoctx)
        else:
            damage = self.on_fail(autoctx)
        return {"total": damage}

    def on_success(self, autoctx):
        return self.run_children_with_damage(self.success, autoctx)

    def on_fail(self, autoctx):
        return self.run_children_with_damage(self.fail, autoctx)

    def build_str(self, caster, evaluator):
        super(Save, self).build_str(caster, evaluator)
        dc = caster.spellbook.dc
        if self.dc:
            try:
                dc_override = evaluator.transformed_str(self.dc)
                dc = int(dc_override)
            except (TypeError, ValueError):
                dc = 0

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
        dice_ast = _upcast_scaled_dice(self, autoctx, dice_ast)

        # -mi # (#527)
        if mi_arg:
            dice_ast = d20.utils.tree_map(_mi_mapper(mi_arg), dice_ast)

        # -d #
        for d_arg in d_args:
            d_ast = d20.parse(d_arg)
            dice_ast.roll = d20.ast.BinOp(dice_ast.roll, '+', d_ast.roll)

        # crit
        in_crit = autoctx.in_crit or crit_arg
        roll_for = "Damage" if not in_crit else "Damage (CRIT!)"
        if in_crit:
            dice_ast = d20.utils.tree_map(_crit_mapper, dice_ast)
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
            dice_ast = d20.utils.tree_map(_max_mapper, dice_ast)

        # evaluate damage
        dmgroll = roll(dice_ast)

        # magic arg (#853)
        always = {'magical'} if (autoctx.is_spell or magic_arg) else None
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

        # return metadata for scripting
        return {'damage': f"**{roll_for}**: {result}", 'total': dmgroll.total, 'roll': dmgroll}

    def is_meta(self, autoctx, strict=False):
        if not strict:
            return any(f"{{{v}}}" in self.damage for v in autoctx.metavars)
        return any(f"{{{v}}}" == self.damage for v in autoctx.metavars)

    def build_str(self, caster, evaluator):
        super(Damage, self).build_str(caster, evaluator)
        damage = evaluator.transformed_str(self.damage)
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
        dice_ast = _upcast_scaled_dice(self, autoctx, dice_ast)

        if maxdmg:
            dice_ast = d20.utils.tree_map(_max_mapper, dice_ast)

        dmgroll = roll(dice_ast)
        autoctx.queue(f"**THP**: {dmgroll.result}")

        if autoctx.target.combatant:
            autoctx.target.combatant.temp_hp = max(dmgroll.total, 0)
            autoctx.footer_queue(
                "{}: {}".format(autoctx.target.combatant.name, autoctx.target.combatant.hp_str()))
        elif autoctx.target.character:
            autoctx.target.character.temp_hp = max(dmgroll.total, 0)
            autoctx.footer_queue(
                "{}: {}".format(autoctx.target.character.name, autoctx.target.character.hp_str()))

    def is_meta(self, autoctx, strict=False):
        if not strict:
            return any(f"{{{v}}}" in self.amount for v in autoctx.metavars)
        return any(f"{{{v}}}" == self.amount for v in autoctx.metavars)

    def build_str(self, caster, evaluator):
        super(TempHP, self).build_str(caster, evaluator)
        amount = evaluator.transformed_str(self.amount)
        return f"{amount} temp HP"


class IEffect(Effect):
    def __init__(self, name: str, duration: int, effects: str, end: bool = False, conc: bool = False, **kwargs):
        super(IEffect, self).__init__("ieffect", **kwargs)
        self.name = name
        self.duration = duration
        self.effects = effects
        self.tick_on_end = end
        self.concentration = conc

    def to_dict(self):
        out = super(IEffect, self).to_dict()
        out.update({"name": self.name, "duration": self.duration, "effects": self.effects, "end": self.tick_on_end,
                    "conc": self.concentration})
        return out

    def run(self, autoctx):
        super(IEffect, self).run(autoctx)
        if isinstance(self.duration, str):
            try:
                duration = int(autoctx.parse_annostr(self.duration, is_full_expression=True))
            except ValueError:
                raise InvalidArgument(f"{self.duration} is not an integer (in effect duration)")
        else:
            duration = self.duration

        duration = autoctx.args.last('dur', duration, int)
        if isinstance(autoctx.target.target, init.Combatant):
            effect = init.Effect.new(autoctx.target.target.combat, autoctx.target.target, self.name,
                                     duration, autoctx.parse_annostr(self.effects), tick_on_end=self.tick_on_end,
                                     concentration=self.concentration)
            if autoctx.conc_effect:
                if autoctx.conc_effect.combatant is autoctx.target.target and self.concentration:
                    raise InvalidArgument("Concentration spells cannot add concentration effects to the caster.")
                effect.set_parent(autoctx.conc_effect)
            effect_result = autoctx.target.target.add_effect(effect)
            autoctx.queue(f"**Effect**: {str(effect)}")
            if conc_conflict := effect_result['conc_conflict']:
                autoctx.queue(f"**Concentration**: dropped {', '.join([e.name for e in conc_conflict])}")
        else:
            effect = init.Effect.new(None, None, self.name, duration, autoctx.parse_annostr(self.effects),
                                     tick_on_end=self.tick_on_end, concentration=self.concentration)
            autoctx.queue(f"**Effect**: {str(effect)}")

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
        dice_ast = _upcast_scaled_dice(self, autoctx, dice_ast)

        if not self.hidden:
            # -mi # (#527)
            if mi:
                dice_ast = d20.utils.tree_map(_mi_mapper(mi), dice_ast)

            if d:
                d_ast = d20.parse(d)
                dice_ast.roll = d20.ast.BinOp(dice_ast.roll, '+', d_ast.roll)

            if maxdmg:
                dice_ast = d20.utils.tree_map(_max_mapper, dice_ast)

        rolled = roll(dice_ast)
        if not self.hidden:
            autoctx.meta_queue(f"**{self.name.title()}**: {rolled.result}")

        d20.utils.simplify_expr(rolled.expr)
        autoctx.metavars[self.name] = RerollableStringifier().stringify(rolled.expr.roll)

    def build_str(self, caster, evaluator):
        super(Roll, self).build_str(caster, evaluator)
        evaluator.builtins[self.name] = self.dice
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

    def build_str(self, caster, evaluator):
        super(Text, self).build_str(caster, evaluator)
        return ""


EFFECT_MAP = {
    "target": Target,
    "attack": Attack,
    "save": Save,
    "damage": Damage,
    "temphp": TempHP,
    "ieffect": IEffect,
    "roll": Roll,
    "text": Text
}


# ==== helpers ====
def _upcast_scaled_dice(effect, autoctx, dice_ast):
    """Scales the dice of the cast to its appropriate amount (handling cantrip scaling and higher level addition)."""
    if autoctx.is_spell:
        if effect.cantripScale:
            level = autoctx.caster.spellbook.caster_level
            if level < 5:
                level_dice = 1
            elif level < 11:
                level_dice = 2
            elif level < 17:
                level_dice = 3
            else:
                level_dice = 4

            def mapper(node):
                if isinstance(node, d20.ast.Dice):
                    node.num = level_dice
                return node

            dice_ast = d20.utils.tree_map(mapper, dice_ast)

        if effect.higher and not autoctx.get_cast_level() == autoctx.spell.level:
            higher = effect.higher.get(str(autoctx.get_cast_level()))
            if higher:
                higher_ast = d20.parse(higher)
                dice_ast.roll = d20.ast.BinOp(dice_ast.roll, '+', higher_ast.roll)

    return dice_ast


def _mi_mapper(minimum):
    """Returns a function that maps Dice AST objects to OperatedDice with miX attached."""

    def mapper(node):
        if isinstance(node, d20.ast.Dice):
            miX = d20.ast.SetOperator('mi', [d20.ast.SetSelector(None, int(minimum))])
            return d20.ast.OperatedDice(node, miX)
        return node

    return mapper


def _max_mapper(node):
    """A function that maps Dice AST objects to OperatedDice that set their values to their maximum."""
    if isinstance(node, d20.ast.Dice):
        miX = d20.ast.SetOperator('mi', [d20.ast.SetSelector(None, node.size)])
        return d20.ast.OperatedDice(node, miX)
    return node


def _crit_mapper(node):
    """A function that doubles the number of dice for each Dice AST node."""
    if isinstance(node, d20.ast.Dice):
        return d20.ast.Dice(node.num * 2, node.size)
    return node


# ==== exceptions ====
class AutomationException(AvraeException):
    pass


class StopExecution(AutomationException):
    """
    Some check failed that should cause automation to stop, whatever stage of execution it's at.
    This does not revert any side effects made before this point.
    """
    pass


class TargetException(AutomationException):
    pass


class AutomationEvaluationException(EvaluationError, AutomationException):
    """
    An error occurred while evaluating Draconic in automation.
    """

    def __init__(self, original, expression):
        super().__init__(original, expression)  # EvaluationError.__init__()


class NoSpellDC(AutomationException):
    def __init__(self, msg="No spell save DC found."):
        super().__init__(msg)


class NoAttackBonus(AutomationException):
    def __init__(self, msg="No attack bonus found."):
        super().__init__(msg)
