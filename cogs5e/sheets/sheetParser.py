"""
Created on Feb 14, 2017

@author: andrew
"""
import random
import re

import discord
import numexpr


class SheetParser():
    
    def __init__(self, sheet):
        self.sheet = sheet
    
    def get_character(self):
        return
    
    def get_sheet(self):
        return
    
    def get_embed(self):
        sheet = self.sheet
        stats = sheet['stats']
        hp = sheet['hp']
        levels = sheet['levels']
        skills = sheet['skills']
        attacks = sheet['attacks']
        saves = sheet['saves']
        armor = sheet['armor']
        resistStr = ''
        try:
            resist= sheet['resist']
            immune= sheet['immune']
            vuln  = sheet['vuln']
            if len(resist) > 0:
                resistStr += "\nResistances: " + ', '.join(resist).title()
            if len(immune) > 0:
                resistStr += "\nImmunities: " + ', '.join(immune).title()
            if len(vuln) > 0:
                resistStr += "\nVulnerabilities: " + ', '.join(vuln).title()
        except KeyError:
            resistStr = "\nPlease update your sheet to view resistances."
        embed = discord.Embed()
        embed.colour = random.randint(0, 0xffffff)
        embed.title = stats['name']
        embed.set_thumbnail(url=stats['image'])
        embed.add_field(name="HP/Level", value="**HP:** {}\nLevel {}".format(hp, levels['level']) + resistStr)
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
            if a['attackBonus'] is not None:
                try:
                    bonus = numexpr.evaluate(a['attackBonus'])
                except:
                    bonus = a['attackBonus']
                tempAttacks.append("**{0}:** +{1} To Hit, {2} damage.".format(a['name'],
                                                                              bonus,
                                                                              a['damage'] if a['damage'] is not None else 'no'))
            else:
                tempAttacks.append("**{0}:** {1} damage.".format(a['name'],
                                                                 a['damage'] if a['damage'] is not None else 'no'))
        if tempAttacks == []:
            tempAttacks = ['No attacks.']
        a = '\n'.join(tempAttacks)
        if len(a) > 1023:
            a = ', '.join(atk['name'] for atk in attacks)
        if len(a) > 1023:
            a = "Too many attacks, values hidden!"
        embed.add_field(name="Attacks", value=a)
        
        return embed