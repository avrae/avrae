class AbilityScores:
    def __init__(self, str_: int, dex: int, con: int, int_: int, wis: int, cha: int):
        self.strength = str_
        self.dexterity = dex
        self.constitution = con
        self.intelligence = int_
        self.wisdom = wis
        self.charisma = cha


class Trait:
    def __init__(self, name, desc, attack=None):
        self.name = name
        self.desc = desc
        self.attack = attack


class Monster:
    def __init__(self, name: str, size: str, race: str, alignment: str, ac: int, armortype: str, hp: int, hitdice: str,
                 speed: str, ability_scores: AbilityScores, cr: str, xp: int, passiveperc: int = 10,
                 vuln: list = None, resist: list = None, immune: list = None, condition_immune: list = None,
                 saves: dict = None, skills: dict = None, languages: list = None, traits: list = None,
                 actions: list = None, reactions: list = None, legactions: list = None,
                 la_per_round=3):
        if vuln is None:
            vuln = []
        if resist is None:
            resist = []
        if immune is None:
            immune = []
        if condition_immune is None:
            condition_immune = []
        if saves is None:
            saves = {}  # TODO: generate from stat scores
        if skills is None:
            skills = {}  # TODO: generate from stat scores
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
        self.vuln = vuln
        self.resist = resist
        self.immume = immune
        self.condition_immune = condition_immune
        self.saves = saves
        self.skills = skills
        self.languages = languages
        self.traits = traits
        self.actions = actions
        self.reactions = reactions
        self.legactions = legactions
        self.la_per_round = la_per_round
