'''
Created on Nov 29, 2016

@author: andrew
'''

import asyncio
import discord
import json
from discord.ext import commands
from functions import discord_trim

class Lookup:
    """Commands to help look up items (WIP), status effects, rules, etc."""
    
    def __init__(self, bot):
        self.bot = bot
        with open('./res/conditions.json', 'r') as f:
            self.conditions = json.load(f)
            
    @commands.command(pass_context=True)
    async def condition(self, ctx, *, name : str):
        """Looks up a condition."""
        result = self.searchCondition(name)
        
        conName = result['name']
        conHeader = '-' * len(conName)
        conDesc = result['desc']
        out = "```markdown\n{0}\n{1}\n{2}```".format(conName, conHeader, conDesc)

        # do stuff here
        for r in discord_trim(out):
            await self.bot.say(r)
            
    def searchCondition(self, condition):
        condition = next(c for c in self.conditions if c['name'].lower() == condition.lower())
        return condition