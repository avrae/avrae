"""
Main entrypoint for the tutorials extension. The tutorials themselves can be found in this module, and
are registered here. The tutorial commands are also registered here, as part of the Help cog.
"""
from discord.ext import commands

from cogs5e.models.embeds import EmbedWithAuthor
from utils.functions import confirm, search_and_select
from .example import ExampleTutorial
from .models import TutorialStateMap


class Tutorials(commands.Cog):
    """
    Commands to help learn how to use the bot.
    """

    # tutorial keys should never change - if needed, change the name in the constructor to change the display name
    tutorials = {
        "test_example": ExampleTutorial(name="example", description="this is an example tutorial")
    }

    def __init__(self, bot):
        self.bot = bot

    # ==== commands ====
    @commands.group(invoke_without_command=True)
    async def tutorial(self, ctx, name=None):
        """
        Shows the current tutorial objective, lists the available tutorials if one is not active, or begins a new tutorial.
        """
        # get user map
        user_state = await TutorialStateMap.from_ctx(ctx)

        if user_state is not None:
            tutorial, state = self.get_tutorial_and_state(user_state)
            if tutorial is None or state is None:
                await ctx.send(f"The tutorial you were running no longer exists. "
                               f"Please run `{ctx.prefix}tutorial end` to start a new tutorial!")
                return
            # show tutorial state objective
            await state.objective(ctx, user_state)
        elif name is not None:
            # begin tutorial with name
            key, tutorial = await search_and_select(ctx, list(self.tutorials.items()), name, lambda tup: tup[1].name)
            new_state = TutorialStateMap.new(ctx, key, tutorial)
            await new_state.transition(ctx, tutorial.first_state)
        else:
            # list available tutorials
            await self.tutorial_list(ctx)

    @tutorial.command(name='list')
    async def tutorial_list(self, ctx):
        """Lists the available tutorials."""
        embed = EmbedWithAuthor(ctx)
        embed.title = "Available Tutorials"
        embed.description = f"Use `{ctx.prefix}tutorial <name>` to select a tutorial from the ones available below!"
        for tutorial in self.tutorials.values():
            embed.add_field(name=tutorial.name, value=tutorial.description, inline=False)
        await ctx.send(embed=embed)

    @tutorial.command(name='skip')
    async def tutorial_skip(self, ctx):
        """Skips the current objective, and moves on to the next part of the tutorial."""
        user_state = await TutorialStateMap.from_ctx(ctx)
        if user_state is None:
            return await ctx.send("You are not currently running a tutorial.")
        tutorial, state = self.get_tutorial_and_state(user_state)
        if tutorial is None or state is None:
            return await ctx.send(f"The tutorial you were running no longer exists. "
                                  f"Please run `{ctx.prefix}tutorial end` to start a new tutorial!")
        # confirm
        result = await confirm(ctx, "Are you sure you want to skip the current tutorial objective?")
        if not result:
            return await ctx.send("Ok, aborting.")
        # run tutorial state transition
        # commit new state map
        await state.transition(ctx, user_state)

    @tutorial.command(name='end')
    async def tutorial_end(self, ctx):
        """Ends the current tutorial."""
        user_state = await TutorialStateMap.from_ctx(ctx)
        if user_state is None:
            return await ctx.send("You are not currently running a tutorial.")
        # confirm
        result = await confirm(ctx, "Are you sure you want to end the current tutorial?")
        if not result:
            return await ctx.send("Ok, aborting.")
        # delete tutorial state map
        await user_state.end_tutorial(ctx)
        await ctx.send("Ok, ended the tutorial.")

    # ==== main listener entrypoint ====
    @commands.Cog.listener()
    async def on_command_completion(self, ctx):
        # get user map
        user_state = await TutorialStateMap.from_ctx(ctx)
        if user_state is None:
            return
        tutorial, state = self.get_tutorial_and_state(user_state)
        if tutorial is None or state is None:
            return

        # run tutorial state listener
        await state.listener(ctx, user_state)

    # ==== helpers ====
    def get_tutorial_and_state(self, user_state):
        tutorial = self.tutorials.get(user_state.tutorial_key)
        if tutorial is None:
            return None, None
        state = tutorial.states.get(user_state.state_key)
        return tutorial, state


# discord ext boilerplate
def setup(bot):
    cog = Tutorials(bot)
    bot.add_cog(cog)
    bot.help_command.cog = cog
