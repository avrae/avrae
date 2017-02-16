'''
Created on Feb 14, 2017

@author: andrew
'''


import asyncio
import io
import random
import re

import aiohttp
import discord
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfparser import PDFParser
from pdfminer.pdftypes import resolve1
from pdfminer.psparser import PSLiteral

from cogs5e.sheets.sheetParser import SheetParser


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
        except:
            raise
        
        sheet = {'type': 'pdf',
                 'stats': stats,
                 'levels': {'level': 0},
                 'hp': int(hp),
                 'armor': int(armor),
                 'attacks': attacks,
                 'skills': skills,
                 'saves': {}}
        
        for key, skill in skills.items():
            if 'Save' in key:
                sheet['saves'][key] = skills[key]
                
        embed = self.get_embed(sheet)
        
        return {'embed': embed, 'sheet': sheet}
    
    def get_embed(self, sheet):
        stats = sheet['stats']
        hp = sheet['hp']
        skills = sheet['skills']
        attacks = sheet['attacks']
        saves = sheet['saves']
        armor = sheet['armor']
        embed = discord.Embed()
        embed.colour = random.randint(0, 0xffffff)
        embed.title = stats['name']
        embed.set_thumbnail(url=stats['image'])
        embed.add_field(name="HP", value="**HP:** {}".format(hp))
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
        stats['name'] = character.get('CharacterName')
        stats['description'] = "Description is not supported with the PDF loader."
        stats['proficiencyBonus'] = int(character.get('ProfBonus'))
        
        for stat in ('strength', 'dexterity', 'constitution', 'wisdom', 'intelligence', 'charisma'):
            stats[stat] = int(character.get(stat[:3].upper() + 'score'))
            stats[stat + 'Mod'] = int(character.get(stat[:3].upper() + 'bonus'))
        
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
        
        attack['attackBonus'] = attack['attackBonus'].replace('+', '', 1) if attack['attackBonus'] is not None else None
        
        return attack
        
    def get_attacks(self):
        """Returns a list of dicts of all of the character's attacks."""
        if self.character is None: raise Exception('You must call get_character() first.')
        attacks = []
        for attack in range(3):
            a = self.get_attack(attack)
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
