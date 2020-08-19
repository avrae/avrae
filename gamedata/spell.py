import logging
import re

import discord

import cogs5e.models.initiative as init
import gamedata.lookuputils
from cogs5e.models import initiative
from cogs5e.models.automation import Automation
from cogs5e.models.embeds import EmbedWithAuthor, add_fields_from_args
from cogs5e.models.errors import AvraeException
from utils.constants import STAT_ABBREVIATIONS
from utils.functions import trim_str, verbose_stat
from .shared import Sourced

log = logging.getLogger(__name__)


class Spell(Sourced):
    def __init__(self, name: str, level: int, school: str, casttime: str, range_: str, components: str, duration: str,
                 description: str, homebrew: bool, classes=None, subclasses=None, ritual: bool = False,
                 higherlevels: str = None, concentration: bool = False, automation: Automation = None,
                 image: str = None, **kwargs):
        if classes is None:
            classes = []
        if isinstance(classes, str):
            classes = [cls.strip() for cls in classes.split(',') if cls.strip()]
        if subclasses is None:
            subclasses = []
        if isinstance(subclasses, str):
            subclasses = [cls.strip() for cls in subclasses.split(',') if cls.strip()]

        super().__init__('spell', homebrew, **kwargs)

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
        self.concentration = concentration
        self.automation = automation
        self.image = image

        if self.concentration and 'Concentration' not in self.duration:
            self.duration = f"Concentration, up to {self.duration}"

    @classmethod
    def from_data(cls, d):  # local JSON
        automation = Automation.from_data(d["automation"])
        return cls(
            d['name'], d['level'], d['school'], d['casttime'], d['range'], d['components'], d['duration'],
            d['description'],
            homebrew=False, classes=d['classes'], subclasses=d['subclasses'], ritual=d['ritual'],
            higherlevels=d['higherlevels'], concentration=d['concentration'], automation=automation,
            source=d['source'], entity_id=d['id'], page=d['page'], url=d['url'], is_free=d['isFree'])

    @classmethod
    def from_homebrew(cls, data, source):  # homebrew spells
        data['components'] = parse_homebrew_components(data['components'])
        data["range_"] = data.pop("range")
        data["automation"] = Automation.from_data(data["automation"])
        return cls(homebrew=True, source=source, **data)

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
            return "1st-level"
        if self.level == 2:
            return "2nd-level"
        if self.level == 3:
            return "3rd-level"
        return f"{self.level}th-level"

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

    def to_dicecloud(self):
        mat = re.search(r'\(([^()]+)\)', self.components)
        text = self.description.replace('\n', '\n  ')
        if self.higherlevels:
            text += f"\n\n**At Higher Levels**: {self.higherlevels}"
        return {
            'name': self.name,
            'description': text,
            'castingTime': self.time,
            'range': self.range,
            'duration': self.duration,
            'components': {
                'verbal': 'V' in self.components,
                'somatic': 'S' in self.components,
                'concentration': self.concentration,
                'material': mat.group(1) if mat else None,
            },
            'ritual': self.ritual,
            'level': int(self.level),
            'school': self.get_school(),
            'prepared': 'prepared'
        }

    async def cast(self, ctx, caster, targets, args, combat=None):
        """
        Casts this spell.

        :param ctx: The context of the casting.
        :param caster: The caster of this spell.
        :type caster: :class:`~cogs5e.models.sheet.statblock.StatBlock`
        :param targets: A list of targets
        :type targets: list of :class:`~cogs5e.models.sheet.statblock.StatBlock`
        :param args: Args
        :type args: :class:`~utils.argparser.ParsedArguments`
        :param combat: The combat the spell was cast in, if applicable.
        :return: {embed: Embed}
        """

        # generic args
        l = args.last('l', self.level, int)
        i = args.last('i', type_=bool)
        title = args.last('title')

        # meta checks
        if not self.level <= l <= 9:
            raise SpellException("Invalid spell level.")

        # caster spell-specific overrides
        dc_override = None
        ab_override = None
        spell_override = None
        spellbook_spell = caster.spellbook.get_spell(self)
        if spellbook_spell is not None:
            dc_override = spellbook_spell.dc
            ab_override = spellbook_spell.sab
            spell_override = spellbook_spell.mod

        if not i:
            # if I'm a warlock, and I didn't have any slots of this level anyway (#655)
            # automatically scale up to the next level s.t. our slots are not 0
            if l > 0 \
                    and l == self.level \
                    and not caster.spellbook.get_max_slots(l) \
                    and not caster.spellbook.can_cast(self, l):
                l = next((sl for sl in range(l, 6) if caster.spellbook.get_max_slots(sl)), l)  # only scale up to l5
                args['l'] = l

            # can I cast this spell?
            if not caster.spellbook.can_cast(self, l):
                embed = EmbedWithAuthor(ctx)
                embed.title = "Cannot cast spell!"
                if not caster.spellbook.get_slots(l):
                    # out of spell slots
                    err = f"You don't have enough level {l} slots left! Use `-l <level>` to cast at a different level, " \
                          f"`{ctx.prefix}g lr` to take a long rest, or `-i` to ignore spell slots!"
                elif self.name not in caster.spellbook:
                    # don't know spell
                    err = f"You don't know this spell! Use `{ctx.prefix}sb add {self.name}` to add it to your spellbook, " \
                          f"or pass `-i` to ignore restrictions."
                else:
                    # ?
                    err = "Not enough spell slots remaining, or spell not in known spell list!\n" \
                          f"Use `{ctx.prefix}game longrest` to restore all spell slots if this is a character, " \
                          f"or pass `-i` to ignore restrictions."
                embed.description = err
                if l > 0:
                    embed.add_field(name="Spell Slots", value=caster.spellbook.remaining_casts_of(self, l))
                return {"embed": embed}

            # use resource
            caster.spellbook.cast(self, l)

        # base stat stuff
        mod_arg = args.last("mod", type_=int)
        stat_override = ''
        if mod_arg is not None:
            mod = mod_arg
            prof_bonus = caster.stats.prof_bonus
            dc_override = 8 + mod + prof_bonus
            ab_override = mod + prof_bonus
            spell_override = mod
        elif any(args.last(s, type_=bool) for s in STAT_ABBREVIATIONS):
            base = next(s for s in STAT_ABBREVIATIONS if args.last(s, type_=bool))
            mod = caster.stats.get_mod(base)
            dc_override = 8 + mod + caster.stats.prof_bonus
            ab_override = mod + caster.stats.prof_bonus
            spell_override = mod
            stat_override = f" with {verbose_stat(base)}"

        # begin setup
        embed = discord.Embed()
        if title:
            embed.title = title.replace('[sname]', self.name)
        else:
            embed.title = f"{caster.get_title_name()} casts {self.name}{stat_override}!"
        if targets is None:
            targets = [None]

        # concentration
        noconc = args.last("noconc", type_=bool)
        conc_conflict = None
        conc_effect = None
        if all((self.concentration, isinstance(caster, init.Combatant), combat, not noconc)):
            duration = args.last('dur', self.get_combat_duration(), int)
            conc_effect = initiative.Effect.new(combat, caster, self.name, duration, "", True)
            effect_result = caster.add_effect(conc_effect)
            conc_conflict = effect_result['conc_conflict']

        if self.automation and self.automation.effects:
            title = f"{caster.name} cast {self.name}!"
            await self.automation.run(ctx, embed, caster, targets, args, combat, self, conc_effect=conc_effect,
                                      ab_override=ab_override, dc_override=dc_override, spell_override=spell_override,
                                      title=title)
        else:
            phrase = args.join('phrase', '\n')
            if phrase:
                embed.description = f"*{phrase}*"

            text = trim_str(self.description, 1024)
            embed.add_field(name="Description", value=text, inline=False)
            if l != self.level and self.higherlevels:
                embed.add_field(name="At Higher Levels", value=trim_str(self.higherlevels, 1024), inline=False)
            embed.set_footer(text="No spell automation found.")

        if l > 0 and not i:
            embed.add_field(name="Spell Slots", value=caster.spellbook.remaining_casts_of(self, l))

        if conc_conflict:
            conflicts = ', '.join(e.name for e in conc_conflict)
            embed.add_field(name="Concentration",
                            value=f"Dropped {conflicts} due to concentration.")

        if 'thumb' in args:
            embed.set_thumbnail(url=args.last('thumb'))
        elif self.image:
            embed.set_thumbnail(url=self.image)

        add_fields_from_args(embed, args.get('f'))
        gamedata.lookuputils.handle_source_footer(embed, self, add_source_str=False)

        return {"embed": embed}


def parse_homebrew_components(components):
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
