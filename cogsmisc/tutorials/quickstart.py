import asyncio

from cogs5e.models.character import Character
from cogs5e.models.errors import NoCharacter
from utils import config
from .models import Tutorial, TutorialEmbed, TutorialState, checklist, state


class Quickstart(Tutorial):
    name = "Quickstart"
    description = """
    *10 minutes*
    New to Avrae or Discord bots in general? This tutorial will help you get started with Avrae's command system, \
    rolling dice, and importing a D&D Beyond character into Discord.
    """

    @state(first=True)
    class Start(TutorialState):
        async def objective(self, ctx, state_map):
            # does the server have a custom prefix?
            server_prefix_override = ""
            if ctx.prefix != config.DEFAULT_PREFIX:
                server_prefix_override = f", but on this server it is `{ctx.prefix}`"

            embed = TutorialEmbed(self, ctx)
            embed.title = "Using Bot Commands"
            embed.description = f"""
            Each command in Avrae starts with a *prefix*, or a short string of symbols at the start of a message. By \
            default, this prefix is `{config.DEFAULT_PREFIX}`{server_prefix_override}. Avrae will only start a command \
            if a message starts with this prefix.
            
            To use a command in Avrae, type the prefix, then the name of the command. For example, to roll a d20, send \
            a message containing `{ctx.prefix}roll d20`. Try it now!
            ```
            {ctx.prefix}roll d20
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.command is ctx.bot.get_command('roll') and 'd20' in ctx.message.content:
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.description = f"""
            Great! As you might have guessed, `{ctx.prefix}roll <dice>` is the command to roll some dice. Throughout \
            the rest of this tutorial and other tutorials, we'll show commands in code blocks like that. 
            
            When you see something like `<dice>` or `[dice]`, this is called an *argument*: it means you can put some \
            input there, like the dice you want to roll. Arguments like `<this>` are required, and arguments like \
            `[this]` are optional.
            """
            await ctx.send(embed=embed)
            await ctx.trigger_typing()
            await asyncio.sleep(5)
            await state_map.transition(ctx, self.tutorial.ImportCharacter)

    @state()
    class ImportCharacter(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Importing a Character"
            embed.description = f"""
            Now, let's import a character and get started with Avrae's automated attacks, skill checks, and ability \
            saves! First, go ahead and make a character on \
            [D&D Beyond](https://www.dndbeyond.com/?utm_source=avrae&utm_medium=tutorial).
            
            Once you're ready, import the character into Avrae with the command `{ctx.prefix}beyond <url>`, using \
            either the "Sharable Link" on your character sheet or the URL in the address bar of your browser.
            ```
            {ctx.prefix}beyond <url>
            ```
            Or, if you've already imported a character, switch to them now!
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            try:
                character = await Character.from_ctx(ctx)
            except NoCharacter:
                return
            if ctx.command in (ctx.bot.get_command('beyond'),
                               ctx.bot.get_command('dicecloud'),
                               ctx.bot.get_command('gsheet'),
                               ctx.bot.get_command('update'),
                               ctx.bot.get_command('char')) \
                    and character is not None:
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            # should be active from listener, and in cache
            # eventually this should get replaced by ctx.character
            character = await Character.from_ctx(ctx)

            embed = TutorialEmbed(self, ctx)
            embed.description = f"""
            Nice to meet you, {character.name}! Avrae has no limit on how many characters you can import, but you can \
            only have one "active" at a time. To switch between active characters, use `{ctx.prefix}character <name>`.
            
            Also, if you change your character's character sheet, Avrae will need to be updated to know about those \
            changes. Whenever you do so, make sure to run `{ctx.prefix}update` to update your active character!
            """
            await ctx.send(embed=embed)
            await ctx.trigger_typing()
            await asyncio.sleep(5)
            await state_map.transition(ctx, self.tutorial.ChecksAttacksSaves)

    @state()
    class ChecksAttacksSaves(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Checks, Saves, and Attacks"
            embed.description = f"""
            Finally, let's go over the three most important rolls in D&D: skill checks, saving throws, and attacks. \
            Now that your character is saved in Avrae, you can easily make these three rolls with simple commands: \
            `{ctx.prefix}check <skill>`, `{ctx.prefix}save <ability>`, and `{ctx.prefix}attack <action>`. 

            For example, you can make a Stealth check with `{ctx.prefix}check stealth`, a Dexterity save with \
            `{ctx.prefix}save dex`, and an unarmed attack with `{ctx.prefix}attack unarmed`. Try these now!
            ```
            {ctx.prefix}check <skill>
            {ctx.prefix}save <ability>
            {ctx.prefix}attack <action>
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            check = ctx.bot.get_command('check')
            save = ctx.bot.get_command('save')
            attack = ctx.bot.get_command('attack')
            if ctx.command in (check, save, attack):
                if ctx.command is check:
                    state_map.data['has_check'] = True
                elif ctx.command is save:
                    state_map.data['has_save'] = True
                elif ctx.command is attack:
                    state_map.data['has_attack'] = True
                await state_map.commit(ctx)
                embed = TutorialEmbed(self, ctx)
                embed.title = "Objectives"
                embed.description = checklist([
                    (f"Make a skill check with `{ctx.prefix}check <skill>`.", state_map.data.get('has_check')),
                    (f"Make an ability save with `{ctx.prefix}save <ability>`.", state_map.data.get('has_save')),
                    (f"Make an attack with `{ctx.prefix}attack <action>`.", state_map.data.get('has_attack'))
                ])
                await ctx.send(embed=embed)

            if state_map.data.get('has_check') and state_map.data.get('has_save') and state_map.data.get('has_attack'):
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            # todo
            await ctx.trigger_typing()
            await state_map.end_tutorial(ctx)