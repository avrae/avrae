'''
Created on May 8, 2017

@author: andrew
'''
import asyncio
import random
import re

import discord
import gspread
from gspread.utils import extract_id_from_url
import numexpr
from oauth2client.service_account import ServiceAccountCredentials

from cogs5e.sheets.errors import MissingAttribute
from cogs5e.sheets.sheetParser import SheetParser


class GoogleSheet(SheetParser):
    
    def __init__(self, url):
        self.url = url
        self.character = None
    
    def _gchar(self):
        scope = ['https://spreadsheets.google.com/feeds']
        credentials = ServiceAccountCredentials.from_json_keyfile_name('avrae-0b82f09d7ab3.json', scope)
        gc = gspread.authorize(credentials)
        sheet = gc.open_by_key(self.url).sheet1
        self.character = sheet
        return sheet
    
    async def get_character(self):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._gchar)
    
    def get_sheet(self):
        """Returns a dict with character sheet data."""
        if self.character is None: raise Exception('You must call get_character() first.')
        character = self.character
        try:
            stats = self.get_stats()
            hp = character.acell("U16").value
            armor = character.acell("R12").value
            attacks = self.get_attacks()
            skills = self.get_skills()
            level = self.get_level()
        except:
            raise
        
        sheet = {'type': 'google',
                 'version': 1,
                 'stats': stats,
                 'levels': {'level': int(level)},
                 'hp': int(hp),
                 'armor': int(armor),
                 'attacks': attacks,
                 'skills': skills,
                 'resist': [],
                 'immune': [],
                 'vuln': [],
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
        stats['name'] = character.acell("C6").value
        stats['description'] = "The Google sheet does not have a description field."
        stats['proficiencyBonus'] = int(character.acell("H14").value)
        stats['image'] = character.acell("C176").value
        
        index = 15
        for stat in ('strength', 'dexterity', 'constitution', 'wisdom', 'intelligence', 'charisma'):
            try:
                stats[stat] = int(character.acell("C" + str(index)).value)
                stats[stat + 'Mod'] = int(character.acell("C" + str(index-2)).value)
                index += 5
            except TypeError:
                raise MissingAttribute(stat)
        
        return stats
            
    def get_attack(self, atkIn):
        """Calculates and returns a dict."""
        if self.character is None: raise Exception('You must call get_character() first.')
        character = self.character
        attack = {'attackBonus': '0', 'damage':'0', 'name': ''}
        name_index = "R" + str(32 + atkIn)
        bonus_index = "Y" + str(32 + atkIn)
        damage_index = "AC" + str(32 + atkIn)
        
        attack['name'] = character.acell(name_index).value
        attack['attackBonus'] = character.acell(bonus_index).value
        attack['damage'] = character.acell(damage_index).value
        
        if attack['name'] is "":
            return None
        if attack['damage'] is "":
            attack['damage'] = None
        
        attack['attackBonus'] = attack['attackBonus'].replace('+', '', 1) if attack['attackBonus'] is not None else None
        
        return attack
        
    def get_attacks(self):
        """Returns a list of dicts of all of the character's attacks."""
        if self.character is None: raise Exception('You must call get_character() first.')
        attacks = []
        for attack in range(5):
            a = self.get_attack(attack)
            if a is not None: attacks.append(a)
        return attacks
            
    def get_skills(self):
        """Returns a dict of all the character's skills."""
        if self.character is None: raise Exception('You must call get_character() first.')
        character = self.character
        skillslist = ['I25', 'I26', 'I27', 'I28',
                      'I22', 'I19', 'I29', 'I18',
                      'I30', 'V12', 'I31', 'I20',
                      'I32', 'I33', 'I34', 'I35',
                      'I36', 'I37', 'I38', 'I39',
                      'I40', 'I41', 'I17', 'I42', 'I21',
                      'C13', 'C18', 'C23', 'C33', 'C28', 'C38']
        skillsMap = ['acrobatics', 'animalHandling', 'arcana', 'athletics',
                     'charismaSave', 'constitutionSave', 'deception', 'dexteritySave',
                     'history', 'initiative', 'insight', 'intelligenceSave',
                     'intimidation', 'investigation', 'medicine', 'nature',
                     'perception', 'performance', 'persuasion', 'religion',
                     'sleightOfHand', 'stealth', 'strengthSave', 'survival', 'wisdomSave',
                     'strength', 'dexterity', 'constitution', 'wisdom', 'intelligence', 'charisma']
        skills = {}
        for index, skill in enumerate(skillslist):
            skills[skillsMap[index]] = int(character.acell(skill).value)
        
        return skills
    
    def get_level(self):
        if self.character is None: raise Exception('You must call get_character() first.')
        character = self.character
        level = int(character.acell("AL6").value)
        return level
    
    
    