import itertools
import logging

from cogs5e.models.sheet.attack import AttackList
from cogs5e.models.sheet.base import BaseStats, Levels, Saves, Skills
from cogs5e.models.sheet.resistance import Resistances
from cogs5e.models.sheet.spellcasting import Spellbook
from cogs5e.models.sheet.statblock import StatBlock
from utils import config
from utils.constants import SKILL_MAP
from utils.functions import a_or_an, bubble_format
from .shared import Sourced

log = logging.getLogger(__name__)


class Trait:
    def __init__(self, name, desc):
        self.name = name
        self.desc = desc

    def to_dict(self):
        return {'name': self.name, 'desc': self.desc}


class Monster(StatBlock, Sourced):
    def __init__(self, name: str, size: str, race: str, alignment: str, ac: int, armortype: str, hp: int, hitdice: str,
                 speed: str, ability_scores: BaseStats, saves: Saves, skills: Skills, senses: str,
                 display_resists: Resistances, condition_immune: list, languages: list, cr: str, xp: int,
                 # optional
                 traits: list = None, actions: list = None, reactions: list = None, legactions: list = None,
                 la_per_round=3, passiveperc: int = None,
                 # augmented
                 resistances: Resistances = None, attacks: AttackList = None, proper: bool = False,
                 image_url: str = None, spellcasting=None, token_free_fp=None, token_sub_fp=None,
                 # sourcing
                 homebrew=False, **kwargs):
        if traits is None:
            traits = []
        if actions is None:
            actions = []
        if reactions is None:
            reactions = []
        if legactions is None:
            legactions = []
        if attacks is None:
            attacks = AttackList()
        if spellcasting is None:
            spellcasting = MonsterSpellbook()
        if passiveperc is None:
            passiveperc = 10 + skills.perception.value

        # old/new resist handling
        if resistances is None:
            # fall back to old-style resistances (deprecated)
            vuln = kwargs.get('vuln', [])
            resist = kwargs.get('resist', [])
            immune = kwargs.get('immune', [])
            resistances = Resistances.from_dict(dict(vuln=vuln, resist=resist, immune=immune))

        try:
            levels = Levels({"Monster": spellcasting.caster_level or int(cr)})
        except ValueError:
            levels = None

        Sourced.__init__(self, 'monster', homebrew, source=kwargs['source'],
                         entity_id=kwargs.get('entity_id'), page=kwargs.get('page'), url=kwargs.get('url'),
                         is_free=kwargs.get('is_free'))
        StatBlock.__init__(
            self,
            name=name, stats=ability_scores, attacks=attacks, skills=skills, saves=saves, resistances=resistances,
            spellbook=spellcasting, ac=ac, max_hp=hp, levels=levels
        )
        self.size = size
        self.race = race
        self.alignment = alignment
        self.armortype = armortype
        self.hitdice = hitdice
        self.speed = speed
        self.cr = cr
        self.xp = xp
        self.passive = passiveperc
        self.senses = senses
        self.condition_immune = condition_immune
        self.languages = languages
        self.traits = traits
        self.actions = actions
        self.reactions = reactions
        self.legactions = legactions
        self.la_per_round = la_per_round
        self.proper = proper
        self.image_url = image_url
        self.token_free_fp = token_free_fp
        self.token_sub_fp = token_sub_fp
        # resistances including notes, e.g. "Bludgeoning from nonmagical weapons"
        self._displayed_resistances = display_resists or resistances

    @classmethod
    def from_data(cls, d):
        ability_scores = BaseStats.from_dict(d['ability_scores'])
        saves = Saves.from_dict(d['saves'])
        skills = Skills.from_dict(d['skills'])
        display_resists = Resistances.from_dict(d['display_resists'], smart=False)
        traits = [Trait(**t) for t in d['traits']]
        actions = [Trait(**t) for t in d['actions']]
        reactions = [Trait(**t) for t in d['reactions']]
        legactions = [Trait(**t) for t in d['legactions']]
        resistances = Resistances.from_dict(d['resistances'])
        attacks = AttackList.from_dict(d['attacks'])
        if d['spellbook'] is not None:
            spellcasting = MonsterSpellbook.from_dict(d['spellbook'])
        else:
            spellcasting = None
        return cls(d['name'], d['size'], d['race'], d['alignment'], d['ac'], d['armortype'], d['hp'], d['hitdice'],
                   d['speed'], ability_scores, saves, skills, d['senses'], display_resists, d['condition_immune'],
                   d['languages'], d['cr'], d['xp'],
                   traits, actions, reactions, legactions,
                   d['la_per_round'], d['passiveperc'],
                   # augmented
                   resistances, attacks, d['proper'], d['image_url'], spellcasting=spellcasting,
                   token_free_fp=d['token_free'], token_sub_fp=d['token_sub'],
                   # sourcing
                   source=d['source'], entity_id=d['id'], page=d['page'], url=d['url'], is_free=d['isFree'])

    @classmethod
    def from_bestiary(cls, data, source):
        for key in ('traits', 'actions', 'reactions', 'legactions'):
            data[key] = [Trait(**t) for t in data.pop(key)]
        data['spellcasting'] = MonsterSpellbook.from_dict(data.pop('spellbook'))
        data['saves'] = Saves.from_dict(data['saves'])
        data['skills'] = Skills.from_dict(data['skills'])
        data['ability_scores'] = BaseStats.from_dict(data['ability_scores'])
        data['attacks'] = AttackList.from_dict(data['attacks'])
        if 'resistances' in data:
            data['resistances'] = Resistances.from_dict(data['resistances'])
        if 'display_resists' in data:
            data['display_resists'] = Resistances.from_dict(data['display_resists'], smart=False)
        else:
            data['display_resists'] = Resistances()
        if 'source' in data:
            del data['source']
        return cls(homebrew=True, source=source, **data)

    def to_dict(self):
        return {
            'name': self.name, 'size': self.size, 'race': self.race, 'alignment': self.alignment, 'ac': self.ac,
            'armortype': self.armortype, 'hp': self.hp, 'hitdice': self.hitdice, 'speed': self.speed,
            'ability_scores': self.stats.to_dict(),
            'cr': self.cr, 'xp': self.xp, 'passiveperc': self.passive, 'senses': self.senses,
            'resistances': self.resistances.to_dict(),
            'condition_immune': self.condition_immune,
            'saves': self.saves.to_dict(), 'skills': self.skills.to_dict(), 'languages': self.languages,
            'traits': [t.to_dict() for t in self.traits], 'actions': [t.to_dict() for t in self.actions],
            'reactions': [t.to_dict() for t in self.reactions],
            'legactions': [t.to_dict() for t in self.legactions], 'la_per_round': self.la_per_round,
            'attacks': self.attacks.to_dict(), 'proper': self.proper,
            'image_url': self.image_url, 'spellbook': self.spellbook.to_dict(),
            'display_resists': self._displayed_resistances.to_dict()
        }

    def get_stat_array(self):
        """
        Returns a string describing the monster's 6 core stats, with modifiers.
        """
        return str(self.stats)

    def get_hidden_stat_array(self):
        stats = ["Unknown", "Unknown", "Unknown", "Unknown", "Unknown", "Unknown"]
        for i, stat in enumerate(
                (self.stats.strength, self.stats.dexterity, self.stats.constitution,
                 self.stats.intelligence, self.stats.wisdom, self.stats.charisma)):
            if stat <= 3:
                stats[i] = "Very Low"
            elif 3 < stat <= 7:
                stats[i] = "Low"
            elif 7 < stat <= 15:
                stats[i] = "Medium"
            elif 15 < stat <= 21:
                stats[i] = "High"
            elif 21 < stat <= 25:
                stats[i] = "Very High"
            elif 25 < stat:
                stats[i] = "Ludicrous"
        return f"**STR**: {stats[0]} **DEX**: {stats[1]} **CON**: {stats[2]}\n" \
               f"**INT**: {stats[3]} **WIS**: {stats[4]} **CHA**: {stats[5]}"

    def get_senses_str(self):
        if self.senses:
            return f"{self.senses}, passive Perception {self.passive}"
        else:
            return f"passive Perception {self.passive}"

    def get_meta(self):
        """
        Returns a string describing the meta statistics of a monster.
        Should be the portion between the embed title and special abilities.
        """
        size = self.size
        type_ = self.race
        alignment = self.alignment
        ac = str(self.ac) + (f" ({self.armortype})" if self.armortype else "")
        hp = f"{self.hp} ({self.hitdice})"
        speed = self.speed

        desc = f"{size} {type_}. {alignment}.\n**AC:** {ac}.\n**HP:** {hp}.\n**Speed:** {speed}\n"
        desc += f"{self.get_stat_array()}\n"

        if str(self.saves):
            desc += f"**Saving Throws:** {self.saves}\n"
        if str(self.skills):
            desc += f"**Skills:** {self.skills}\n"
        desc += f"**Senses:** {self.get_senses_str()}.\n"
        if self._displayed_resistances.vuln:
            desc += f"**Vulnerabilities:** {', '.join(str(r) for r in self._displayed_resistances.vuln)}\n"
        if self._displayed_resistances.resist:
            desc += f"**Resistances:** {', '.join(str(r) for r in self._displayed_resistances.resist)}\n"
        if self._displayed_resistances.immune:
            desc += f"**Damage Immunities:** {', '.join(str(r) for r in self._displayed_resistances.immune)}\n"
        if self.condition_immune:
            desc += f"**Condition Immunities:** {', '.join(map(str, self.condition_immune))}\n"
        if self.languages:
            desc += f"**Languages:** {', '.join(self.languages)}\n"
        else:
            desc += "**Languages:** --\n"
        desc += f"**CR:** {self.cr} ({self.xp} XP)"
        return desc

    def get_title_name(self):
        """Returns a monster's name for use in embed titles."""
        return a_or_an(self.name, upper=True) if not self.proper else self.name

    def get_image_url(self):
        """Returns a monster's image URL."""
        return self.image_url or ''

    def get_token_url(self, is_sub=False):
        """Returns a monster's token URL."""
        if not self.token_free_fp:
            return None
        if is_sub:
            return f"{config.MONSTER_TOKEN_ENDPOINT}/{self.token_sub_fp}"
        return f"{config.MONSTER_TOKEN_ENDPOINT}/{self.token_free_fp}"

    # ---- setter overrides ----
    @property
    def hp(self):
        return super().hp

    @hp.setter
    def hp(self, value):
        pass

    @property
    def temp_hp(self):
        return super().temp_hp

    @temp_hp.setter
    def temp_hp(self, value):
        pass


def parse_type(_type):
    if isinstance(_type, dict):
        if 'tags' in _type:
            tags = []
            for tag in _type['tags']:
                if isinstance(tag, str):
                    tags.append(tag)
                else:
                    tags.append(f"{tag['prefix']} {tag['tag']}")
            return f"{_type['type']} ({', '.join(tags)})"
        elif 'swarmSize' in _type:
            return f"swarm of {parsesize(_type['swarmSize'])} {_type['type']}"
    return str(_type)


def parse_alignment(alignment):
    aligndict = {'U': 'unaligned', 'L': 'lawful', 'N': 'neutral', 'C': 'chaotic', 'G': 'good', 'E': 'evil',
                 'A': 'any alignment', 'NX': 'neutral', 'NY': 'neutral'}
    out = []
    for a in alignment:
        if not isinstance(a, dict):
            out.append(aligndict.get(a))
        elif 'chance' in a:
            out.append(f"{a['chance']}% chance to be {parse_alignment(a['alignment'])}")
        elif 'special' in a:
            out.append(a['special'])
    return ' '.join(out)


def parse_speed(speed):
    out = []
    for movetype, movespeed in speed.items():
        if isinstance(movespeed, dict):
            movespeed = f"{movespeed['number']}{movespeed['condition']}"
        if not movetype == 'walk':
            out.append(f"{movetype} {movespeed} ft.")
        else:
            out.append(f"{movespeed} ft.")
    return ', '.join(out)


def parse_resists(resists, notated=True):
    out = []
    if not resists:
        return out
    for dmgtype in resists:
        if isinstance(dmgtype, str):
            out.append(dmgtype)
        elif isinstance(dmgtype, dict):
            if 'special' in dmgtype:
                out.append(dmgtype['special'])
            else:
                rs = parse_resists(dmgtype.get('resist') or dmgtype.get('immune') or dmgtype.get('vulnerable'))
                if notated:
                    out.append(f"{', '.join(rs)} {dmgtype.get('note')}")
                else:
                    out.extend(rs)
    return out


def parsesize(size):
    s = {"T": "Tiny", "S": "Small", "M": "Medium", "L": "Large", "H": "Huge", "G": "Gargantuan"}
    return s.get(size, "Unknown")


def xp_by_cr(cr):
    return {'0': 10, '1/8': 25, '1/4': 50, '1/2': 100, '1': 200, '2': 450, '3': 700, '4': 1100, '5': 1800, '6': 2300,
            '7': 2900, '8': 3900, '9': 5000, '10': 5900, '11': 7200, '12': 8400, '13': 10000, '14': 11500, '15': 13000,
            '16': 15000, '17': 18000, '18': 20000, '19': 22000, '20': 25000, '21': 33000, '22': 41000, '23': 50000,
            '24': 62000, '25': 75000, '26': 90000, '27': 105000, '28': 120000, '29': 135000, '30': 155000}.get(cr, 0)


def _calc_prof(stats, saves, skills):
    """HACK: Calculates proficiency bonus from save/skill proficiencies."""
    prof = None
    for skill_name, skill in itertools.chain(saves, skills):
        if skill.prof == 1:
            prof = skill.value - stats.get_mod(SKILL_MAP[skill_name])
            break

    if prof is not None:
        return prof
    return 0


# ===== spellcasting =====
class MonsterSpellbook(Spellbook):
    def __init__(self, *args, at_will=None, daily=None, daily_max=None, **kwargs):
        """
        :param at_will: The list of spells the monster can cast at will. These spells should be in the spells list.
        :type at_will: list[str]
        :param daily: A dict of spells -> x the monster can cast x/day. These spells should be in the spells list.
        :type daily: dict[str, int]
        """
        super().__init__(*args, **kwargs)
        if daily is None:
            daily = {}
        if at_will is None:
            at_will = []
        self.at_will = at_will
        self.daily = daily
        self.daily_max = daily_max or daily.copy()  # only monsters can have daily, and we'll init their max to immutable daily

    def to_dict(self):
        d = super().to_dict()
        d.update({
            "at_will": self.at_will,
            "daily": self.daily,
            "daily_max": self.daily_max
        })
        return d

    # ===== utils =====
    def slots_str(self, level: int = None):
        if level is not None:
            return super().slots_str(level)

        slots = super().slots_str(level)
        before = []
        if self.at_will:
            before.append(f"**At Will**: {', '.join(self.at_will)}")
        for spell, remaining in self.daily.items():
            before.append(f"**{spell}**: {bubble_format(remaining, self.daily_max[spell])}")
        before = '\n'.join(before)
        return f"{before}\n{slots}".strip()

    def remaining_casts_of(self, spell, level):
        if spell.name in self.at_will:
            return f"**{spell.name}**: At Will"
        elif spell.name in self.daily:
            return f"**{spell.name}**: {bubble_format(self.daily[spell.name], self.daily_max[spell.name])}"
        return super().remaining_casts_of(spell, level)

    def cast(self, spell, level):
        return  # monster singletons should not have mutable slots

    def can_cast(self, spell, level) -> bool:
        # slot
        has_slot = self.get_slots(level) > 0

        # at will
        is_at_will = spell.name.lower() in [s.lower() for s in self.at_will]

        # daily
        daily_key = next((k for k in self.daily if spell.name.lower() == k.lower()), None)
        is_daily = daily_key is not None and self.daily[daily_key] > 0

        # check
        return spell.name in self and (has_slot or is_daily or is_at_will)


class MonsterCastableSpellbook(MonsterSpellbook):
    @classmethod
    def copy(cls, other: Spellbook):
        """Makes a copy of a MonsterSpellbook (for adding to init)."""
        new = other.to_dict()
        if 'daily' in new:
            new['daily'] = new['daily'].copy()
        new['slots'] = new['slots'].copy()
        return cls.from_dict(new)

    def cast(self, spell, level):
        if spell.name.lower() in [s.lower() for s in self.at_will]:
            return
        elif (daily_key := next((k for k in self.daily if spell.name.lower() == k.lower()), None)) is not None:
            self.daily[daily_key] -= 1
        else:
            self.use_slot(level)
