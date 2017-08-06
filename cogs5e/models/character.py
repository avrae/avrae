
"""
{'type': 'dicecloud',
 'version': 6, #v6: added stat cvars
 'stats': stats,
 'levels': levels,
 'hp': int(hp),
 'armor': int(armor),
 'attacks': attacks,
 'skills': skills,
 'resist': resistances,
 'immune': immunities,
 'vuln': vulnerabilities,
 'saves': saves,
 'stat_cvars': stat_vars,
 'overrides': {},
 'cvars': {}}
"""

class Character: # TODO: this
    def __init__(self, _chardict):
        self.type = _chardict['type']
        self.version = _chardict['version']
        self.stats = _chardict['stats']
        self.levels = _chardict['levels']
        self.hp = _chardict['hp']
        self.armor = _chardict['armor']
        self.attacks = _chardict['attacks']
        self.skills = _chardict['skills']
        self.resist = _chardict['resist']
        self.immune = _chardict['immune']
        self.vuln = _chardict['vuln']
        self.saves = _chardict['saves']
        self.stat_cvars = _chardict['stat_cvars']
        self.overrides = _chardict.get('overrides', {})
        self.cvars = _chardict.get('cvars', {})