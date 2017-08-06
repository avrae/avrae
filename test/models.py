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

consumables = {'hp': 0,
               'deathsaves': {'fail': 0, 'success': 0},
               'spellslots': {"1": 0, "2": 0} # etc
               }

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
             'cvars': {} # optional
             }
