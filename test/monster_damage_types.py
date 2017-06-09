'''
Created on Jun 8, 2017

@author: andrew
'''

import json
import re

def nth_repl(s, sub, repl, nth):
    find = s.find(sub)
    # if find is not p1 we have found at least one match for the substring
    i = find != -1
    # loop util we find the nth or we find no match
    while find != -1 and i != nth:
        # find + 1 means we start at the last match start index + 1
        find = s.find(sub, find + 1)
        i += 1
    # if i  is equal to nth we found nth matches so replace
    if i == nth:
        return s[:find]+repl+s[find + len(sub):]
    return s

with open('backup/bestiary.json', mode='r', encoding='utf-8') as f:
    monsters = json.load(f)
    
for monster in monsters:
    attacks = []  # setup things
    if "trait" in monster:
        for a in monster["trait"]:
            if isinstance(a['text'], list):
                a['text'] = '\n'.join(t for t in a['text'] if t is not None)
            if 'attack' in a:
                attacks.append(a)
    if "action" in monster:
        for a in monster["action"]:
            if isinstance(a['text'], list):
                a['text'] = '\n'.join(t for t in a['text'] if t is not None)     
            if 'attack' in a:
                attacks.append(a)
        
    if "reaction" in monster:
        a = monster["reaction"]
        if isinstance(a['text'], list):
            a['text'] = '\n'.join(t for t in a['text'] if t is not None) 
        if 'attack' in a:
            attacks.append(a)
        
    if "legendary" in monster:
        for a in monster["legendary"]:
            if isinstance(a['text'], list):
                a['text'] = '\n'.join(t for t in a['text'] if t is not None)
            if 'attack' in a:
                attacks.append(a)
                
    # fix list of attack dicts
    tempAttacks = []
    for a in attacks:
        desc = a['text']
        parentName = a['name']
        for atk in a['attack']:
            if atk is None: continue
            data = atk.split('|')
            name = data[0] if not data[0] == '' else parentName
            toHit = data[1] if not data[1] == '' else None
            damage = data[2] if not data[2] == '' else None
            occ = []
            for damage_str in re.finditer(r'\((.*?)\)\s+(\w+)', desc):
                oldDamage = damage_str.group(1).replace(' ', '')
                dtype = damage_str.group(2)
                occNum = len([o for o in occ if oldDamage in o])+1
                newDamage = oldDamage + '[{}]'.format(dtype)
                if damage:
                    if occNum > damage.count(oldDamage): continue
                    damage = nth_repl(damage, oldDamage, newDamage, occNum)
                occ.append(oldDamage)
            atkObj = {'name': name,
                      'desc': desc,
                      'attackBonus': toHit,
                      'damage': damage}
            tempAttacks.append(atkObj)
    
    monster['attacks'] = tempAttacks

with open('backup/bestiary_typed.json', mode='w', encoding='utf-8') as f:
    json.dump(monsters, f, sort_keys=True, indent=4)
print("done!")