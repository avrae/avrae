'''
Created on Jun 28, 2017

@author: andrew
'''
import json
from re import IGNORECASE
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

with open('backup/spells.json', mode='r', encoding='utf-8') as f:
    spells = json.load(f)

out = []

for spell in spells:
    print("Processing " + spell['name'])
    if spell.get('source') == "UAMystic":
        print("Skipping mystic talent\n")
        continue
    if isinstance(spell['text'], list):
        text = '\n'.join(spell['text'])
    else:
        text = spell['text']
        
    saves = list(re.finditer(r'(strength|dexterity|constitution|intelligence|wisdom|charisma) saving throw', text, IGNORECASE))
        
    if len(saves):
        print("Save spell")
        for save in saves:
            print("Save: " + save.group(1))
        
        damages = spell.get("roll", [])
        if not isinstance(damages, list):
            damages = [damages]
        
        for i, damage in enumerate(damages):
            occ = []
            for damage_str in re.finditer(r'(\w*?)\s+(acid|bludgeoning|cold|fire|force|lightning|necrotic|piercing|poison|psychic|radiant|slashing|thunder)', text):
                oldDamage = damage_str.group(1).replace(' ', '')
                dtype = damage_str.group(2)
                occNum = len([o for o in occ if oldDamage in o])+1
                newDamage = oldDamage + '[{}]'.format(dtype)
                if damage:
                    if occNum > damage.count(oldDamage): continue
                    damage = nth_repl(damage, oldDamage, newDamage, occNum)
                occ.append(oldDamage)
            damages[i] = damage
        if len(damages):
            print("Damage: " + str(damages))
        else:
            print("Effect spell")
        
        if 'save, or half' in text or 'half damage' in text or 'half as much damage' in text or 'half the initial damage' in text:
            print("Save for half")
        else:
            print("Save or suck")
            
    elif "spell attack" in text.lower():
        print("Attack Spell")
    else:
        print("Just works, skipping\n")
        continue
    
    print()
    keep = input("Keep spell for further processing? ")
    if keep == 'y':
        out.append(spell)

with open('procspells.json', mode='w') as f:
    json.dump(out, f, sort_keys=True, indent=4)
    