import re
from math import floor


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
                 speed: str, ability_scores: AbilityScores, cr: str, xp: int, passiveperc: int = 10,
                 senses: str = '', vuln: list = None, resist: list = None, immune: list = None,
                 condition_immune: list = None, raw_saves: str = '', saves: dict = None, raw_skills: str = '',
                 skills: dict = None, languages: list = None, traits: list = None, actions: list = None,
                 reactions: list = None, legactions: list = None, la_per_round=3, srd=True, source='homebrew',
                 attacks: list = None, proper: bool = False):
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
        for skill, stat in SKILL_MAP.items():
            if skill not in skills:
                skills[skill] = ability_scores.get_mod(stat)
        for save, stat in SAVE_MAP.items():
            if save not in saves:
                saves[save] = ability_scores.get_mod(stat)
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

    @classmethod
    def from_data(cls, data):
        _type = ','.join(data['type'].split(',')[:-1])
        ac = int(data['ac'].split(' (')[0])
        armortype = re.search(r'\((.*)\)', data['ac'])
        if armortype is not None:
            armortype = armortype.group(1)
        hp = int(data['hp'].split(' (')[0])
        hitdice = re.search(r'\((.*)\)', data['hp']).group(1)
        scores = AbilityScores(int(data['str']), int(data['dex']), int(data['con']), int(data['int']), int(data['wis']),
                               int(data['cha']))
        vuln = data.get('vulnerable', '').split(', ') if data.get('vulnerable') else None
        resist = data.get('resist', '').split(', ') if data.get('resist') else None
        immune = data.get('immune', '').split(', ') if data.get('immune') else None
        condition_immune = data.get('conditionImmune', '').split(', ') if data.get('condiitonImmune') else None

        languages = data.get('languages', '').split(', ') if data.get('languages') else None

        traits = parse_traits(data, 'trait')
        actions = parse_traits(data, 'action')
        reactions = Trait(data['reaction']['name'], '\n'.join(data['reaction']['text'])) if 'reaction' in data else None
        legactions = parse_traits(data, 'legendary')

        raw_skills = data.get('skill', "")
        skills = parse_raw_skills(raw_skills)
        if isinstance(raw_skills, list):
            raw_skills = raw_skills[0]
        for skill, stat in SKILL_MAP.items():
            if skill not in skills:
                skills[skill] = scores.get_mod(stat)

        raw_saves = data.get('save', "")
        saves = parse_raw_saves(raw_saves)
        for save, stat in SAVE_MAP.items():
            if save not in saves:
                saves[save] = scores.get_mod(stat)

        source = parsesource(data['type'].split(',')[-1])

        return cls(data['name'], parsesize(data['size']), _type, data['alignment'], ac, armortype, hp, hitdice,
                   data['speed'], scores, data['cr'], xp_by_cr(data['cr']), data['passive'], data.get('senses', ''),
                   vuln, resist, immune, condition_immune, raw_saves, saves, raw_skills, skills, languages, traits,
                   actions, reactions, legactions, 3, data.get('srd', False), source, data.get('attacks', []))

    @classmethod
    def from_bestiary(cls, data):
        strength = data.pop('strength')
        dexterity = data.pop('dexterity')
        constitution = data.pop('constitution')
        intelligence = data.pop('intelligence')
        wisdom = data.pop('wisdom')
        charisma = data.pop('charisma')
        data['abilitiy_scores'] = AbilityScores(strength, dexterity, constitution, intelligence, wisdom, charisma)
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
                'srd': self.srd, 'source': self.source, 'attacks': self.attacks, 'proper': self.proper}

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


def parse_raw_saves(raw):
    saves = {}
    for save in raw.split(', '):
        try:
            _type = next(sa for sa in SAVE_MAP if save.split(' ')[0].lower() in sa.lower())
            mod = int(save.split(' ')[1])
            saves[_type] = mod
        except (StopIteration, IndexError, ValueError):
            pass
    return saves


def parse_raw_skills(raw_skills):
    if isinstance(raw_skills, str):
        raw_skills = raw_skills.split(', ')
    else:
        if raw_skills[0]:
            raw_skills = raw_skills[0].split(', ')
        else:
            raw_skills = []
    skills = {}
    for s in raw_skills:
        if s:
            _name = ' '.join(s.split(' ')[:-1]).lower()
            _value = int(s.split(' ')[-1])
            skills[_name] = _value
    return skills


def parse_traits(data, key):
    traits = []
    for trait in data.get(key, []):
        if isinstance(trait['text'], list):
            text = '\n'.join(t for t in trait['text'] if t is not None)
        else:
            text = trait['text']
        attacks = []
        if 'attack' in trait:
            for atk in trait['attack']:
                name, bonus, damage = atk.split('|')
                name = name or trait['name']
                bonus = bonus or None
                attacks.append({'name': name, 'attackBonus': bonus, 'damage': damage, 'details': text})
        traits.append(Trait(trait['name'], text, attacks))
    return traits


def parsesize(size):
    if size == "T": size = "Tiny"
    if size == "S": size = "Small"
    if size == "M": size = "Medium"
    if size == "L": size = "Large"
    if size == "H": size = "Huge"
    if size == "G": size = "Gargantuan"
    return size


def parsesource(src):
    source = src.strip()
    if source == "monster manual": source = "MM";
    if source == "Volo's Guide": source = "VGM";
    if source == "elemental evil": source = "PotA";
    if source == "storm kings thunder": source = "SKT";
    if source == "tyranny of dragons": source = "ToD";
    if source == "out of the abyss": source = "OotA";
    if source == "curse of strahd": source = "CoS";
    if source == "lost mine of phandelver": source = "LMoP";
    if source == "Tales from the Yawning Portal": source = "TYP";
    if source == "tome of beasts": source = "ToB";
    if source == "Plane Shift Amonkhet": source = "PSA";
    if source == "Plane Shift Innistrad": source = "PSI";
    if source == "Plane Shift Kaladesh": source = "PSK";
    if source == "Plane Shift Zendikar": source = "PSZ";
    if source == "Tomb of Annihilation": source = "ToA";
    if source == "The Tortle Package": source = "TTP";
    return source


def xp_by_cr(cr):
    return {'0': 10, '1/8': 25, '1/4': 50, '1/2': 100, '1': 200, '2': 450, '3': 700, '4': 1100, '5': 1800, '6': 2300,
            '7': 2900, '8': 3900, '9': 5000, '10': 5900, '11': 7200, '12': 8400, '13': 10000, '14': 11500, '15': 13000,
            '16': 15000, '17': 18000, '18': 20000, '19': 22000, '20': 25000, '21': 33000, '22': 41000, '23': 50000,
            '24': 62000, '25': 75000, '26': 90000, '27': 105000, '28': 120000, '29': 135000, '30': 155000}.get(cr, 0)
