import re
from math import floor
from urllib import parse

import html2text

from utils.functions import a_or_an

AVRAE_ATTACK_OVERRIDES_RE = re.compile(r'<avrae hidden>(.*?)\|([+-]?\d*)\|(.*?)</avrae>', re.IGNORECASE)
ATTACK_RE = re.compile(r'(?:<i>)?(?:\w+ ){1,4}Attack:(?:</i>)? ([+-]?\d+) to hit, .*?(?:<i>)?'
                       r'Hit:(?:</i>)? [+-]?\d+ \((.+?)\) (\w+) damage[., ]??'
                       r'(?:in melee, or [+-]?\d+ \((.+?)\) (\w+) damage at range[,.]?)?'
                       r'(?: or [+-]?\d+ \((.+?)\) (\w+) damage .*?[.,]?)?'
                       r'(?: plus [+-]?\d+ \((.+?)\) (\w+) damage.)?', re.IGNORECASE)
JUST_DAMAGE_RE = re.compile(r'[+-]?\d+ \((.+?)\) (\w+) damage', re.IGNORECASE)


class AbilityScores:
    def __init__(self, str_: int, dex: int, con: int, int_: int, wis: int, cha: int):
        self.strength = str_
        self.dexterity = dex
        self.constitution = con
        self.intelligence = int_
        self.wisdom = wis
        self.charisma = cha

    def get_mod(self, stat):
        return {'str': floor(self.strength / 2 - 5), 'dex': floor(self.dexterity / 2 - 5),
                'con': floor(self.constitution / 2 - 5), 'int': floor(self.intelligence / 2 - 5),
                'wis': floor(self.wisdom / 2 - 5), 'cha': floor(self.charisma / 2 - 5)}.get(stat, 0)


class Trait:
    def __init__(self, name, desc, attacks=None):
        if attacks is None:
            attacks = []
        self.name = name
        self.desc = desc
        self.attacks = attacks

    def to_dict(self):
        return {'name': self.name, 'desc': self.desc, 'attacks': self.attacks}


SKILL_MAP = {'acrobatics': 'dex', 'animal handling': 'wis', 'arcana': 'int', 'athletics': 'str', 'deception': 'cha',
             'history': 'int', 'initiative': 'dex', 'insight': 'wis', 'intimidation': 'cha', 'investigation': 'int',
             'medicine': 'wis', 'nature': 'int', 'perception': 'wis', 'performance': 'cha', 'persuasion': 'cha',
             'religion': 'int', 'sleight of hand': 'dex', 'stealth': 'dex', 'survival': 'wis', 'strength': 'str',
             'dexterity': 'dex', 'constitution': 'con', 'intelligence': 'int', 'wisdom': 'wis', 'charisma': 'cha'}

SAVE_MAP = {'strengthSave': 'str', 'dexteritySave': 'dex', 'constitutionSave': 'con', 'intelligenceSave': 'int',
            'wisdomSave': 'wis', 'charismaSave': 'cha'}


class Monster:
    def __init__(self, name: str, size: str, race: str, alignment: str, ac: int, armortype: str, hp: int, hitdice: str,
                 speed: str, ability_scores: AbilityScores, cr: str, xp: int, passiveperc: int = None,
                 senses: str = '', vuln: list = None, resist: list = None, immune: list = None,
                 condition_immune: list = None, raw_saves: str = '', saves: dict = None, raw_skills: str = '',
                 skills: dict = None, languages: list = None, traits: list = None, actions: list = None,
                 reactions: list = None, legactions: list = None, la_per_round=3, srd=True, source='homebrew',
                 attacks: list = None, proper: bool = False, image_url: str = None, spellcasting=None, page=None):
        if vuln is None:
            vuln = []
        if resist is None:
            resist = []
        if immune is None:
            immune = []
        if condition_immune is None:
            condition_immune = []
        if saves is None:
            saves = {}
        if skills is None:
            skills = {}
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
            attacks = []
        if spellcasting is None:
            spellcasting = {}
        for skill, stat in SKILL_MAP.items():
            if skill not in skills:
                skills[skill] = ability_scores.get_mod(stat)
            else:
                skills[skill] = int(skills[skill])
        for save, stat in SAVE_MAP.items():
            if save not in saves:
                saves[save] = ability_scores.get_mod(stat)
            else:
                saves[save] = int(saves[save])
        if passiveperc is None:
            passiveperc = 10 + skills['perception']
        self.name = name
        self.size = size
        self.race = race
        self.alignment = alignment
        self.ac = ac
        self.armortype = armortype
        self.hp = hp
        self.hitdice = hitdice
        self.speed = speed
        self.strength = ability_scores.strength
        self.dexterity = ability_scores.dexterity
        self.constitution = ability_scores.constitution
        self.intelligence = ability_scores.intelligence
        self.wisdom = ability_scores.wisdom
        self.charisma = ability_scores.charisma
        self.cr = cr
        self.xp = xp
        self.passive = passiveperc
        self.senses = senses
        self.vuln = vuln
        self.resist = resist
        self.immume = immune
        self.condition_immune = condition_immune
        self.raw_saves = raw_saves
        self.saves = saves
        self.raw_skills = raw_skills
        self.skills = skills
        self.languages = languages
        self.traits = traits
        self.actions = actions
        self.reactions = reactions
        self.legactions = legactions
        self.la_per_round = la_per_round
        self.srd = srd
        self.source = source
        self.attacks = attacks
        self.proper = proper
        self.image_url = image_url
        self.spellcasting = spellcasting
        self.page = page  # this should really be by source, but oh well

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
        scores = AbilityScores(data['str'], data['dex'], data['con'], data['int'], data['wis'], data['cha'])
        if isinstance(data['cr'], dict):
            cr = data['cr']['cr']
        else:
            cr = data['cr']

        vuln = parse_resists(data['vulnerable']) if 'vulnerable' in data else None
        resist = parse_resists(data['resist']) if 'resist' in data else None
        immune = parse_resists(data['immune']) if 'immune' in data else None
        condition_immune = data.get('conditionImmune', []) if 'conditionImmune' in data else None

        languages = data.get('languages', '').split(', ') if 'languages' in data else None

        traits = [Trait(t['name'], t['text']) for t in data.get('trait', [])]
        actions = [Trait(t['name'], t['text']) for t in data.get('action', [])]
        legactions = [Trait(t['name'], t['text']) for t in data.get('legendary', [])]
        reactions = [Trait(t['name'], t['text']) for t in data.get('reaction', [])]

        skills = data.get('skill', {})
        skill_text = parse_skill_text(skills)
        for skill in skills.copy():
            if not skill in SKILL_MAP:
                del skills[skill]

        saves = parse_raw_saves(data.get('save', {}))
        save_text = parse_save_text(data.get('save', {}))

        source = data['source']
        proper = bool(data.get('isNamedCreature') or data.get('isNPC'))

        attacks = data.get('attacks', [])
        spellcasting = data.get('spellcasting', {})

        return cls(data['name'], parsesize(data['size']), _type, alignment, ac, armortype, hp, hitdice,
                   speed, scores, cr, xp_by_cr(cr), data['passive'], data.get('senses', ''),
                   vuln, resist, immune, condition_immune, save_text, saves, skill_text, skills, languages, traits,
                   actions, reactions, legactions, 3, data.get('srd', False), source, attacks,
                   spellcasting=spellcasting, page=data.get('page'), proper=proper)

    @classmethod
    def from_critterdb(cls, data):
        ability_scores = AbilityScores(data['stats']['abilityScores']['strength'],
                                       data['stats']['abilityScores']['dexterity'],
                                       data['stats']['abilityScores']['constitution'],
                                       data['stats']['abilityScores']['intelligence'],
                                       data['stats']['abilityScores']['wisdom'],
                                       data['stats']['abilityScores']['charisma'])
        cr = {0.125: '1/8', 0.25: '1/4', 0.5: '1/2'}.get(data['stats']['challengeRating'],
                                                         str(data['stats']['challengeRating']))
        num_hit_die = data['stats']['numHitDie']
        hit_die_size = data['stats']['hitDieSize']
        con_by_level = num_hit_die * ability_scores.get_mod('con')
        hp = floor(((hit_die_size + 1) / 2) * num_hit_die) + con_by_level
        hitdice = f"{num_hit_die}d{hit_die_size} + {con_by_level}"

        proficiency = data['stats']['proficiencyBonus']
        skills = {}
        raw_skills = []
        for skill in data['stats']['skills']:
            name = skill['name'].lower()
            if skill['proficient']:
                mod = ability_scores.get_mod(SKILL_MAP.get(name)) + proficiency
            else:
                try:
                    mod = skill['value']
                except KeyError:
                    continue
            skills[name] = mod
            raw_skills.append(f"{skill['name']} {mod:+}")
        raw_skills = ', '.join(raw_skills)

        saves = {}
        raw_saves = []
        for save in data['stats']['savingThrows']:
            name = save['ability'].lower() + 'Save'
            if save['proficient']:
                mod = ability_scores.get_mod(SAVE_MAP.get(name)) + proficiency
            else:
                mod = save.get('value') or ability_scores.get_mod(SAVE_MAP.get(name))
            saves[name] = mod
            raw_saves.append(f"{save['ability'].title()} {mod:+}")
        raw_saves = ', '.join(raw_saves)

        traits = parse_critterdb_traits(data, 'additionalAbilities')
        actions = parse_critterdb_traits(data, 'actions')
        reactions = parse_critterdb_traits(data, 'reactions')
        legactions = parse_critterdb_traits(data, 'legendaryActions')

        attacks = []
        for atk_src in (traits, actions, reactions, legactions):
            for trait in atk_src:
                attacks.extend(trait.attacks)

        return cls(data['name'], data['stats']['size'], data['stats']['race'], data['stats']['alignment'],
                   data['stats']['armorClass'], data['stats']['armorType'], hp, hitdice, data['stats']['speed'],
                   ability_scores, cr, data['stats']['experiencePoints'], None,
                   ', '.join(data['stats']['senses']), data['stats']['damageVulnerabilities'],
                   data['stats']['damageResistances'], data['stats']['damageImmunities'],
                   data['stats']['conditionImmunities'], raw_saves, saves, raw_skills, skills,
                   data['stats']['languages'], traits, actions, reactions, legactions,
                   data['stats']['legendaryActionsPerRound'], True, 'homebrew', attacks,
                   data['flavor']['nameIsProper'], data['flavor']['imageUrl'])

    @classmethod
    def from_bestiary(cls, data):
        strength = data.pop('strength')
        dexterity = data.pop('dexterity')
        constitution = data.pop('constitution')
        intelligence = data.pop('intelligence')
        wisdom = data.pop('wisdom')
        charisma = data.pop('charisma')
        data['ability_scores'] = AbilityScores(strength, dexterity, constitution, intelligence, wisdom, charisma)
        for key in ('traits', 'actions', 'reactions', 'legactions'):
            data[key] = [Trait(**t) for t in data.pop(key)]
        return cls(**data)

    def to_dict(self):
        return {'name': self.name, 'size': self.size, 'race': self.race, 'alignment': self.alignment, 'ac': self.ac,
                'armortype': self.armortype, 'hp': self.hp, 'hitdice': self.hitdice, 'speed': self.speed,
                'strength': self.strength, 'dexterity': self.dexterity, 'constitution': self.constitution,
                'intelligence': self.intelligence, 'wisdom': self.wisdom, 'charisma': self.charisma,
                'cr': self.cr, 'xp': self.xp, 'passiveperc': self.passive, 'senses': self.senses, 'vuln': self.vuln,
                'resist': self.resist, 'immune': self.immume, 'condition_immune': self.condition_immune,
                'raw_saves': self.raw_saves, 'saves': self.saves,
                'raw_skills': self.raw_skills, 'skills': self.skills, 'languages': self.languages,
                'traits': [t.to_dict() for t in self.traits], 'actions': [t.to_dict() for t in self.actions],
                'reactions': [t.to_dict() for t in self.reactions],
                'legactions': [t.to_dict() for t in self.legactions], 'la_per_round': self.la_per_round,
                'srd': self.srd, 'source': self.source, 'attacks': self.attacks, 'proper': self.proper,
                'image_url': self.image_url, 'spellcasting': self.spellcasting}

    def get_stat_array(self):
        """
        Returns a string describing the monster's 6 core stats, with modifiers.
        """
        str_mod = floor(self.strength / 2 - 5)
        dex_mod = floor(self.dexterity / 2 - 5)
        con_mod = floor(self.constitution / 2 - 5)
        int_mod = floor(self.intelligence / 2 - 5)
        wis_mod = floor(self.wisdom / 2 - 5)
        cha_mod = floor(self.charisma / 2 - 5)
        return f"**STR**: {self.strength} ({str_mod:+}) **DEX**: {self.dexterity} ({dex_mod:+}) " \
               f"**CON**: {self.constitution} ({con_mod:+})\n**INT**: {self.intelligence} ({int_mod:+}) " \
               f"**WIS**: {self.wisdom} ({wis_mod:+}) **CHA**: {self.charisma} ({cha_mod:+})"

    def get_hidden_stat_array(self):
        stats = ["Unknown", "Unknown", "Unknown", "Unknown", "Unknown", "Unknown"]
        for i, stat in enumerate(
                (self.strength, self.dexterity, self.constitution, self.intelligence, self.wisdom, self.charisma)):
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

        if self.raw_saves:
            desc += f"**Saving Throws:** {self.raw_saves}\n"
        if self.raw_skills:
            desc += f"**Skills:** {self.raw_skills}\n"
        desc += f"**Senses:** {self.get_senses_str()}.\n"
        if self.vuln:
            desc += f"**Vulnerabilities:** {', '.join(self.vuln)}\n"
        if self.resist:
            desc += f"**Resistances:** {', '.join(self.resist)}\n"
        if self.immume:
            desc += f"**Damage Immunities:** {', '.join(self.immume)}\n"
        if self.condition_immune:
            desc += f"**Condition Immunities:** {', '.join(self.condition_immune)}\n"
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
            return f"https://5etools.com/img/{parse.quote(self.source)}/{parse.quote(self.name)}.png"
        else:
            return self.image_url or ''

    def get_mod(self, stat):
        """
        Gets the monster's stat modifier for a core stat.
        :param stat: The core stat to get. Can be of the form "cha", "charisma", or "charismaMod".
        :return: The monster's relevant stat modifier.
        """
        valid = ["strengthMod", "dexterityMod", "constitutionMod", "intelligenceMod", "wisdomMod", "charismaMod"]
        stat = next((s for s in valid if stat in s), None)
        if stat is None:
            raise ValueError(f"{stat} is not a valid stat.")
        score = (self.strength, self.dexterity, self.constitution, self.intelligence, self.wisdom, self.charisma)[
            valid.index(stat)]
        return int(floor((score - 10) / 2))


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
                 'A': 'any', 'NX': 'neutral', 'NY': 'neutral'}
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


def parse_skill_text(skills):
    out = []
    for skill, mod in skills.items():
        if not isinstance(mod, dict):
            out.append(f"{skill.title()} {mod}")
    return ', '.join(out)


def parse_save_text(saves):
    return ', '.join(f"{save.title()} {mod}" for save, mod in saves.items())


def parse_raw_saves(raw):
    saves = {}
    for save, mod in raw.items():
        try:
            _type = next(sa for sa in SAVE_MAP if save.lower() in sa.lower())
            saves[_type] = int(mod)
        except (StopIteration, IndexError, ValueError):
            pass
    return saves


def parse_critterdb_traits(data, key):
    traits = []
    for trait in data['stats'][key]:
        name = trait['name']
        raw = trait['description']

        attacks = []
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

        traits.append(Trait(name, desc, attacks))
    return traits


def parse_resists(resists):
    out = []
    for dmgtype in resists:
        if isinstance(dmgtype, str):
            out.append(dmgtype)
        elif isinstance(dmgtype, dict):
            if 'special' in dmgtype:
                out.append(dmgtype['special'])
            else:
                out.append(
                    f"{', '.join(parse_resists(dmgtype.get('resist') or dmgtype.get('immune') or dmgtype.get('vulnerable')))} "
                    f"{dmgtype.get('note')}")
    return out


def parsesize(size):
    s = {"T": "Tiny", "S": "Small", "M": "Medium", "L": "Large", "H": "Huge", "G": "Gargantuan"}
    return s.get(size, "Unknown")


def xp_by_cr(cr):
    return {'0': 10, '1/8': 25, '1/4': 50, '1/2': 100, '1': 200, '2': 450, '3': 700, '4': 1100, '5': 1800, '6': 2300,
            '7': 2900, '8': 3900, '9': 5000, '10': 5900, '11': 7200, '12': 8400, '13': 10000, '14': 11500, '15': 13000,
            '16': 15000, '17': 18000, '18': 20000, '19': 22000, '20': 25000, '21': 33000, '22': 41000, '23': 50000,
            '24': 62000, '25': 75000, '26': 90000, '27': 105000, '28': 120000, '29': 135000, '30': 155000}.get(cr, 0)
