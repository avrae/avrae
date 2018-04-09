class AbilityScores:
    def __init__(self, str_: int, dex: int, con: int, int_: int, wis: int, cha: int):
        self.strength = str_
        self.dexterity = dex
        self.constitution = con
        self.intelligence = int_
        self.wisdom = wis
        self.charisma = cha


class Monster:
    def __init__(self, name, size, race, alignment, ac, armortype, hp, hitdie, speed, ability_scores,
                 passiveperc, cr, xp,
                 vuln=None, resist=None, immune=None, condition_immune=None, saves=None, skills=None, languages=None,
                 traits=None, actions=None, reactions=None, legactions=None, la_per_round=3):
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
