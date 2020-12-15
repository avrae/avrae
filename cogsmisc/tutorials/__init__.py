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


def setup(bot):
    cog = Tutorials(bot)
    bot.add_cog(cog)
    bot.help_command.cog = cog
