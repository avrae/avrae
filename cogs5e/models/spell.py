import logging
import re

import discord

from cogs5e.funcs.dice import roll, SingleDiceGroup
from cogs5e.models import initiative
from cogs5e.models.character import Character
from cogs5e.models.embeds import EmbedWithAuthor, add_homebrew_footer
from cogs5e.models.errors import AvraeException, NoSpellAB, NoSpellDC, InvalidSaveType
from cogs5e.models.initiative import Combatant
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

    async def run(self, ctx, embed, caster, targets, args, combat=None, spell=None):
        autoctx = AutomationContext(ctx, embed, caster, targets, args, combat, spell)
        for effect in self.effects:
            effect.run(autoctx)

        autoctx.build_embed()
        for user, msgs in autoctx.pm_queue.items():
            try:
                await ctx.bot.send_message(ctx.message.server.get_member(user),
                                           f"{autoctx.caster.name} cast {autoctx.spell.name}!\n" + '\n'.join(msgs))
            except:
                pass


class AutomationContext:
    ANNOSTR_RE = re.compile(r"{(\w+)}")
    ANNOSTR_RE_NO_SPELL = re.compile(r"(?!{spell}){(\w+)}")

    def __init__(self, ctx, embed, caster, targets, args, combat, spell):
        self.ctx = ctx
        self.embed = embed
        self.caster = caster
        self.targets = targets
        self.args = args
        self.combat = combat
        self.spell = spell

        self.metavars = {
            "spell": caster.spellcasting.sab - caster.pb_from_level()  # for healing spells
        }
        self.target = None
        self.in_crit = False

        self._embed_queue = []
        self._meta_queue = []
        self._effect_queue = []
        self._field_queue = []
        self._footer_queue = []
        self.pm_queue = {}

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
            self._field_queue.append({"name": title, "value": '\n'.join(self._embed_queue), "inline": inline})
        self._embed_queue = []

    def insert_meta_field(self):
        if not self._meta_queue:
            return
        self._field_queue.insert(0, {"name": "Meta", "value": '\n'.join(self._meta_queue)})
        self._meta_queue = []

    def build_embed(self):
        self._meta_queue.extend(t for t in self._embed_queue if t not in self._meta_queue)
        self.insert_meta_field()
        for field in self._field_queue:
            self.embed.add_field(**field)
        for effect in self._effect_queue:
            self.embed.add_field(name="Effect", value=effect)
        self.embed.set_footer(text='\n'.join(self._footer_queue))

    def add_pm(self, user, message):
        if user not in self.pm_queue:
            self.pm_queue[user] = []
        self.pm_queue[user].append(message)

    def get_cast_level(self):
        return self.args.last('l', self.spell.level, int)

    def parse_annostr(self, annostr):
        def metasub(match):
            return str(self.metavars.get(match.group(1), match.group(0)))

        return self.ANNOSTR_RE.sub(metasub, annostr)


class AutomationTarget:
    def __init__(self, target):
        self.target = target

    @property
    def name(self):
        if isinstance(self.target, str):
            return self.target
        return self.target.get_name()

    @property
    def ac(self):
        if hasattr(self.target, "ac"):
            return self.target.ac
        return None

    def get_save(self, save, default=0):
        if hasattr(self.target, "saves"):
            return self.target.saves.get(save, default)
        raise TargetException("Target does not have defined saves.")

    def get_resists(self):
        if hasattr(self.target, "resists"):
            return self.target.resists
        return {}

    def get_resist(self):
        return self.get_resists().get("resist", [])

    def get_immune(self):
        return self.get_resists().get("immune", [])

    def get_vuln(self):
        return self.get_resists().get("vuln", [])

    def get_neutral(self):
        return self.get_resists().get("neutral", [])

    def damage(self, autoctx, amount):
        if isinstance(self.target, Combatant):
            if self.target.hp is not None:
                self.target.mod_hp(-amount, overheal=False)
                autoctx.footer_queue("{}: {}".format(self.target.name, self.target.get_hp_str()))
                if self.target.isPrivate:
                    autoctx.add_pm(self.target.controller, f"{self.target.name}'s HP: {self.target.get_hp_str(True)}")
            else:
                autoctx.footer_queue("Dealt {} damage to {}!".format(amount, self.target.name))
            if self.target.is_concentrating() and amount > 0:
                autoctx.queue(f"**Concentration**: DC {int(max(amount/2, 10))}")
        elif isinstance(self.target, Character):
            self.target.modify_hp(-amount)


class Effect:
    def __init__(self, type_, meta=None):
        self.type = type_
        if meta:
            meta = Effect.deserialize(meta)
        self.meta = meta

    @staticmethod
    def deserialize(data):
        return [EFFECT_MAP[e['type']].from_data(e) for e in data]

    @classmethod
    def from_data(cls, data):  # catch-all
        data.pop('type')
        return cls(**data)

    def run(self, autoctx):
        log.debug(f"Running {self.type}")
        if self.meta:
            for metaeffect in self.meta:
                metaeffect.run(autoctx)


class Target(Effect):
    def __init__(self, target, effects: list, **kwargs):
        super(Target, self).__init__("target", **kwargs)
        self.target = target
        self.effects = effects

    @classmethod
    def from_data(cls, data):
        data['effects'] = Effect.deserialize(data['effects'])
        return super(Target, cls).from_data(data)

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
        for e in self.effects:
            e.run(autoctx)
        if autoctx.target.target:
            autoctx.push_embed_field(autoctx.target.name)
        else:
            autoctx.push_embed_field(None, to_meta=True)


class Attack(Effect):
    def __init__(self, hit: list, miss: list, **kwargs):
        super(Attack, self).__init__("attack", **kwargs)
        self.hit = hit
        self.miss = miss

    @classmethod
    def from_data(cls, data):
        data['hit'] = Effect.deserialize(data['hit'])
        data['miss'] = Effect.deserialize(data['miss'])
        return super(Attack, cls).from_data(data)

    def run(self, autoctx):
        super(Attack, self).run(autoctx)
        args = autoctx.args
        adv = args.adv(True)
        crit = args.last('crit', None, bool) and 1
        hit = args.last('hit', None, bool) and 1
        miss = (args.last('miss', None, bool) and not hit) and 1
        rr = min(args.last('rr', 1, int), 25)
        b = args.join('b', '+')

        reroll = args.last('reroll', 0, int)
        criton = args.last('criton', 20, int)

        sab = autoctx.caster.spellcasting.sab

        if not sab:
            raise NoSpellAB()

        # roll attack(s) against autoctx.target
        for iteration in range(rr):
            if rr > 1:
                autoctx.queue(f"**Attack {iteration + 1}**")

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

                if b:
                    toHit = roll(f"{formatted_d20}+{sab}+{b}", rollFor='To Hit', inline=True, show_blurbs=False)
                else:
                    toHit = roll(f"{formatted_d20}+{sab}", rollFor='To Hit', inline=True, show_blurbs=False)

                autoctx.queue(toHit.result)

                # crit processing
                try:
                    d20_value = next(p for p in toHit.raw_dice.parts if
                                     isinstance(p, SingleDiceGroup) and p.max_value == 20).get_total()
                except StopIteration:
                    d20_value = 0

                if d20_value >= criton:
                    itercrit = 1
                else:
                    itercrit = toHit.crit

                if autoctx.target.target and autoctx.target.ac is not None:
                    if toHit.total < autoctx.target.ac and itercrit == 0:
                        itercrit = 2  # miss!

                if itercrit == 2:
                    self.on_miss(autoctx)
                elif itercrit == 1:
                    self.on_crit(autoctx)
                else:
                    self.on_hit(autoctx)
            elif hit:
                autoctx.queue(f"**To Hit**: Automatic hit!")
                if crit:
                    self.on_crit(autoctx)
                else:
                    self.on_hit(autoctx)
            else:
                autoctx.queue(f"**To Hit**: Automatic miss!")
                self.on_miss(autoctx)

    def on_hit(self, autoctx):
        for effect in self.hit:
            effect.run(autoctx)

    def on_crit(self, autoctx):
        original = autoctx.in_crit
        autoctx.in_crit = True
        self.on_hit(autoctx)
        autoctx.in_crit = original

    def on_miss(self, autoctx):
        autoctx.queue("**Miss!**")
        for effect in self.miss:
            effect.run(autoctx)


class Save(Effect):
    def __init__(self, stat: str, fail: list, success: list, **kwargs):
        super(Save, self).__init__("save", **kwargs)
        self.stat = stat
        self.fail = fail
        self.success = success

    @classmethod
    def from_data(cls, data):
        data['fail'] = Effect.deserialize(data['fail'])
        data['success'] = Effect.deserialize(data['success'])
        return super(Save, cls).from_data(data)

    def run(self, autoctx):
        super(Save, self).run(autoctx)
        dc = autoctx.args.last('dc', type_=int) or autoctx.caster.spellcasting.dc
        save = autoctx.args.last('save') or self.stat
        adv = autoctx.args.adv(False)

        if not dc:
            raise NoSpellDC()
        try:
            save_skill = next(s for s in ('strengthSave', 'dexteritySave', 'constitutionSave',
                                          'intelligenceSave', 'wisdomSave', 'charismaSave') if
                              save.lower() in s.lower())
        except StopIteration:
            raise InvalidSaveType()

        autoctx.meta_queue(f"**DC**: {dc}")
        if autoctx.target.target:
            target_save_mod = autoctx.target.get_save(save_skill)
            save_roll = roll('1d20{:+}'.format(target_save_mod), adv=adv,
                             rollFor='{} Save'.format(save_skill[:3].upper()), inline=True, show_blurbs=False)
            is_success = save_roll.total >= dc
            autoctx.queue(save_roll.result + ("; Success!" if is_success else "; Failure!"))
        else:
            autoctx.meta_queue('{} Save'.format(save_skill[:3].upper()))
            is_success = False

        if is_success:
            self.on_success(autoctx)
        else:
            self.on_fail(autoctx)

    def on_success(self, autoctx):
        for effect in self.success:
            effect.run(autoctx)

    def on_fail(self, autoctx):
        for effect in self.fail:
            effect.run(autoctx)


class Damage(Effect):
    def __init__(self, damage: str, higher: dict = None, cantripScale: bool = None, **kwargs):
        super(Damage, self).__init__("damage", **kwargs)
        self.damage = damage
        self.higher = higher
        self.cantripScale = cantripScale

    def run(self, autoctx):
        super(Damage, self).run(autoctx)
        args = autoctx.args
        damage = self.damage
        d = args.join('d', '+')
        c = args.join('c', '+')
        resist = args.get('resist', [])
        immune = args.get('immune', [])
        vuln = args.get('vuln', [])
        neutral = args.get('neutral', [])
        crit = args.last('crit', None, bool)
        maxdmg = args.last('max', None, bool)
        if autoctx.target.target:
            resist = resist or autoctx.target.get_resist()
            immune = immune or autoctx.target.get_immune()
            vuln = vuln or autoctx.target.get_vuln()
            neutral = neutral or autoctx.target.get_neutral()

        if not autoctx.target.target and autoctx.ANNOSTR_RE_NO_SPELL.match(
                damage):  # likely have output this in meta already
            return
        if autoctx.ANNOSTR_RE_NO_SPELL.search(damage):
            d = None  # d was likely applied in the Roll effect already
        damage = autoctx.parse_annostr(damage)

        if self.cantripScale:
            def cantrip_scale(matchobj):
                level = autoctx.caster.spellcasting.casterLevel
                if level < 5:
                    levelDice = "1"
                elif level < 11:
                    levelDice = "2"
                elif level < 17:
                    levelDice = "3"
                else:
                    levelDice = "4"
                return levelDice + 'd' + matchobj.group(2)

            damage = re.sub(r'(\d+)d(\d+)', cantrip_scale, damage)

        if self.higher and not autoctx.get_cast_level() == autoctx.spell.level:
            higher = self.higher.get(str(autoctx.get_cast_level()))
            if higher:
                damage = f"{damage}+{higher}"

        if d:
            damage = f"{damage}+{d}"

        if autoctx.in_crit or crit:
            def critSub(matchobj):
                return f"{int(matchobj.group(1)) * 2}d{matchobj.group(2)}"

            damage = re.sub(r'(\d+)d(\d+)', critSub, damage)
            if c:
                damage = f"{damage}+{c}"

        if maxdmg:
            def maxSub(matchobj):
                return f"{matchobj.group(1)}d{matchobj.group(2)}mi{matchobj.group(2)}"

            damage = re.sub(r'(\d+)d(\d+)', maxSub, damage)

        damage = parse_resistances(damage, resist, immune, vuln, neutral)

        dmgroll = roll(damage, rollFor="Damage", inline=True, show_blurbs=False)
        autoctx.queue(dmgroll.result)

        autoctx.target.damage(autoctx, dmgroll.total)


class IEffect(Effect):
    def __init__(self, name: str, duration: int, effects: str, **kwargs):
        super(IEffect, self).__init__("ieffect", **kwargs)
        self.name = name
        self.duration = duration
        self.effects = effects

    def run(self, autoctx):
        super(IEffect, self).run(autoctx)
        effect = initiative.Effect.new(self.name, self.duration, autoctx.parse_annostr(self.effects))
        if isinstance(autoctx.target.target, Combatant):
            if isinstance(self.duration, str):
                try:
                    self.duration = int(autoctx.parse_annostr(self.duration))
                except ValueError:
                    raise SpellException(f"{self.duration} is not an integer (in effect duration)")
            autoctx.target.target.add_effect(effect)
        autoctx.queue(f"**Effect**: {str(effect)}")


class Roll(Effect):
    def __init__(self, dice: str, name: str, higher: dict = None, cantripScale: bool = None, **kwargs):
        super(Roll, self).__init__("roll", **kwargs)
        self.dice = dice
        self.name = name
        self.higher = higher
        self.cantripScale = cantripScale

    def run(self, autoctx):
        super(Roll, self).run(autoctx)
        d = autoctx.args.join('d', '+')
        maxdmg = autoctx.args.last('max', None, bool)
        dice = self.dice
        if self.cantripScale:
            def cantrip_scale(matchobj):
                level = autoctx.caster.spellcasting.casterLevel
                if level < 5:
                    levelDice = "1"
                elif level < 11:
                    levelDice = "2"
                elif level < 17:
                    levelDice = "3"
                else:
                    levelDice = "4"
                return levelDice + 'd' + matchobj.group(2)

            dice = re.sub(r'(\d+)d(\d+)', cantrip_scale, dice)

        if self.higher and not autoctx.get_cast_level() == autoctx.spell.level:
            higher = self.higher.get(str(autoctx.get_cast_level()))
            if higher:
                dice = f"{dice}+{higher}"
        if d:
            dice = f"{dice}+{d}"

        if maxdmg:
            def maxSub(matchobj):
                return f"{matchobj.group(1)}d{matchobj.group(2)}mi{matchobj.group(2)}"

            dice = re.sub(r'(\d+)d(\d+)', maxSub, dice)

        rolled = roll(dice, rollFor=self.name.title(), inline=True, show_blurbs=False)
        autoctx.meta_queue(rolled.result)

        formatted_rolled = ""
        for p in rolled.raw_dice.parts:
            if isinstance(p, SingleDiceGroup):
                formatted_rolled += "{} {}".format(p.get_total(), p.annotation)
            else:
                formatted_rolled += str(p)
        autoctx.metavars[self.name] = formatted_rolled


class Text(Effect):
    def __init__(self, text: str, **kwargs):
        super(Text, self).__init__("text", **kwargs)
        self.text = text
        self.added = False

    def run(self, autoctx):
        if self.text:
            text = self.text
            if len(text) > 1020:
                text = f"{text[:1020]}..."
            autoctx.effect_queue(text)


EFFECT_MAP = {
    "target": Target,
    "attack": Attack,
    "save": Save,
    "damage": Damage,
    "ieffect": IEffect,
    "roll": Roll,
    "text": Text
}


class Spell:
    def __init__(self, name: str, level: int, school: str, casttime: str, range_: str, components: str, duration: str,
                 description: str, classes=None, subclasses=None, ritual: bool = False, higherlevels: str = None,
                 source: str = "homebrew", page: int = None, concentration: bool = False, automation: Automation = None,
                 srd: bool = False, image: str = None):
        if classes is None:
            classes = []
        if isinstance(classes, str):
            classes = [cls.strip() for cls in classes.split(',') if cls.strip()]
        if subclasses is None:
            subclasses = []
        if isinstance(subclasses, str):
            subclasses = [cls.strip() for cls in subclasses.split(',') if cls.strip()]
        self.name = name
        self.level = level
        self.school = school
        self.classes = classes
        self.subclasses = subclasses
        self.time = casttime
        self.range = range_
        self.components = components
        self.duration = duration
        self.ritual = ritual
        self.description = description
        self.higherlevels = higherlevels
        self.source = source
        self.page = page
        self.concentration = concentration
        self.automation = automation
        self.srd = srd
        self.image = image

    @classmethod
    def from_data(cls, data):  # local JSON
        data["range_"] = data.pop("range")  # ignore this
        data["automation"] = Automation.from_data(data["automation"])
        return cls(**data)

    @classmethod
    def from_dict(cls, raw):  # homebrew spells
        raw['components'] = parse_components(raw['components'])
        return cls.from_data(raw)

    # def to_dict(self):
    #     return {"name": self.name, "level": self.level, "school": self.school, "classes": self.classes,
    #             "subclasses": self.subclasses, "time": self.time, "range": self.range,
    #             "components": serialize_components(self.components), "duration": self.duration, "ritual": self.ritual,
    #             "description": self.description, "higherlevels": self.higherlevels, "source": self.source,
    #             "page": self.page, "concentration": self.concentration, "automation": self.automation, "srd": self.srd}

    def get_school(self):
        return {
            "A": "Abjuration",
            "V": "Evocation",
            "E": "Enchantment",
            "I": "Illusion",
            "D": "Divination",
            "N": "Necromancy",
            "T": "Transmutation",
            "C": "Conjuration"
        }.get(self.school, self.school)

    def get_level(self):
        if self.level == 0:
            return "cantrip"
        if self.level == 1:
            return "1st level"
        if self.level == 2:
            return "2nd level"
        if self.level == 3:
            return "3rd level"
        return f"{self.level}th level"

    def get_combat_duration(self):
        match = re.match(r"(?:Concentration, up to )?(\d+) (\w+)", self.duration)
        if match:
            num = int(match.group(1))
            unit = match.group(2)
            if 'round' in unit:
                return num
            elif 'minute' in unit:
                if num == 1:  # anything over 1 minute can be indefinite, really
                    return 10
        return -1

    async def cast(self, ctx, caster, targets, args, combat=None):
        """
        Casts this spell.
        :param ctx: The context of the casting.
        :param caster: The caster of this spell.
        :type caster: cogs5e.models.caster.Spellcaster
        :param targets: A list of targets (Combatants)
        :param args: Args
        :param combat: The combat the spell was cast in, if applicable.
        :return: {embed: Embed}
        """

        # generic args
        l = args.last('l', self.level, int)
        i = args.last('i', type_=bool)
        phrase = args.join('phrase', '\n')

        # meta checks
        if not self.level <= l <= 9:
            raise SpellException("Invalid spell level.")

        if not (caster.can_cast(self, l) or i):
            embed = EmbedWithAuthor(ctx)
            embed.title = "Cannot cast spell!"
            embed.description = "Not enough spell slots remaining, or spell not in known spell list!\n" \
                                "Use `!game longrest` to restore all spell slots if this is a character, " \
                                "or pass `-i` to ignore restrictions."
            if l > 0:
                embed.add_field(name="Spell Slots", value=caster.remaining_casts_of(self, l))
            return {"embed": embed}

        if not i:
            caster.cast(self, l)

        # begin setup
        embed = discord.Embed()
        if targets:
            embed.title = f"{caster.get_name()} casts {self.name} at..."
        else:
            embed.title = f"{caster.get_name()} casts {self.name}!"
            if targets is None:
                targets = [None]

        if phrase:
            embed.description = f"*{phrase}*"

        if self.automation and self.automation.effects:
            await self.automation.run(ctx, embed, caster, targets, args, combat, self)
        else:
            text = self.description
            if len(text) > 1020:
                text = f"{text[:1020]}..."
            embed.add_field(name="Description", value=text)
            if l != self.level and self.higherlevels:
                embed.add_field(name="At Higher Levels", value=self.higherlevels)
            embed.set_footer(text="No spell automation found.")

        if l > 0:
            embed.add_field(name="Spell Slots", value=caster.remaining_casts_of(self, l))

        if self.image:
            embed.set_thumbnail(url=self.image)

        if self.source == 'homebrew':
            add_homebrew_footer(embed)

        return {"embed": embed}


def parse_components(components):
    v = components.get('verbal')
    s = components.get('somatic')
    m = components.get('material')
    if isinstance(m, bool):
        parsedm = "M"
    else:
        parsedm = f"M ({m})"

    comps = []
    if v:
        comps.append("V")
    if s:
        comps.append("S")
    if m:
        comps.append(parsedm)
    return ', '.join(comps)


class SpellException(AvraeException):
    pass


class TargetException(SpellException):
    pass
