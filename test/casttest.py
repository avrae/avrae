'''
Created on Jun 28, 2017

@author: andrew
'''
import json
from re import IGNORECASE
import re


with open('backup/spells.json', mode='r', encoding='utf-8') as f:
    spells = json.load(f)
    
sp = input("Cast: ")
while sp:
    spell = next(s for s in spells if sp in s['name'])
    print("Casting " + spell['name'])
    
    if isinstance(spell['text'], list):
        text = '\n'.join(spell['text'])
    else:
        text = spell['text']
        
    saves = re.finditer(r'(strength|dexterity|constitution|intelligence|wisdom|charisma) saving throw', text, IGNORECASE)
    if len(list(saves)):
        print("Save spell!")
        for save in saves:
            print("Save: " + save.group(1))
        if 'save, or half' in text:
            print("Save for half")
        else:
            print("Save or suck")
    
    sp = input("Cast: ")