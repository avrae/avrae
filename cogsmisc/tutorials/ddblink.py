"""
This is an example tutorial not designed to be run. It demonstrates how to use tutorial states and can be used
as a stub to build new tutorials from.
"""
import asyncio

from .models import Tutorial, TutorialEmbed, TutorialState, state


class DDBLink(Tutorial):
    name = "D&D Beyond Link"
    description = """
    *5 minutes*
    Learn how to link your D&D Beyond and Discord accounts to use your D&D Beyond content in Avrae, import your \
    private characters, sync rolls with your D&D Beyond campaign, and more!
    """

    @state(first=True)
    class LinkingYourAccount(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Linking Your Account"
            embed.description = f"""
            Did you know you can use all your D&D Beyond content in Avrae for free?  It's pretty easy to set up!

            First, visit your [Account Settings](https://www.dndbeyond.com/account) page in D&D Beyond.  You'll see \
            an option there to link your Discord account. Make sure you’re logged in with the correct Discord account \
            when you do so.
            
            Once that's done, come back here and use `{ctx.prefix}ddb` to confirm.
            ```
            {ctx.prefix}ddb
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.command is ctx.bot.get_command('ddb'):
                user = await ctx.bot.ddb.get_ddb_user(ctx, ctx.author.id)
                if user is None:
                    embed = TutorialEmbed(self, ctx)
                    embed.description = f"""
                    Looks like your D&D Beyond account isn't connected yet. Make sure you’re logged in with the \
                    correct Discord account, and check again in a few minutes!
                    """
                    await ctx.send(embed=embed)
                else:
                    await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            await state_map.transition(ctx, self.tutorial.ContentLookup)

    @state()
    class ContentLookup(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Content Lookup"
            embed.description = f"""
            Now that you’re set up, let’s try it out!  Use `{ctx.prefix}spell <name>` to look up a spell. Avrae will \
            give you the full details for any spell you have [in D&D Beyond](https://www.dndbeyond.com/spells).
            ```
            {ctx.prefix}spell <name>
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.command is ctx.bot.get_command('spell'):
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.description = f"""
            You got it!  If you’re a spellcaster, now you can even cast `{ctx.prefix}cast` those spells, too. \
            It also works with all of the other lookup commands as well, like `{ctx.prefix}monster`,  \
            `{ctx.prefix}item`, or  `{ctx.prefix}feat`.

            Plus, you can share the fun with the rest of your party using D&D Beyond's \
            [Campaign Content Sharing](https://dndbeyond.zendesk.com/hc/en-us/articles/115011257067-Campaign-Content-Sharing-and-You). \
            That lets the whole group share their unlocked game content with each other, and it works here in Avrae, \
            too!
            """
            await ctx.send(embed=embed)
            await state_map.end_tutorial(ctx)
