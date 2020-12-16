from .models import Tutorial, TutorialState, state


class ExampleTutorial(Tutorial):
    @state()
    class FirstState(TutorialState):
        async def listener(self, ctx, state_map):
            await ctx.send("FirstState listener")

        async def objective(self, ctx, state_map):
            await ctx.send("FirstState objective")

        async def transition(self, ctx, state_map):
            await ctx.send("FirstState transition")
            await state_map.transition(self.tutorial.SecondState)

    @state()
    class SecondState(TutorialState):
        async def listener(self, ctx, state_map):
            await ctx.send("SecondState listener")

        async def objective(self, ctx, state_map):
            await ctx.send("SecondState objective")

        async def transition(self, ctx, state_map):
            await ctx.send("SecondState transition")
            return None
