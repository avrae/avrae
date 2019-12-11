import itertools
import logging
import re
from math import floor
from urllib import parse

import html2text

from cogs5e.models import errors
from cogs5e.models.sheet.attack import AttackList
from cogs5e.models.sheet.base import BaseStats, Levels, Resistances, Saves, Skills
from cogs5e.models.sheet.spellcasting import Spellbook, SpellbookSpell
from cogs5e.models.sheet.statblock import StatBlock
from utils.constants import SKILL_MAP
from utils.functions import a_or_an, bubble_format

AVRAE_ATTACK_OVERRIDES_RE = re.compile(r'<avrae hidden>(.*?)\|([+-]?\d*)\|(.*?)</avrae>', re.IGNORECASE)
ATTACK_RE = re.compile(r'(?:<i>)?(?:\w+ ){1,4}Attack:(?:</i>)? ([+-]?\d+) to hit, .*?(?:<i>)?'
                       r'Hit:(?:</i>)? [+-]?\d+ \((.+?)\) (\w+) damage[., ]??'
                       r'(?:in melee, or [+-]?\d+ \((.+?)\) (\w+) damage at range[,.]?)?'
                       r'(?: or [+-]?\d+ \((.+?)\) (\w+) damage .*?[.,]?)?'
                       r'(?: (?:plus|and) [+-]?\d+ \((.+?)\) (\w+) damage.)?', re.IGNORECASE)
JUST_DAMAGE_RE = re.compile(r'[+-]?\d+ \((.+?)\) (\w+) damage', re.IGNORECASE)

log = logging.getLogger(__name__)


class Trait:
    def __init__(self, name, desc):
        self.name = name
        self.desc = desc

    def to_dict(self):
        return {'name': self.name, 'desc': self.desc}


class Monster(StatBlock):
    def __init__(self, name: str, size: str, race: str, alignment: str, ac: int, armortype: str, hp: int, hitdice: str,
                 speed: str, ability_scores: BaseStats, cr: str, xp: int, passiveperc: int = None,
                 senses: str = '', vuln: list = None, resist: list = None, immune: list = None,
                 condition_immune: list = None, saves: Saves = None, skills: Skills = None, languages: list = None,
                 traits: list = None, actions: list = None, reactions: list = None, legactions: list = None,
                 la_per_round=3, srd=True, source='homebrew', attacks: AttackList = None, proper: bool = False,
                 image_url: str = None, spellcasting=None, page=None, display_resists: Resistances = None, **_):
        if vuln is None:
            vuln = []
        if resist is None:
            resist = []
        if immune is None:
            immune = []
        if condition_immune is None:
            condition_immune = []
        if saves is None:
            saves = Saves.default(ability_scores)
        if skills is None:
            skills = Skills.default(ability_scores)
        if languages is None:
            languages = []
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
            spellcasting = Spellbook({}, {}, [])
        if passiveperc is None:
            passiveperc = 10 + skills.perception.value

        try:
            levels = Levels({"Monster": spellcasting.caster_level or int(cr)})
        except ValueError:
            levels = None

        resistances = Resistances(vuln=vuln, resist=resist, immune=immune)

        super(Monster, self).__init__(
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
        self.srd = srd
        self.source = source
        self.proper = proper
        self.image_url = image_url
        self.page = page  # this should really be by source, but oh well
        # resistances including notes, e.g. "Bludgeoning from nonmagical weapons"
        self._displayed_resistances = display_resists or resistances

    @classmethod
    def from_data(cls, data):
        # print(f"Parsing {data['name']}")
        _type = parse_type(data['type'])
        alignment = parse_alignment(data['alignment'])
        speed = parse_speed(data['speed'])
        ac = data['ac']['ac']
        armortype = data['ac'].get('armortype') or None
        if not 'special' in data['hp']:
            hp = data['hp']['average']
            hitdice = data['hp']['formula']
        else:
            hp = 0
            hitdice = data['hp']['special']
        scores = BaseStats(0, data['str'] or 10, data['dex'] or 10, data['con'] or 10, data['int'] or 10,
                           data['wis'] or 10, data['cha'] or 10)
        if isinstance(data['cr'], dict):
            cr = data['cr']['cr']
        else:
            cr = data['cr']

        # resistances
        vuln = parse_resists(data['vulnerable'], notated=False) if 'vulnerable' in data else None
        resist = parse_resists(data['resist'], notated=False) if 'resist' in data else None
        immune = parse_resists(data['immune'], notated=False) if 'immune' in data else None

        display_resists = Resistances(*[parse_resists(data.get(r)) for r in ('resist', 'immune', 'vulnerable')])

        condition_immune = data.get('conditionImmune', []) if 'conditionImmune' in data else None

        languages = data.get('languages', '').split(', ') if 'languages' in data else None

        traits = [Trait(t['name'], t['text']) for t in data.get('trait', [])]
        actions = [Trait(t['name'], t['text']) for t in data.get('action', [])]
        legactions = [Trait(t['name'], t['text']) for t in data.get('legendary', [])]
        reactions = [Trait(t['name'], t['text']) for t in data.get('reaction', [])]

        skills = Skills.default(scores)
        skills.update(data['skill'])

        saves = Saves.default(scores)
        saves.update(data['save'])

        scores.prof_bonus = _calc_prof(scores, saves, skills)

        source = data['source']
        proper = bool(data.get('proper'))

        attacks = AttackList.from_dict(data.get('attacks', []))
        if 'spellbook' in data:
            spellbook = MonsterSpellbook.from_dict(data['spellbook'])
        else:
            spellbook = None

        return cls(data['name'], parsesize(data['size']), _type, alignment, ac, armortype, hp, hitdice,
                   speed, scores, cr, xp_by_cr(cr), data['passive'], data.get('senses', ''),
                   vuln, resist, immune, condition_immune, saves, skills, languages, traits,
                   actions, reactions, legactions, 3, data.get('srd', False), source, attacks,
                   spellcasting=spellbook, page=data.get('page'), proper=proper, display_resists=display_resists)

    @classmethod
    def from_critterdb(cls, data):
        ability_scores = BaseStats(data['stats']['proficiencyBonus'] or 0,
                                   data['stats']['abilityScores']['strength'] or 10,
                                   data['stats']['abilityScores']['dexterity'] or 10,
                                   data['stats']['abilityScores']['constitution'] or 10,
                                   data['stats']['abilityScores']['intelligence'] or 10,
                                   data['stats']['abilityScores']['wisdom'] or 10,
                                   data['stats']['abilityScores']['charisma'] or 10)
        cr = {0.125: '1/8', 0.25: '1/4', 0.5: '1/2'}.get(data['stats']['challengeRating'],
                                                         str(data['stats']['challengeRating']))
        num_hit_die = data['stats']['numHitDie']
        hit_die_size = data['stats']['hitDieSize']
        con_by_level = num_hit_die * ability_scores.get_mod('con')
        hp = floor(((hit_die_size + 1) / 2) * num_hit_die) + con_by_level
        hitdice = f"{num_hit_die}d{hit_die_size} + {con_by_level}"

        proficiency = data['stats']['proficiencyBonus']
        if proficiency is None:
            raise errors.ExternalImportError(f"Monster's proficiency bonus is nonexistent ({data['name']}).")

        skills = Skills.default(ability_scores)
        skill_updates = {}
        for skill in data['stats']['skills']:
            name = spaced_to_camel(skill['name'])
            if skill['proficient']:
                mod = skills[name].value + proficiency
            else:
                mod = skill.get('value')
            if mod is not None:
                skill_updates[name] = mod
        skills.update(skill_updates)

        saves = Saves.default(ability_scores)
        save_updates = {}
        for save in data['stats']['savingThrows']:
            name = save['ability'].lower() + 'Save'
            if save['proficient']:
                mod = saves.get(name).value + proficiency
            else:
                mod = save.get('value')
            if mod is not None:
                save_updates[name] = mod
        saves.update(save_updates)

        attacks = []
        traits, atks = parse_critterdb_traits(data, 'additionalAbilities')
        attacks.extend(atks)
        actions, atks = parse_critterdb_traits(data, 'actions')
        attacks.extend(atks)
        reactions, atks = parse_critterdb_traits(data, 'reactions')
        attacks.extend(atks)
        legactions, atks = parse_critterdb_traits(data, 'legendaryActions')
        attacks.extend(atks)

        attacks = AttackList.from_dict(attacks)
        spellcasting = parse_critterdb_spellcasting(traits)

        return cls(data['name'], data['stats']['size'], data['stats']['race'], data['stats']['alignment'],
                   data['stats']['armorClass'], data['stats']['armorType'], hp, hitdice, data['stats']['speed'],
                   ability_scores, cr, data['stats']['experiencePoints'], None,
                   ', '.join(data['stats']['senses']), data['stats']['damageVulnerabilities'],
                   data['stats']['damageResistances'], data['stats']['damageImmunities'],
                   data['stats']['conditionImmunities'], saves, skills,
                   data['stats']['languages'], traits, actions, reactions, legactions,
                   data['stats']['legendaryActionsPerRound'], True, 'homebrew', attacks,
                   data['flavor']['nameIsProper'], data['flavor']['imageUrl'],
                   spellcasting=spellcasting)

    @classmethod
    def from_bestiary(cls, data):
        for key in ('traits', 'actions', 'reactions', 'legactions'):
            data[key] = [Trait(**t) for t in data.pop(key)]
        data['spellcasting'] = MonsterSpellbook.from_dict(data.pop('spellbook'))
        data['saves'] = Saves.from_dict(data['saves'])
        data['skills'] = Skills.from_dict(data['skills'])
        data['ability_scores'] = BaseStats.from_dict(data['ability_scores'])
        data['attacks'] = AttackList.from_dict(data['attacks'])
        if 'display_resists' in data:
            data['display_resists'] = Resistances.from_dict(data['display_resists'])
        return cls(**data)

    def to_dict(self):
        return {
            'name': self.name, 'size': self.size, 'race': self.race, 'alignment': self.alignment, 'ac': self.ac,
            'armortype': self.armortype, 'hp': self.hp, 'hitdice': self.hitdice, 'speed': self.speed,
            'ability_scores': self.stats.to_dict(),
            'cr': self.cr, 'xp': self.xp, 'passiveperc': self.passive, 'senses': self.senses,
            'vuln': self.resistances.vuln, 'resist': self.resistances.resist, 'immune': self.resistances.immune,
            'condition_immune': self.condition_immune,
            'saves': self.saves.to_dict(), 'skills': self.skills.to_dict(), 'languages': self.languages,
            'traits': [t.to_dict() for t in self.traits], 'actions': [t.to_dict() for t in self.actions],
            'reactions': [t.to_dict() for t in self.reactions],
            'legactions': [t.to_dict() for t in self.legactions], 'la_per_round': self.la_per_round,
            'srd': self.srd, 'source': self.source, 'attacks': self.attacks.to_dict(), 'proper': self.proper,
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
            desc += f"**Vulnerabilities:** {', '.join(self._displayed_resistances.vuln)}\n"
        if self._displayed_resistances.resist:
            desc += f"**Resistances:** {', '.join(self._displayed_resistances.resist)}\n"
        if self._displayed_resistances.immune:
            desc += f"**Damage Immunities:** {', '.join(self._displayed_resistances.immune)}\n"
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
        if not self.source == 'homebrew':
            return f"https://media.avrae.io/{parse.quote(self.source)}/{parse.quote(self.name)}.png"
        else:
            return self.image_url or ''

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


def parse_critterdb_traits(data, key):
    traits = []
    attacks = []
    for trait in data['stats'][key]:
        name = trait['name']
        raw = trait['description']

        overrides = list(AVRAE_ATTACK_OVERRIDES_RE.finditer(raw))
        raw_atks = list(ATTACK_RE.finditer(raw))
        raw_damage = list(JUST_DAMAGE_RE.finditer(raw))

        filtered = AVRAE_ATTACK_OVERRIDES_RE.sub('', raw)
        desc = '\n'.join(html2text.html2text(text, bodywidth=0).strip() for text in filtered.split('\n')).strip()

        if overrides:
            for override in overrides:
                attacks.append({'name': override.group(1) or name,
                                'attackBonus': override.group(2) or None, 'damage': override.group(3) or None,
                                'details': desc})
        elif raw_atks:
            for atk in raw_atks:
                if atk.group(6) and atk.group(7):  # versatile
                    damage = f"{atk.group(6)}[{atk.group(7)}]"
                    if atk.group(8) and atk.group(8):  # bonus damage
                        damage += f"+{atk.group(8)}[{atk.group(9)}]"
                    attacks.append(
                        {'name': f"2 Handed {name}", 'attackBonus': atk.group(1).lstrip('+'), 'damage': damage,
                         'details': desc})
                if atk.group(4) and atk.group(5):  # ranged
                    damage = f"{atk.group(4)}[{atk.group(5)}]"
                    if atk.group(8) and atk.group(8):  # bonus damage
                        damage += f"+{atk.group(8)}[{atk.group(9)}]"
                    attacks.append({'name': f"Ranged {name}", 'attackBonus': atk.group(1).lstrip('+'), 'damage': damage,
                                    'details': desc})
                damage = f"{atk.group(2)}[{atk.group(3)}]"
                if atk.group(8) and atk.group(9):  # bonus damage
                    damage += f"+{atk.group(8)}[{atk.group(9)}]"
                attacks.append(
                    {'name': name, 'attackBonus': atk.group(1).lstrip('+'), 'damage': damage, 'details': desc})
        else:
            for dmg in raw_damage:
                damage = f"{dmg.group(1)}[{dmg.group(2)}]"
                attacks.append({'name': name, 'attackBonus': None, 'damage': damage, 'details': desc})

        traits.append(Trait(name, desc))
    return traits, attacks


def parse_critterdb_spellcasting(traits):
    known_spells = []
    usual_dc = (0, 0)  # dc, number of spells using dc
    usual_sab = (0, 0)  # same thing
    caster_level = 1
    for trait in traits:
        if not 'Spellcasting' in trait.name:
            continue
        desc = trait.desc
        level_match = re.search(r"is a (\d+)[stndrh]{2}-level", desc)
        ab_dc_match = re.search(r"spell save DC (\d+), [+-](\d+) to hit", desc)
        spells = []
        for spell_match in re.finditer(
                r"(?:(?:(?:\d[stndrh]{2}\slevel)|(?:Cantrip))\s(?:\(.+\))|(?:At will)|(?:\d/day)): (.+)$", desc,
                re.MULTILINE):
            spell_texts = spell_match.group(1).split(', ')
            for spell_text in spell_texts:
                s = spell_text.strip('* _')
                spells.append(s.lower())
        if level_match:
            caster_level = max(caster_level, int(level_match.group(1)))
        if ab_dc_match:
            ab = int(ab_dc_match.group(2))
            dc = int(ab_dc_match.group(1))
            if len(spells) > usual_dc[1]:
                usual_dc = (dc, len(spells))
            if len(spells) > usual_sab[1]:
                usual_sab = (ab, len(spells))
        known_spells.extend(s for s in spells if s not in known_spells)
    dc = usual_dc[0]
    sab = usual_sab[0]
    log.debug(f"Lvl {caster_level}; DC: {dc}; SAB: {sab}; Spells: {known_spells}")
    spells = [SpellbookSpell(s) for s in known_spells]
    spellbook = MonsterSpellbook({}, {}, spells, dc, sab, caster_level)
    return spellbook


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


def spaced_to_camel(spaced):
    return re.sub(r"\s+(\w)", lambda m: m.group(1).upper(), spaced.lower())


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
        has_slot = self.get_slots(level) > 0
        is_at_will = spell.name in self.at_will
        is_daily = spell.name in self.daily and self.daily[spell.name] > 0
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
        if spell.name in self.at_will:
            return
        elif spell.name in self.daily:
            self.daily[spell.name] -= 1
        else:
            self.use_slot(level)
