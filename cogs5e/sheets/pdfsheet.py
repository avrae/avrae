"""
Created on Feb 14, 2017

@author: andrew
"""


import asyncio
import io
import logging
import random
import re

import aiohttp
import discord
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfparser import PDFParser
from pdfminer.pdftypes import resolve1
from pdfminer.psparser import PSLiteral

from cogs5e.funcs.dice import get_roll_comment
from cogs5e.funcs.lookupFuncs import c
from cogs5e.sheets.errors import MissingAttribute
from cogs5e.sheets.sheetParser import SheetParser
from utils.functions import strict_search

log = logging.getLogger(__name__)

class PDFSheetParser(SheetParser):
    
    def __init__(self, file):
        self.file = file
        self.character = None

    async def get_character(self):
        file = self.file
        if not file['filename'].endswith('.pdf'): raise Exception('This is not a PDF file!')
        async with aiohttp.get(file['url']) as f:
            fp = io.BytesIO(await f.read())
        
        def parsePDF():
            character = {}
            parser = PDFParser(fp)
            doc = PDFDocument(parser)
            try:
                fields = resolve1(doc.catalog['AcroForm'])['Fields']
            except:
                raise Exception('This is not a form-fillable character sheet!')
            for i in fields:
                field = resolve1(i)
                name, value = field.get('T'), field.get('V')
                if isinstance(value, PSLiteral):
                    value = value.name
                elif value is not None:
                    try:
                        value = value.decode('iso-8859-1')
                    except:
                        pass
                    
                character[name.decode('iso-8859-1')] = value
            return character
        loop = asyncio.get_event_loop()
        character = await loop.run_in_executor(None, parsePDF)
        self.character = character
        return character
    
    def get_sheet(self):
        """Returns a dict with character sheet data."""
        if self.character is None: raise Exception('You must call get_character() first.')
        character = self.character
        try:
            stats = self.get_stats()
            hp = character.get('HPMax')
            armor = character.get('AC')
            attacks = self.get_attacks()
            skills = self.get_skills()
            level = self.get_level()
            spellbook = self.get_spellbook()
        except:
            raise
        
        saves = {}
        for key in skills:
            if 'Save' in key:
                saves[key] = skills[key]
        
        stat_vars = {}
        stat_vars.update(stats)
        stat_vars['level'] = int(level)
        stat_vars['hp'] = int(hp)
        stat_vars['armor'] = int(armor)
        stat_vars.update(saves)
        
        sheet = {'type': 'pdf',
                 'version': 5, #v3: added stat cvars
                               #v4: consumables
                               #v5: spellbook
                 'stats': stats,
                 'levels': {'level': int(level)},
                 'hp': int(hp),
                 'armor': int(armor),
                 'attacks': attacks,
                 'skills': skills,
                 'resist': [],
                 'immune': [],
                 'vuln': [],
                 'saves': saves,
                 'stat_cvars': stat_vars,
                 'consumables': {},
                 'spellbook': spellbook}
                
        embed = self.get_embed(sheet)
        
        return {'embed': embed, 'sheet': sheet}
    
    def get_embed(self, sheet):
        stats = sheet['stats']
        hp = sheet['hp']
        skills = sheet['skills']
        attacks = sheet['attacks']
        levels = sheet['levels']
        saves = sheet['saves']
        armor = sheet['armor']
        embed = discord.Embed()
        embed.colour = random.randint(0, 0xffffff)
        embed.title = stats['name']
        embed.set_thumbnail(url=stats['image'])
        embed.add_field(name="HP/Level", value="**HP:** {}\nLevel {}".format(hp, levels['level']))
        embed.add_field(name="AC", value=str(armor))
        embed.add_field(name="Stats", value="**STR:** {strength} ({strengthMod:+})\n" \
                                            "**DEX:** {dexterity} ({dexterityMod:+})\n" \
                                            "**CON:** {constitution} ({constitutionMod:+})\n" \
                                            "**INT:** {intelligence} ({intelligenceMod:+})\n" \
                                            "**WIS:** {wisdom} ({wisdomMod:+})\n" \
                                            "**CHA:** {charisma} ({charismaMod:+})".format(**stats))
        embed.add_field(name="Saves", value="**STR:** {strengthSave:+}\n" \
                                            "**DEX:** {dexteritySave:+}\n" \
                                            "**CON:** {constitutionSave:+}\n" \
                                            "**INT:** {intelligenceSave:+}\n" \
                                            "**WIS:** {wisdomSave:+}\n" \
                                            "**CHA:** {charismaSave:+}".format(**saves))
        
        skillsStr = ''
        tempSkills = {}
        for skill, mod in sorted(skills.items()):
            if 'Save' not in skill:
                skillsStr += '**{}**: {:+}\n'.format(re.sub(r'((?<=[a-z])[A-Z]|(?<!\A)[A-Z](?=[a-z]))', r' \1', skill), mod)
                tempSkills[skill] = mod
        sheet['skills'] = tempSkills
                
        embed.add_field(name="Skills", value=skillsStr.title())
        
        tempAttacks = []
        for a in attacks:
            if a is not None:
                if a['attackBonus'] is not None:
                    bonus = a['attackBonus']
                    tempAttacks.append("**{0}:** +{1} To Hit, {2} damage.".format(a['name'],
                                                                                  bonus,
                                                                                  a['damage'] if a['damage'] is not None else 'no'))
                else:
                    tempAttacks.append("**{0}:** {1} damage.".format(a['name'],
                                                                     a['damage'] if a['damage'] is not None else 'no'))
        if tempAttacks == []:
            tempAttacks = ['No attacks.']
        embed.add_field(name="Attacks", value='\n'.join(tempAttacks))
        
        return embed
        
    def get_stats(self):
        """Returns a dict of stats."""
        if self.character is None: raise Exception('You must call get_character() first.')
        character = self.character
        stats = {"name":"", "image":"", "description":"",
                 "strength":10, "dexterity":10, "constitution":10, "wisdom":10, "intelligence":10, "charisma":10,
                 "strengthMod":0, "dexterityMod":0, "constitutionMod":0, "wisdomMod":0, "intelligenceMod":0, "charismaMod":0,
                 "proficiencyBonus":0}
        stats['name'] = character.get('CharacterName', "No name") or "Unnamed"
        stats['description'] = "Description is not supported with the PDF loader."
        stats['proficiencyBonus'] = int(character.get('ProfBonus'))
        
        for stat in ('strength', 'dexterity', 'constitution', 'wisdom', 'intelligence', 'charisma'):
            try:
                stats[stat] = int(character.get(stat[:3].upper() + 'score'))
                stats[stat + 'Mod'] = int(character.get(stat[:3].upper() + 'bonus'))
            except TypeError:
                raise MissingAttribute(stat)
        
        return stats
            
    def get_attack(self, atkIn):
        """Calculates and returns a dict."""
        if self.character is None: raise Exception('You must call get_character() first.')
        character = self.character
        attack = {'attackBonus': '0', 'damage':'0', 'name': ''}
        
        attack['name'] = character.get('Attack' + str(atkIn))
        attack['attackBonus'] = character.get('AtkBonus' + str(atkIn))
        attack['damage'] = character.get('Damage' + str(atkIn))
        
        if attack['name'] is None:
            return None
        if attack['damage'] is "":
            attack['damage'] = None
        else:
            damageTypes = ['acid', 'bludgeoning', 'cold', 'fire', 'force',
                           'lightning', 'necrotic', 'piercing', 'poison',
                           'psychic', 'radiant', 'slashing', 'thunder']
            dice, comment = get_roll_comment(attack['damage'])
            if any(d in comment.lower() for d in damageTypes):
                attack['damage'] = "{}[{}]".format(dice, comment)
            else:
                attack['damage'] = dice
                if comment.strip():
                    attack['details'] = comment.strip()
        
        attack['attackBonus'] = attack['attackBonus'].replace('+', '', 1) if attack['attackBonus'] is not None else None
        
        return attack
        
    def get_attacks(self):
        """Returns a list of dicts of all of the character's attacks."""
        if self.character is None: raise Exception('You must call get_character() first.')
        attacks = []
        for attack in range(3):
            a = self.get_attack(attack + 1)
            if a is not None: attacks.append(a)
        return attacks
            
    def get_skills(self):
        """Returns a dict of all the character's skills."""
        if self.character is None: raise Exception('You must call get_character() first.')
        character = self.character
        skillslist = ['Acrobatics', 'AnHan', 'Arcana', 'Athletics',
                      'CHAsave', 'CONsave', 'Deception', 'DEXsave',
                      'History', 'Init', 'Insight', 'INTsave',
                      'Intimidation', 'Investigation', 'Medicine', 'Nature',
                      'Perception', 'Performance', 'Persuasion', 'Religion',
                      'SleightofHand', 'Stealth', 'STRsave', 'Survival', 'WISsave']
        skillsMap = ['acrobatics', 'animalHandling', 'arcana', 'athletics',
                     'charismaSave', 'constitutionSave', 'deception', 'dexteritySave',
                     'history', 'initiative', 'insight', 'intelligenceSave',
                     'intimidation', 'investigation', 'medicine', 'nature',
                     'perception', 'performance', 'persuasion', 'religion',
                     'sleightOfHand', 'stealth', 'strengthSave', 'survival', 'wisdomSave']
        skills = {}
        for skill in skillslist:
            skills[skillsMap[skillslist.index(skill)]] = int(character.get(skill))
             
        for stat in ('strength', 'dexterity', 'constitution', 'wisdom', 'intelligence', 'charisma'):
            skills[stat] = int(character.get(stat[:3].upper() + 'bonus'))
        
        return skills
    
    def get_level(self):
        if self.character is None: raise Exception('You must call get_character() first.')
        character = self.character
        level = 0
        classlevel = character.get("ClassLevel", "")
        for l in re.finditer(r'\d+', classlevel):
            level += int(l.group(0))
        return level

    def get_spellbook(self):
        if self.character is None: raise Exception('You must call get_character() first.')
        spellbook = {'spellslots': {},
                     'spells': [],
                     'dc': 0,
                     'attackBonus': 0}

        for lvl in range(1, 10):
            try:
                numSlots = int(self.character.get(f"SlotsTot{lvl}") or 0)
            except ValueError:
                numSlots = 0
            spellbook['spellslots'][str(lvl)] = numSlots

        spellnames = set([self.character.get(f"Spells{n}") for n in range(1, 101) if self.character.get(f"Spells{n}")])

        for spell in spellnames:
            s = strict_search(c.spells, 'name', spell)
            if s:
                spellbook['spells'].append(s.get('name'))

        try:
            spellbook['dc'] = int(self.character.get('SpellSaveDC', 0) or 0)
        except ValueError:
            pass

        try:
            spellbook['attackBonus'] = int(self.character.get('SAB', 0) or 0)
        except ValueError:
            pass

        log.debug(f"Completed parsing spellbook: {spellbook}")
        return spellbook
