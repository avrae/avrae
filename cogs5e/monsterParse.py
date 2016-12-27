import asyncio
import json
import math

import discord
from discord.ext import commands

from functions import *


class MonsterParser:
    """Monster lookup."""
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command(pass_context=True)
    async def monster(self, ctx, *, monstername : str):
        """Looks up a monster.
        Requires role 'DM' or 'Game Master' to show full stat block.
        Shows Beasts if you have the role 'Druid'."""
        
        result = self.searchMonster(monstername, ctx, False)
    
        # do stuff here
        for r in result:
            await self.bot.say(r)
            
    @commands.command(pass_context=True)
    async def vmonster(self, ctx, *, monstername : str):
        """Looks up a monster, including all of its skills.
        Requires role 'DM' or 'Game Master' to show full stat block.
        Shows Beasts if you have the role 'Druid'."""
        
        result = self.searchMonster(monstername, ctx, True)
    
        # do stuff here
        for r in result:
            await self.bot.say(r)
    
    def searchMonster(self, monstername, ctx, verbose):
        with open('./res/monsters.json', 'r') as f:
            monsters = json.load(f)
        
        monsterDesc = []
        visible = False
    
        try:
            monster = next(item for item in monsters if item["name"].upper() == monstername.upper())
        except Exception:
            monsterDesc.append("Monster does not exist or is misspelled.")
            return monsterDesc
        
        visible_roles = ['dm', 'game master', 'dungeon master', 'gm']
        
        for ro in visible_roles:
            if ro in (str(r).lower() for r in ctx.message.author.roles):
                visible = True
        if 'druid' in (str(r).lower() for r in ctx.message.author.roles) and monster['type'] == 'beast':
            visible = True
        
        if visible:
                
            monster['hit_dice_and_con'] = monster['hit_dice'] + ' + {}'.format(str(math.floor((int(monster['constitution'])-10)/2) * int(monster['hit_dice'].split('d')[0])))
            
            for stat in ["strength", "dexterity", "constitution", "wisdom", "intelligence", "charisma"]:
                monster["{}_mod".format(stat)] = math.floor((monster[stat]-10)/2)
                monster[stat] = "{0} ({1:+})".format(monster[stat], math.floor((monster[stat]-10)/2))
                
            for save in ["strength", "dexterity", "constitution", "wisdom", "intelligence", "charisma"]:
                if "{}_save".format(save) not in monster:
                    monster["{}_save".format(save)] = monster["{}_mod".format(save)]
                    
            for str_skill in ["athletics"]:
                if str_skill not in monster:
                    monster[str_skill] = monster["strength_mod"]
                    
            for dex_skill in ["acrobatics", "sleight_of_hand", "stealth"]:
                if dex_skill not in monster:
                    monster[dex_skill] = monster["dexterity_mod"]
                    
            for con_skill in []:
                if con_skill not in monster:
                    monster[con_skill] = monster["constitution_mod"]
                    
            for int_skill in ["arcana", "history", "investigation", "nature", "religion"]:
                if int_skill not in monster:
                    monster[int_skill] = monster["intelligence_mod"]
                    
            for wis_skill in ["animal_handling", "insight", "medicine", "perception", "survival"]:
                if wis_skill not in monster:
                    monster[wis_skill] = monster["wisdom_mod"]
                    
            for cha_skill in ["deception", "intimidation", "performance", "persuasion"]:
                if cha_skill not in monster:
                    monster[cha_skill] = monster["charisma_mod"]
                    
            
            monsterDesc.append("{name}, {size} {type}. {alignment}.\n**AC:** {armor_class}.\n**HP:** {hit_points} ({hit_dice_and_con}).\n**Speed:** {speed}\n".format(**monster))
            if not verbose:
                monsterDesc.append("**STR:** {strength} **DEX:** {dexterity} **CON:** {constitution} **WIS:** {wisdom} **INT:** {intelligence} **CHA:** {charisma}\n".format(**monster))
            else:
                monsterDesc.append('```markdown\n')
                monsterDesc.append(print_table([("**STR:** {strength}".format(**monster), "**DEX:** {dexterity}".format(**monster), "**CON:** {constitution}".format(**monster)),
                                                ("- Save: {strength_save:+}".format(**monster), "- Save: {dexterity_save:+}".format(**monster), "- Save: {constitution_save:+}".format(**monster)),
                                                ("- Athletics: {athletics:+}".format(**monster), "- Acrobatics: {acrobatics:+}".format(**monster), ""),
                                                ("", "- SoH: {sleight_of_hand:+}".format(**monster), ""),
                                                ("", "- Stealth: {stealth:+}".format(**monster), "")]))
                monsterDesc.append('\n')
                monsterDesc.append(print_table([("**INT:** {intelligence}".format(**monster), "**WIS:** {wisdom}".format(**monster), "**CHA:** {charisma}".format(**monster)),
                                                ("- Save: {intelligence_save:+}".format(**monster), "- Save: {wisdom_save:+}".format(**monster), "- Save: {charisma_save:+}".format(**monster)),
                                                ("- Arcana: {arcana:+}".format(**monster), "- A. Handling: {animal_handling:+}".format(**monster), "- Deception: {deception:+}".format(**monster)),
                                                ("- History: {history:+}".format(**monster), "- Insight: {insight:+}".format(**monster), "- Intimid.: {intimidation:+}".format(**monster)),
                                                ("- Invest.: {investigation:+}".format(**monster), "- Medicine: {medicine:+}".format(**monster), "- Perf.: {performance:+}".format(**monster)),
                                                ("- Nature: {nature:+}".format(**monster), "- Perception: {perception:+}".format(**monster), "- Persuasion: {persuasion:+}".format(**monster)),
                                                ("- Religion: {religion:+}".format(**monster), "- Survival: {survival:+}".format(**monster), "")]))
                monsterDesc.append('\n```')
#                 monsterDesc.append("**STR:** {strength}\n|- Athletics: {athletics:+}\n".format(**monster))
#                 monsterDesc.append("**DEX:** {dexterity}\n|- Acrobatics: {acrobatics:+}\n|- Sleight of Hand: {sleight_of_hand:+}\n|- Stealth: {stealth:+}\n".format(**monster))
#                 monsterDesc.append("**CON:** {constitution}\n".format(**monster))
#                 monsterDesc.append("**INT:** {intelligence}\n|- Arcana: {arcana:+}\n|- History: {history:+}\n|- Investigation: {investigation:+}\n|- Nature: {nature:+}\n|- Religion: {religion:+}\n".format(**monster))
#                 monsterDesc.append("**WIS:** {wisdom}\n|- Animal Handling: {animal_handling:+}\n|- Insight: {insight:+}\n|- Medicine: {medicine:+}\n|- Perception: {perception:+}\n|- Survival: {survival:+}\n".format(**monster))
#                 monsterDesc.append("**CHA:** {charisma}\n|- Deception: {deception:+}\n|- Intimidation: {intimidation:+}\n|- Performance: {performance:+}\n|- Persuasion: {persuasion:+}\n".format(**monster))
            monsterDesc.append("**Senses:** {senses}.\n**Vulnerabilities:** {damage_vulnerabilities}\n**Resistances:** {damage_resistances}\n**Damage Immunities:** {damage_immunities}\n**Condition Immunities:** {condition_immunities}\n**Languages:** {languages}\n**CR:** {challenge_rating}\n".format(**monster))
            
            if "special_abilities" in monster:
                monsterDesc.append("\n**__Special Abilities:__**\n")
                for a in monster["special_abilities"]:
                    monsterDesc.append("**{name}:** {desc}\n".format(**a))
            
            monsterDesc.append("\n**__Actions:__**\n")
            for a in monster["actions"]:      
                monsterDesc.append("**{name}:** {desc}\n".format(**a))
                
            if "reactions" in monster:
                monsterDesc.append("\n**__Reactions:__**\n")
                for a in monster["reactions"]:
                    monsterDesc.append("**{name}:** {desc}\n".format(**a))
                
            if "legendary_actions" in monster:
                monsterDesc.append("\n**__Legendary Actions:__**\n")
                for a in monster["legendary_actions"]:
                    monsterDesc.append("**{name}:** {desc}\n".format(**a))
        else:
            if monster["hit_points"] < 10:
                monster["hit_points"] = "Very Low"
            elif 10 <= monster["hit_points"] < 50:
                monster["hit_points"] = "Low"
            elif 50 <= monster["hit_points"] < 100:
                monster["hit_points"] = "Medium"
            elif 100 <= monster["hit_points"] < 200:
                monster["hit_points"] = "High"
            elif 200 <= monster["hit_points"] < 400:
                monster["hit_points"] = "Very High"
            elif 400 <= monster["hit_points"]:
                monster["hit_points"] = "Godly"
                
            if monster["armor_class"] < 6:
                monster["armor_class"] = "Very Low"
            elif 6 <= monster["armor_class"] < 9:
                monster["armor_class"] = "Low"
            elif 9 <= monster["armor_class"] < 15:
                monster["armor_class"] = "Medium"
            elif 15 <= monster["armor_class"] < 17:
                monster["armor_class"] = "High"
            elif 17 <= monster["armor_class"] < 22:
                monster["armor_class"] = "Very High"
            elif 22 <= monster["armor_class"]:
                monster["armor_class"] = "Godly"
                
            for stat in ["strength", "dexterity", "constitution", "wisdom", "intelligence", "charisma"]:
                if monster[stat] <= 3:
                    monster[stat] = "Very Low"
                elif 3 < monster[stat] <= 7:
                    monster[stat] = "Low"
                elif 7 < monster[stat] <= 15:
                    monster[stat] = "Medium"
                elif 15 < monster[stat] <= 21:
                    monster[stat] = "High"
                elif 21 < monster[stat] <= 26:
                    monster[stat] = "Very High"
                elif 26 < monster[stat]:
                    monster[stat] = "Godly"
                    
            if monster["languages"]:
                monster["languages"] = len(monster["languages"].split(", "))
            else:
                monster["languages"] = 0
            
            monsterDesc.append("{name}, {size} {type}.\n**AC:** {armor_class}.\n**HP:** {hit_points}.\n**Speed:** {speed}\n**STR:** {strength} **DEX:** {dexterity} **CON:** {constitution} **WIS:** {wisdom} **INT:** {intelligence} **CHA:** {charisma}\n**Languages:** {languages}\n".format(**monster))
            
            if "special_abilities" in monster:
                monsterDesc.append("**__Special Abilities:__** " + str(len(monster["special_abilities"])) + "\n")
            
            monsterDesc.append("**__Actions:__** " + str(len(monster["actions"])) + "\n")
            
            if "reactions" in monster:
                monsterDesc.append("**__Reactions:__** " + str(len(monster["reactions"])) + "\n")
                
            if "legendary_actions" in monster:
                monsterDesc.append("**__Legendary Actions:__** " + str(len(monster["legendary_actions"])) + "\n")
                    
        tempStr = ""
        for m in monsterDesc:
            tempStr += m
        
        
        
        return discord_trim(tempStr)
    
    
    
    
