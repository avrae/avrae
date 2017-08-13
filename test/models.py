'''
Created on Jun 30, 2017

@author: andrew
'''

attack = {'name': "Fire Bolt",
          'desc': "A flammable object hit by this spell ignites if it isn't being worn or carried.",
          'attackBonus': "12",
          'damage': "4d10[fire]"}

save_dmg = {'name': 'Fireball',
            'save': 'dexterity',
            'desc': '',
            'damage': '8d6[fire]',
            'success': '8d6/2[fire]'}



stats = {"name":"", "image":"", "description":"",
         "strength":10, "dexterity":10, "constitution":10, "wisdom":10, "intelligence":10, "charisma":10,
         "strengthMod":0, "dexterityMod":0, "constitutionMod":0, "wisdomMod":0, "intelligenceMod":0, "charismaMod":0,
         "proficiencyBonus":0}

levels = {"level": 0}

attacks = [{'attackBonus': '0', 'damage':'0', 'name': 'foo', 'details': 'bar'}]

skills = {'acrobatics': 0} # etc

resistances = ['cold']
immunities = vulnerabilities = resistances

saves = {'dexteritySave': 0} # etc

stat_vars = {}

# reset: can be long, short, hp, None, reset
# Counter object - fields= value, reset, max, min
# value: int; reset: long, short, None, hp, 'none'
consumables = {'hp': {'value': 0, 'reset': 'long', 'max': 100}, # optional: max, min, reset
               'deathsaves': {'fail': {'value': 0, 'reset': 'hp'},
                              'success': {'value': 0, 'reset': 'hp'}},
               'spellslots': {'1': {'value': 0, 'reset': 'long', 'max': 4, 'min': 0},
                              '2': {'value': 0, 'reset': 'long', 'max': 3, 'min': 0}}, # etc
               'custom': {'NAME': {'value': 0, 'reset': 'long'},
                          'NAME2': {'value': 0, 'reset': 'long'}} # etc
               }

spellbook = {'spellslots': {"1": 4,
                            "2": 3}, # etc, max only
             'spells': ['Fireball', 'Fire Bolt'],
             'dc': 10,
             'attackBonus': 3} # etc

character = {'type': 'dicecloud',
             'version': 6,
             'stats': stats,
             'levels': levels,
             'hp': 0,
             'armor': 10,
             'attacks': attacks,
             'skills': skills,
             'resist': resistances,
             'immune': immunities,
             'vuln': vulnerabilities,
             'saves': saves,
             'stat_cvars': stat_vars,
             'overrides': {}, # optional
             'cvars': {}, # optional
             'skill_effects': {}, # v7dc
             'consumables': {}, #v3gsht, v3pdf, v8dc
             'spellbook': spellbook # v4gsht, v4pdf, v9dc
             }
