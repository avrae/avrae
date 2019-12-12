import logging
import re

from cogs5e.funcs.dice import SingleDiceGroup, roll
from cogs5e.funcs.scripting.evaluators import SpellEvaluator
from cogs5e.models import embeds, initiative
from cogs5e.models.character import Character
from cogs5e.models.errors import AvraeException, EvaluationError, InvalidArgument, InvalidSaveType
from cogs5e.models.initiative import Combatant, PlayerCombatant
from utils.functions import parse_resistances

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
                  dc_override=None, spell_override=None, title=None):
        if not targets:
            targets = [None]  # outputs a single iteration of effects in a generic meta field
        autoctx = AutomationContext(ctx, embed, caster, targets, args, combat, spell, conc_effect, ab_override,
                                    dc_override, spell_override)
        for effect in self.effects:
            effect.run(autoctx)

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
        evaluator = SpellEvaluator.with_caster(caster)
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
        if isinstance(caster, PlayerCombatant):
            self.character = caster.character
        elif isinstance(caster, Character):
            self.character = caster

        self.evaluator = SpellEvaluator.with_caster(caster, spell_override=spell_override)

        self.combatant = None
        if isinstance(caster, Combatant):
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
            return self.evaluator.parse(annostr, extra_names=self.metavars)

        original_names = self.evaluator.names.copy()
        self.evaluator.names.update(self.metavars)
        try:
            out = self.evaluator.eval(annostr)
        except Exception as ex:
            raise EvaluationError(ex, annostr)
        self.evaluator.names = original_names
        return out

    def cantrip_scale(self, damage_dice):
        if not self.is_spell:
            return damage_dice

        def scale(matchobj):
            level = self.caster.spellbook.caster_level
            if level < 5:
                levelDice = "1"
            elif level < 11:
                levelDice = "2"
            elif level < 17:
                levelDice = "3"
            else:
                levelDice = "4"
            return levelDice + 'd' + matchobj.group(2)

        return re.sub(r'(\d+)d(\d+)', scale, damage_dice)


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
        if isinstance(self.target, Combatant):
            sb = self.target.active_effects('sb')

        saveroll = save_obj.d20(base_adv=adv)

        if sb:
            saveroll = f"{saveroll}+{'+'.join(sb)}"

        return saveroll

    def get_resists(self):
        return self.target.resistances

    def get_resist(self):
        return self.get_resists().resist

    def get_immune(self):
        return self.get_resists().immune

    def get_vuln(self):
        return self.get_resists().vuln

    def get_neutral(self):
        return self.get_resists().neutral

    def damage(self, autoctx, amount, allow_overheal=True):
        if not self.is_simple:
            result = self.target.modify_hp(-amount, overflow=allow_overheal)
            autoctx.footer_queue(f"{self.target.name}: {result}")

            if isinstance(self.target, Combatant):
                if self.target.is_private:
                    autoctx.add_pm(self.target.controller, f"{self.target.name}'s HP: {self.target.hp_str(True)}")

                if self.target.is_concentrating() and amount > 0:
                    autoctx.queue(f"**Concentration**: DC {int(max(amount / 2, 10))}")

    @property
    def combatant(self):
        if isinstance(self.target, Combatant):
            return self.target
        return None

    @property
    def character(self):
        if isinstance(self.target, PlayerCombatant):
            return self.target.character
        elif isinstance(self.target, Character):
            return self.target
        return None


class Effect:
    def __init__(self, type_, meta=None):
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
            result = effect.run(autoctx)
            if result and 'total' in result:
                damage += result['total']
        return damage

    # required methods
    @classmethod
    def from_data(cls, data):  # catch-all
        data.pop('type')
        return cls(**data)

    def to_dict(self):
        meta = self.meta
        if meta is not None:
            meta = Effect.serialize(meta)
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
        out.update({"hit": hit, "miss": miss, "attackBonus": self.bonus})
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
            reroll = autoctx.character.get_setting('reroll') or reroll
            criton = autoctx.character.get_setting('criton') or criton

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
            raise NoAttackBonus()

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
                toHit = roll(f"{formatted_d20}+{attack_bonus}+{b}", rollFor=to_hit_message, inline=True,
                             show_blurbs=False)
            else:
                toHit = roll(f"{formatted_d20}+{attack_bonus}", rollFor=to_hit_message, inline=True, show_blurbs=False)

            # crit processing
            try:
                d20_value = next(p for p in toHit.raw_dice.parts if
                                 isinstance(p, SingleDiceGroup) and p.max_value == 20).get_total()
            except (StopIteration, AttributeError):
                d20_value = 0

            if d20_value >= criton:
                itercrit = 1
            else:
                itercrit = toHit.crit

            # -ac #
            target_has_ac = not autoctx.target.is_simple and autoctx.target.ac is not None
            if target_has_ac:
                ac = ac or autoctx.target.ac

            if itercrit == 0 and ac:
                if toHit.total < ac:
                    itercrit = 2  # miss!

            # output
            if not hide:  # not hidden
                autoctx.queue(toHit.result)
            elif target_has_ac:  # hidden
                if itercrit == 2:
                    hit_type = 'MISS'
                elif itercrit == 1:
                    hit_type = 'CRIT'
                else:
                    hit_type = 'HIT'
                autoctx.queue(f"**To Hit**: {formatted_d20}... = `{hit_type}`")
                autoctx.add_pm(str(autoctx.ctx.author.id), toHit.result)
            else:  # hidden, no ac
                autoctx.queue(f"**To Hit**: {formatted_d20}... = `{toHit.total}`")
                autoctx.add_pm(str(autoctx.ctx.author.id), toHit.result)

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
        out.update({"stat": self.stat, "fail": fail, "success": success, "dc": self.dc})
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

        dc = autoctx.args.last('dc', type_=int) or dc_override or autoctx.dc_override or autoctx.caster.spellbook.dc

        if dc is None:
            raise NoSpellDC()
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
                save_roll = roll(saveroll, rollFor=save_blurb, inline=True, show_blurbs=False)
                is_success = save_roll.total >= dc
                success_str = ("; Success!" if is_success else "; Failure!")
                if not hide:
                    autoctx.queue(f"{save_roll.result}{success_str}")
                else:
                    autoctx.add_pm(str(autoctx.ctx.author.id), f"{save_roll.result}{success_str}")
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
                dc_override = evaluator.parse(self.dc)
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
            "damage": self.damage, "overheal": self.overheal, "higher": self.higher, "cantripScale": self.cantripScale
        })
        return out

    def run(self, autoctx):
        super(Damage, self).run(autoctx)
        # general arguments
        args = autoctx.args
        damage = self.damage
        d = args.join('d', '+', ephem=True)
        c = args.join('c', '+', ephem=True)
        resist = args.get('resist', [], ephem=True)
        immune = args.get('immune', [], ephem=True)
        vuln = args.get('vuln', [], ephem=True)
        neutral = args.get('neutral', [], ephem=True)
        crit = args.last('crit', None, bool, ephem=True)
        maxdmg = args.last('max', None, bool, ephem=True)
        mi = args.last('mi', None, int)
        critdice = args.last('critdice', 0, int)
        hide = args.last('h', type_=bool)

        # character-specific arguments
        if autoctx.character:
            critdice = autoctx.character.get_setting('critdice') or critdice

        # combat-specific arguments
        if not autoctx.target.is_simple:
            resist = resist or autoctx.target.get_resist()
            immune = immune or autoctx.target.get_immune()
            vuln = vuln or autoctx.target.get_vuln()
            neutral = neutral or autoctx.target.get_neutral()

        # check if we actually need to run this damage roll (not in combat and roll is redundant)
        if autoctx.target.is_simple and self.is_meta(autoctx, True):
            return

        # add on combatant damage effects (#224)
        if autoctx.combatant:
            effect_d = '+'.join(autoctx.combatant.active_effects('d'))
            if effect_d:
                if d:
                    d = f"{d}+{effect_d}"
                else:
                    d = effect_d

        # check if we actually need to care about the -d tag
        if self.is_meta(autoctx):
            d = None  # d was likely applied in the Roll effect already

        damage = autoctx.parse_annostr(damage)

        if autoctx.is_spell:
            if self.cantripScale:
                damage = autoctx.cantrip_scale(damage)

            if self.higher and not autoctx.get_cast_level() == autoctx.spell.level:
                higher = self.higher.get(str(autoctx.get_cast_level()))
                if higher:
                    damage = f"{damage}+{higher}"

        # crit
        in_crit = autoctx.in_crit or crit
        roll_for = "Damage" if not in_crit else "Damage (CRIT!)"

        def parsecrit(damage_dice, wep=False):
            if in_crit:
                def critSub(matchobj):
                    extracritdice = critdice if (critdice and wep) else 0
                    return f"{int(matchobj.group(1)) * 2 + extracritdice}d{matchobj.group(2)}"

                damage_dice = re.sub(r'(\d+)d(\d+)', critSub, damage_dice)
            return damage_dice

        # -mi # (#527)
        if mi:
            damage = re.sub(r'(\d+d\d+)', rf'\1mi{mi}', damage)

        # -d #
        if d:
            damage = parsecrit(damage, wep=not autoctx.is_spell) + '+' + parsecrit(d)
        else:
            damage = parsecrit(damage, wep=not autoctx.is_spell)

        # -c #
        if c and in_crit:
            damage = f"{damage}+{c}"

        # max
        if maxdmg:
            def maxSub(matchobj):
                return f"{matchobj.group(1)}d{matchobj.group(2)}mi{matchobj.group(2)}"

            damage = re.sub(r'(\d+)d(\d+)', maxSub, damage)

        damage = parse_resistances(damage, resist, immune, vuln, neutral)

        dmgroll = roll(damage, rollFor=roll_for, inline=True, show_blurbs=False)

        # output
        if not hide:
            autoctx.queue(dmgroll.result)
        else:
            autoctx.queue(f"**{roll_for}**: {dmgroll.consolidated()} = `{dmgroll.total}`")
            autoctx.add_pm(str(autoctx.ctx.author.id), dmgroll.result)

        autoctx.target.damage(autoctx, dmgroll.total, allow_overheal=self.overheal)

        # return metadata for scripting
        return {'damage': dmgroll.result, 'total': dmgroll.total, 'roll': dmgroll}

    def is_meta(self, autoctx, strict=False):
        if not strict:
            return any(f"{{{v}}}" in self.damage for v in autoctx.metavars)
        return any(f"{{{v}}}" == self.damage for v in autoctx.metavars)

    def build_str(self, caster, evaluator):
        super(Damage, self).build_str(caster, evaluator)
        damage = evaluator.parse(self.damage)
        return f"{damage} damage"


class TempHP(Effect):
    def __init__(self, amount: str, higher: dict = None, cantripScale: bool = None, **kwargs):
        super(TempHP, self).__init__("temphp", **kwargs)
        self.amount = amount
        self.higher = higher
        self.cantripScale = cantripScale

    def to_dict(self):
        out = super(TempHP, self).to_dict()
        out.update({"amount": self.amount, "higher": self.higher, "cantripScale": self.cantripScale})
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

        if autoctx.is_spell:
            if self.cantripScale:
                amount = autoctx.cantrip_scale(amount)

            if self.higher and not autoctx.get_cast_level() == autoctx.spell.level:
                higher = self.higher.get(str(autoctx.get_cast_level()))
                if higher:
                    amount = f"{amount}+{higher}"

        roll_for = "THP"

        if maxdmg:
            def maxSub(matchobj):
                return f"{matchobj.group(1)}d{matchobj.group(2)}mi{matchobj.group(2)}"

            amount = re.sub(r'(\d+)d(\d+)', maxSub, amount)

        dmgroll = roll(amount, rollFor=roll_for, inline=True, show_blurbs=False)
        autoctx.queue(dmgroll.result)

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
        amount = evaluator.parse(self.amount)
        return f"{amount} temp HP"


class IEffect(Effect):
    def __init__(self, name: str, duration: int, effects: str, end: bool = False, **kwargs):
        super(IEffect, self).__init__("ieffect", **kwargs)
        self.name = name
        self.duration = duration
        self.effects = effects
        self.tick_on_end = end

    def to_dict(self):
        out = super(IEffect, self).to_dict()
        out.update({"name": self.name, "duration": self.duration, "effects": self.effects, "end": self.tick_on_end})
        return out

    def run(self, autoctx):
        super(IEffect, self).run(autoctx)
        if isinstance(self.duration, str):
            try:
                duration = int(autoctx.parse_annostr(self.duration))
            except ValueError:
                raise InvalidArgument(f"{self.duration} is not an integer (in effect duration)")
        else:
            duration = self.duration

        duration = autoctx.args.last('dur', duration, int)
        if isinstance(autoctx.target.target, Combatant):
            effect = initiative.Effect.new(autoctx.target.target.combat, autoctx.target.target, self.name,
                                           duration, autoctx.parse_annostr(self.effects), tick_on_end=self.tick_on_end)
            if autoctx.conc_effect:
                effect.set_parent(autoctx.conc_effect)
            autoctx.target.target.add_effect(effect)
        else:
            effect = initiative.Effect.new(None, None, self.name, duration, autoctx.parse_annostr(self.effects),
                                           tick_on_end=self.tick_on_end)
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
            "dice": self.dice, "name": self.name, "higher": self.higher, "cantripScale": self.cantripScale,
            "hidden": self.hidden
        })
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

        dice = self.dice

        if autoctx.is_spell:
            if self.cantripScale:
                dice = autoctx.cantrip_scale(dice)

            if self.higher and not autoctx.get_cast_level() == autoctx.spell.level:
                higher = self.higher.get(str(autoctx.get_cast_level()))
                if higher:
                    dice = f"{dice}+{higher}"

        if not self.hidden:
            # -mi # (#527)
            if mi:
                dice = re.sub(r'(\d+d\d+)', rf'\1mi{mi}', dice)

            if d:
                dice = f"{dice}+{d}"

        if maxdmg:
            def maxSub(matchobj):
                return f"{matchobj.group(1)}d{matchobj.group(2)}mi{matchobj.group(2)}"

            dice = re.sub(r'(\d+)d(\d+)', maxSub, dice)

        rolled = roll(dice, rollFor=self.name.title(), inline=True, show_blurbs=False)
        if not self.hidden:
            autoctx.meta_queue(rolled.result)

        if not rolled.raw_dice:
            raise InvalidArgument(f"Invalid roll in meta roll: {rolled.result}")

        autoctx.metavars[self.name] = rolled.consolidated()

    def build_str(self, caster, evaluator):
        super(Roll, self).build_str(caster, evaluator)
        evaluator.names[self.name] = self.dice
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
            text = self.text
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


class AutomationException(AvraeException):
    pass


class TargetException(AutomationException):
    pass


class NoSpellDC(AutomationException):
    def __init__(self):
        super().__init__("No spell save DC found.")


class NoAttackBonus(AutomationException):
    def __init__(self):
        super().__init__("No attack bonus found.")
