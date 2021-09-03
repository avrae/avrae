from cogs5e.models.errors import NoCharacter
from .models import Tutorial, TutorialEmbed, TutorialState, state


class DDBLink(Tutorial):
    name = "D&D Beyond Link"
    description = """
    *5 minutes*
    Learn how to link your D&D Beyond and Discord accounts to use your D&D Beyond content in Avrae, import your private characters, sync rolls with your D&D Beyond campaign, and more!
    """

    @state(first=True)
    class LinkingYourAccount(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Linking Your Account"
            embed.description = f"""
            Did you know you can use all your D&D Beyond content in Avrae for free?  It's pretty easy to set up!

            First, visit your [Account Settings](https://www.dndbeyond.com/account) page in D&D Beyond.  You'll see an option there to link your Discord account. Make sure you’re logged in with the correct Discord account when you do so.
            
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
                    Looks like your D&D Beyond account isn't connected yet. Make sure you’re logged in with the correct Discord account, and check again in a few minutes!
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
            Now that you’re set up, let’s try it out!  Use `{ctx.prefix}spell <name>` to look up a spell. Avrae will give you the full details for any spell you have [in D&D Beyond](https://www.dndbeyond.com/spells).
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
            You got it!  If you’re a spellcaster, now you can even cast `{ctx.prefix}cast` those spells, too. It also works with all of the other lookup commands as well, like `{ctx.prefix}monster`,  `{ctx.prefix}item`, or  `{ctx.prefix}feat`.

            Plus, you can share the fun with the rest of your party using D&D Beyond's [Campaign Content Sharing](https://dndbeyond.zendesk.com/hc/en-us/articles/115011257067-Campaign-Content-Sharing-and-You). That lets the whole group share their unlocked game content with each other, and it works here in Avrae, too!
            """
            await ctx.send(embed=embed)
            try:
                await ctx.get_character()
                await state_map.transition_with_delay(ctx, self.tutorial.CampaignLink, 5)
            except NoCharacter:
                await state_map.transition_with_delay(ctx, self.tutorial.ImportCharacter, 5)

    @state()
    class ImportCharacter(TutorialState):  # copied from quickstart
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Importing a Character"
            embed.description = f"""
            Now, let's import a character and get started with Avrae's automated attacks, skill checks, and ability saves! First, go ahead and make a character on [D&D Beyond](https://www.dndbeyond.com/?utm_source=avrae&utm_medium=tutorial).

            Once you're ready, import the character into Avrae with the command `{ctx.prefix}beyond <url>`, using either the "Sharable Link" on your character sheet or the URL in the address bar of your browser.
            ```
            {ctx.prefix}import <url>
            ```
            Or, if you've already imported a character, switch to them now using `{ctx.prefix}character <name>`!
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            try:
                character = await ctx.get_character()
            except NoCharacter:
                return
            if ctx.command in (ctx.bot.get_command('import'),
                               ctx.bot.get_command('beyond'),
                               ctx.bot.get_command('update'),
                               ctx.bot.get_command('char')) \
                    and character is not None:
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            character = await ctx.get_character()

            embed = TutorialEmbed(self, ctx)
            embed.description = f"""
            Nice to meet you, {character.name}! Avrae has no limit on how many characters you can import, but you can only have one "active" at a time across all servers. To switch between active characters, use `{ctx.prefix}character <name>`.

            Also, if you change your character's character sheet, Avrae will need to be updated to know about those changes. Whenever you do so, make sure to run `{ctx.prefix}update` to update your active character!
            """
            await ctx.send(embed=embed)
            await state_map.transition_with_delay(ctx, self.tutorial.CampaignLink, 5)

    @state()
    class CampaignLink(TutorialState):
        async def objective(self, ctx, state_map):
            character = await ctx.get_character()

            embed = TutorialEmbed(self, ctx)
            embed.title = "Campaign Link"
            embed.description = f"""
            If {character.name} is assigned to a D&D Beyond campaign, it gets even better!  The DM for that campaign can link it to a specific Discord channel by using `{ctx.prefix}campaign [campaign_link]` in that channel.  This will tie that channel to your campaign’s Game Log.
            
            After that, any rolls you make here in Avrae will show up in real time in the Game Log.  Plus, any digital dice rolls on your character sheet in D&D Beyond will also be sent to the Game Log, and back to your Discord channel as well!
            
            Once your campaign is linked, let’s make a stealth check and see it in action.
            ```
            {ctx.prefix}check stealth
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.command is ctx.bot.get_command('check'):
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.description = f"""
            Did you see it in the Game Log already?  If you need help finding it, try going to your campaign page and clicking the Game Log button at the top of the page.  Your stealth check should already be there waiting for you.
            
            While you’re there, try rolling some digital dice on your character sheet, too.  You’ll see them show up in your Discord channel just as though you’d rolled them in Avrae.
            
            Happy rolling!
            """
            embed.set_image(url="https://media.avrae.io/tutorial-assets/ddblink/CampaignLinkTransition.gif")
            embed.set_footer(text=f"{self.tutorial.name} | Tutorial complete!")
            await ctx.send(embed=embed)
            await state_map.end_tutorial(ctx)
