"""
This is an example tutorial not designed to be run. It demonstrates how to use tutorial states and can be used
as a stub to build new tutorials from.
"""

from .models import Tutorial, TutorialState, state


class ExampleTutorial(Tutorial):
    name = "Example"
    description = """
    *9001 minutes*
    These are some words about what this tutorial is
    """

    @state()
    class FirstState(TutorialState):
        async def objective(self, ctx, state_map):
            await ctx.send("FirstState objective - run echo to move on")

        async def listener(self, ctx, state_map):
            await ctx.send("FirstState listener")
            if ctx.command is ctx.bot.get_command("echo"):
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            await ctx.send("FirstState transition")
            await state_map.transition(ctx, self.tutorial.SecondState)

    @state()
    class SecondState(TutorialState):
        async def objective(self, ctx, state_map):
            await ctx.send("SecondState objective - run attack to move on")

        async def listener(self, ctx, state_map):
            await ctx.send("SecondState listener")
            if ctx.command is ctx.bot.get_command("attack"):
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            await ctx.send("SecondState transition")
            await state_map.end_tutorial(ctx)
