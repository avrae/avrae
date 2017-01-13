'''
Created on Jan 13, 2017

@author: andrew
'''
from discord.ext import commands

class PBPUtils:
    """Commands to help streamline playing-by-post over Discord."""
    
    def __init__(self, bot):
        self.bot = bot
        
    @commands.command(pass_context=True)
    async def br(self, ctx):
        """Prints a scene break."""
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass
        
        await self.bot.say("```" + '-'*50 + "```")