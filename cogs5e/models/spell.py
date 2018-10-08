import discord

from cogs5e.funcs.dice import roll, SingleDiceGroup
from cogs5e.models.embeds import EmbedWithAuthor
from cogs5e.models.errors import AvraeException, NoSpellAB


class Automation:
    def __init__(self, effects: list):
        self.effects = effects

    @classmethod
    def from_data(cls, data: list):
        if data is not None:
            effects = Effect.deserialize(data)
            return cls(effects)
        return None

    def run(self, ctx, embed, caster, targets, args, combat=None):
        autoctx = AutomationContext(ctx, embed, caster, targets, args, combat)
        for effect in self.effects:
            effect.run(autoctx)

        autoctx.build_embed()


class AutomationContext:
    def __init__(self, ctx, embed, caster, targets, args, combat):
        self.ctx = ctx
        self.embed = embed
        self.caster = caster
        self.targets = targets
        self.args = args
        self.combat = combat

        self.metavars = {}
        self.target = None
        self.in_crit = False

        self._embed_queue = []
        self._meta_queue = []
        self._field_queue = []

    def queue(self, text):
        self._embed_queue.append(text)

    def meta_queue(self, text):
        self._meta_queue.append(text)

    def push_embed_field(self, title):
        if not self._embed_queue:
            return
        self._field_queue.append({"name": title, "value": '\n'.join(self._embed_queue)})
        self._embed_queue = []

    def insert_meta_field(self):
        if not self._meta_queue:
            return
        self._field_queue.insert(0, {"name": "Meta", "value": '\n'.join(self._meta_queue)})
        self._meta_queue = []

    def build_embed(self):
        self.push_embed_field("Effect")
        self.insert_meta_field()
        for field in self._field_queue:
            self.embed.add_field(**field)


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


class Effect:
    def __init__(self, type_, meta=None):
        self.type = type_
        self.meta = meta

    @staticmethod
    def deserialize(data):
        return [EFFECT_MAP[e['type']].from_data(e) for e in data]

    @classmethod
    def from_data(cls, data):  # catch-all
        data.pop('type')
        return cls(**data)

    def run(self, autoctx):
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
                autoctx.target = target
                self.run_effects(autoctx)
        elif self.target == 'self':
            autoctx.target = autoctx.caster
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
        autoctx.push_embed_field(autoctx.target.name)


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

    def run(self, autoctx):  # TODO fix the attack framework, future me
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
        ac = autoctx.target.ac

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

                if ac is not None:
                    if toHit.total < ac and itercrit == 0:
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


class Damage(Effect):
    def __init__(self, damage: str, higher: dict = None, cantripScale: bool = None, **kwargs):
        super(Damage, self).__init__("damage", **kwargs)
        self.damage = damage
        self.higher = higher
        self.cantripScale = cantripScale


class IEffect(Effect):
    def __init__(self, name: str, duration: int, effects: str, **kwargs):
        super(IEffect, self).__init__("ieffect", **kwargs)
        self.name = name
        self.duration = duration
        self.effects = effects


class Roll(Effect):
    def __init__(self, dice: str, name: str, higher: dict = None, cantripScale: bool = None, **kwargs):
        super(Roll, self).__init__("roll", **kwargs)
        self.dice = dice
        self.name = name
        self.higher = higher
        self.cantripScale = cantripScale


class Text(Effect):
    def __init__(self, text: str, **kwargs):
        super(Text, self).__init__("text", **kwargs)
        self.text = text


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
                 description: str, classes: list = None, subclasses: list = None, ritual: bool = False,
                 higherlevels: str = None, source: str = "homebrew", page: int = None, concentration: bool = False,
                 automation: Automation = None, srd: bool = False):
        if classes is None:
            classes = []
        if subclasses is None:
            subclasses = []
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

    @classmethod
    def from_data(cls, data):
        data["range_"] = data.pop("range")  # ignore this
        data["automation"] = Automation.from_data(data["automation"])
        return cls(**data)

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

    async def cast(self, ctx, caster, targets, args, combat=None):
        """
        Casts this spell.
        :param ctx: The context of the casting.
        :param caster: The caster of this spell.
        :type caster: cogs5e.models.caster.Spellcaster
        :param targets: A list of targets.
        :param args: Args
        :param combat: The combat the spell was cast in, if applicable.
        :return: {embed: Embed}
        """

        # generic args
        l = args.last('l', self.level, int)
        i = args.last('i', type_=bool)
        phrase = args.join('phrase', '\n')
        # save args
        dc = args.last('dc', type_=int) or caster.spellcasting.dc
        save = args.last('save')
        # attack/save args
        adv = args.adv(True)  # hopefully no one EAs a save spell?
        # damage args
        d = args.join('d', '+')
        resist = args.get('resist')
        immune = args.get('immune')
        vuln = args.get('vuln')
        neutral = args.get('neutral')

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
        if len(targets):
            embed.title = f"{caster.get_name()} casts {self.name} at..."
        else:
            embed.title = f"{caster.get_name()} casts {self.name}!"

        if phrase:
            embed.description = f"*{phrase}*"

        if self.automation:
            self.automation.run(ctx, embed, caster, targets, args, combat)
        else:
            pass  # TODO no automation

        return {"embed": embed}


class SpellException(AvraeException):
    pass
