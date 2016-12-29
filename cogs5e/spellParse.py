import json

import discord
from discord.ext import commands

from utils import checks
from cogs5e import tables
from functions import discord_trim


class SpellParser:
    """Spell lookup."""
    def __init__(self, bot):
        self.bot = bot
        self.teachers = []
        with open('./res/spells.json', 'r') as f:
            self.spells = json.load(f)
        
        
    @commands.command(pass_context=True)
    async def spell(self, ctx, *, args : str):
        """Looks up a spell."""
        valid_args = {'--class', '--level', '--school'}
        result = self.searchSpell(args)

        # do stuff here
        for r in result:
            await self.bot.say(r)
            

    def searchSpell(self, spellname):
        spellDesc = []
        
        if spellname.upper() == 'All'.upper():
            spellDesc.append(tables.getAllSpellMessage())
            return spellDesc
    
        try:
            spell = next(item for item in self.spells if item["name"].upper() == spellname.upper())
        except Exception:
            spellDesc.append("Spell does not exist or is misspelled (ha).")
            return spellDesc
        
        if "ritual" not in spell:
            spell["ritual"] = "?"
    
        if "material" in spell:
            spellDesc.append("{name}, {level} {school}. ({class})\n**Casting Time:** {casting_time}\n**Range:** {range}\n**Components:** {components}\n**Material Requirement:** {material}\n**Duration:** {duration}\n**Concentration:** {concentration}\n**Ritual:** {ritual}".format(**spell))
        else:
            spellDesc.append("{name}, {level} {school}. ({class})\n**Casting Time:** {casting_time}\n**Range:** {range}\n**Components:** {components}\n**Duration:** {duration}\n**Concentration:** {concentration}\n**Ritual:** {ritual}".format(**spell))
    
        for a in spell["desc"].split("<p>"):
            if a:
                spellDesc.append(a.replace("</p>", "").replace("<b>", "**").replace("</b>", "**"))
    
        if "higher_level" in spell:
            spellDesc.append("**At Higher Levels:** " + spell["higher_level"].replace("<p>", "").replace("</p>", ""))
            
        tempStr = ""
        for m in spellDesc:
            tempStr += m
            tempStr += "\n"
            
        return discord_trim(tempStr)
    
    #print(searchSpell("Wish"))
