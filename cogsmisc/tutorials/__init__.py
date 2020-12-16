"""
Main entrypoint for the tutorials extension. The tutorials themselves can be found in this module, and
are registered here. The tutorial commands are also registered here, as part of the Help cog.
"""
from discord.ext import commands

from .example import ExampleTutorial


class Tutorials(commands.Cog):
    """
    Commands to help learn how to use the bot.
    """

    tutorials = {
        "test_example": ExampleTutorial()
    }

    def __init__(self, bot):
        self.bot = bot

    @commands.group()
    async def tutorial(self, ctx):
        """Shows the current tutorial objective, or lists the available tutorials if one is not active."""
        # get user map
        # if tutorial is none:
        #   list available
        # else:
        #   get tutorial state
        #   if none:
        #       error
        #   run tutorial state objective
        pass

    @tutorial.command(name='skip')
    async def tutorial_skip(self, ctx):
        """Skips the current objective, and moves on to the next part of the tutorial."""
        # confirm
        # run tutorial state transition
        # commit new state map
        pass

    @tutorial.command(name='end')
    async def tutorial_end(self, ctx):
        """Ends the current tutorial."""
        # confirm
        # delete tutorial state map
        pass

    # main listener entrypoint
    @commands.Cog.listener()
    async def on_command_completion(self, ctx):
        # get user map
        # get tutorial
        # if none:
        #   error
        # get tutorial state
        # if none:
        #   error
        # run tutorial state listener
        # commit new state map if needed (how to handle transition?)
        pass


def setup(bot):
    cog = Tutorials(bot)
    bot.add_cog(cog)
    bot.help_command.cog = cog
