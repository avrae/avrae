import asyncio

from cogs5e.models.errors import NoCharacter
from utils import config
from .models import Tutorial, TutorialEmbed, TutorialState, checklist, state


class Quickstart(Tutorial):
    name = "Quickstart"
    description = """
    *10 minutes*
    New to Avrae or Discord bots in general? This tutorial will help you get started with Avrae's command system, rolling dice, and importing a D&D Beyond character into Discord.
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
            Each command in Avrae starts with a *prefix*, or a short string of characters at the start of a message. By default, this prefix is `{config.DEFAULT_PREFIX}`{server_prefix_override}. Avrae will only run a command if a message starts with this prefix.
            
            To use a command in Avrae, type the prefix, then the name of the command. For example, to roll a d20, send a message containing `{ctx.prefix}roll d20`. Try it now!
            ```
            {ctx.prefix}roll d20
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.command is ctx.bot.get_command("roll") and "d20" in ctx.message.content:
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.description = f"""
            Great! As you might have guessed, `{ctx.prefix}roll <dice>` is the command to roll some dice. Throughout the rest of this tutorial and other tutorials, we'll show commands in code blocks like `this`. 
            
            When you see something like `<dice>` or `[dice]`, this is called an *argument*: it means you can put some input there, like the dice you want to roll. Arguments in brackets like `<this>` are required, and arguments in brackets like `[this]` are optional. Make sure not to include the brackets themselves!
            """
            await ctx.send(embed=embed)
            try:
                await ctx.get_character()
                await state_map.transition_with_delay(ctx, self.tutorial.ChecksAttacksSaves, 5)
            except NoCharacter:
                await state_map.transition_with_delay(ctx, self.tutorial.ImportCharacter, 5)

    @state()
    class ImportCharacter(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Importing a Character"
            embed.description = f"""
            Now, let's import a character and get started with Avrae's automated attacks, skill checks, and ability saves! First, go ahead and make a character on [D&D Beyond](https://www.dndbeyond.com/?utm_source=avrae&utm_medium=tutorial).
            
            Once you're ready, import the character into Avrae with the command `{ctx.prefix}import <url>`, using either the "Sharable Link" on your character sheet or the URL in the address bar of your browser.
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
            if (
                ctx.command
                in (
                    ctx.bot.get_command("beyond"),
                    ctx.bot.get_command("import"),
                    ctx.bot.get_command("update"),
                    ctx.bot.get_command("char"),
                )
                and character is not None
            ):
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            character = await ctx.get_character()

            embed = TutorialEmbed(self, ctx)
            embed.description = f"""
            Nice to meet you, {character.name}! Avrae has no limit on how many characters you can import, but you can only have one "active" at a time across all servers. To switch between active characters, use `{ctx.prefix}character <name>`.
            
            Also, if you change your character sheet, Avrae will need to be updated to know about those changes. Whenever you do so, make sure to run `{ctx.prefix}update` to update your active character!
            """
            await ctx.send(embed=embed)
            await state_map.transition_with_delay(ctx, self.tutorial.ChecksAttacksSaves, 5)

    @state()
    class ChecksAttacksSaves(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Checks, Saves, and Attacks"
            embed.description = f"""
            Let's go over the three most important rolls in D&D: skill checks, saving throws, and attacks. Now that your character is saved in Avrae, you can easily make these three rolls with simple commands: `{ctx.prefix}check <skill>`, `{ctx.prefix}save <ability>`, and `{ctx.prefix}action <action>`. 

            For example, you can make a Stealth check with `{ctx.prefix}check stealth`, a Dexterity save with `{ctx.prefix}save dex`, and an unarmed attack with `{ctx.prefix}action "Unarmed Strike"`. Try these now!
            ```
            {ctx.prefix}check <skill>
            {ctx.prefix}save <ability>
            {ctx.prefix}action <action>
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            check = ctx.bot.get_command("check")
            save = ctx.bot.get_command("save")
            attack = ctx.bot.get_command("action")
            if ctx.command in (check, save, attack):
                if ctx.command is check:
                    state_map.data["has_check"] = True
                elif ctx.command is save:
                    state_map.data["has_save"] = True
                elif ctx.command is attack and " " in ctx.message.content:  # not just !a, must use actual attack
                    state_map.data["has_attack"] = True
                await state_map.commit(ctx)
                embed = TutorialEmbed(self, ctx)
                embed.title = "Objectives"
                embed.description = checklist([
                    (f"Make a skill check with `{ctx.prefix}check <skill>`.", state_map.data.get("has_check")),
                    (f"Make an ability save with `{ctx.prefix}save <ability>`.", state_map.data.get("has_save")),
                    (f"Make an attack with `{ctx.prefix}action <action>`.", state_map.data.get("has_attack")),
                ])
                await ctx.send(embed=embed)

            if state_map.data.get("has_check") and state_map.data.get("has_save") and state_map.data.get("has_attack"):
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            await ctx.trigger_typing()
            await asyncio.sleep(3)
            embed = TutorialEmbed(self, ctx)
            embed.description = f"""
            Nice! You might have noticed that the command to make an attack is `{ctx.prefix}action` - this is because Avrae can automate more actions than just attacks! Let's take a look at how to use some of your other actions.
            """
            await ctx.send(embed=embed)
            await state_map.transition_with_delay(ctx, self.tutorial.Actions, 5)

    @state()
    class Actions(TutorialState):
        async def objective(self, ctx, state_map):
            embed = TutorialEmbed(self, ctx)
            embed.title = "Actions"
            embed.description = f"""
            Actions are how you can use the rest of your character's abilities. In Avrae, most abilities can be run automatically with just one command: `{ctx.prefix}action`. These abilities include not just attacks, but any features your character has from their race, class, or feats!

            Let's try using an action. List the actions you have available with `{ctx.prefix}action list`, and then use one with `{ctx.prefix}action <action>`! Don't forget to use quotes around the action name if it has multiple words! You can choose to only use part of the full name, too, if it's very long.
            ```
            {ctx.prefix}action list
            {ctx.prefix}action <action>
            ```
            """
            await ctx.send(embed=embed)

        async def listener(self, ctx, state_map):
            if ctx.command is ctx.bot.get_command("action") and ctx.args:
                await self.transition(ctx, state_map)

        async def transition(self, ctx, state_map):
            await ctx.trigger_typing()
            await asyncio.sleep(2)
            embed = TutorialEmbed(self, ctx, footer=False)
            embed.description = f"""
            That's all you need to get started! If you ever need a refresher on one command, you can use `{ctx.prefix}help <command>` to get the command's help sent to you. Next, you might want to try the *Playing the Game* tutorial - start this tutorial with `{ctx.prefix}tutorial Playing the Game`.

            Looking for additional resources? Come join us at the [Avrae Development Discord](https://support.avrae.io).
            """
            embed.set_footer(text=f"{self.tutorial.name} | Tutorial complete!")
            await ctx.send(embed=embed)
            await state_map.end_tutorial(ctx)
