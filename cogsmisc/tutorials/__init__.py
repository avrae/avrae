"""
Main entrypoint for the tutorials extension. The tutorials themselves can be found in this module, and
are registered here. The tutorial commands are also registered here, as part of the Help cog.
"""
from discord.ext import commands


class Tutorials(commands.Cog):
    """
    Commands to help learn how to use the bot.
    """

    def __init__(self, bot):
        self.bot = bot

    @commands.group()
    async def tutorial(self, ctx):
        """Shows the current tutorial objective, or lists the available tutorials if one is not active."""
        pass

    @tutorial.command(name='skip')
    async def tutorial_skip(self, ctx):
        """Skips the current objective, and moves on to the next part of the tutorial."""
        pass

    @tutorial.command(name='end')
    async def tutorial_end(self, ctx):
        """Ends the current tutorial."""
        pass


def setup(bot):
    cog = Tutorials(bot)
    bot.add_cog(cog)
    bot.help_command.cog = cog
