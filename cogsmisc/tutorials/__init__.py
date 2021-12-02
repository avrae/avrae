"""
Main entrypoint for the tutorials extension. The tutorials themselves can be found in this module, and
are registered here. The tutorial commands are also registered here, as part of the Help cog.
"""
import textwrap

import discord
from discord.ext import commands

from cogs5e.models.embeds import EmbedWithAuthor
from utils import checks, config
from utils.aldclient import discord_user_to_dict
from utils.functions import confirm, get_guild_member, search_and_select
from .ddblink import DDBLink
from .init_dm import DMInitiative
from .init_player import PlayerInitiative
from .models import TutorialStateMap
from .playingthegame import PlayingTheGame
from .quickstart import Quickstart
from .runningthegame import RunningTheGame
from .spellcasting import Spellcasting


class Tutorials(commands.Cog):
    """
    Commands to help learn how to use the bot.
    """

    # tutorial keys should never change - if needed, change the name in the constructor to change the display name
    tutorials = {
        "quickstart": Quickstart(),
        "playingthegame": PlayingTheGame(),
        "ddblink": DDBLink(),
        "spellcasting": Spellcasting(),
        "runningthegame": RunningTheGame(),
        "init_player": PlayerInitiative(),
        "init_dm": DMInitiative()
    }

    def __init__(self, bot):
        self.bot = bot

    # ==== commands ====
    @commands.group(invoke_without_command=True)
    @checks.feature_flag('command.tutorial.enabled')
    async def tutorial(self, ctx, *, name=None):
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
    @checks.feature_flag('command.tutorial.enabled')
    async def tutorial_list(self, ctx):
        """Lists the available tutorials."""
        embed = EmbedWithAuthor(ctx)
        embed.title = "Available Tutorials"
        embed.description = f"Use `{ctx.prefix}tutorial <name>` to select a tutorial from the ones available below!\n" \
                            f"First time here? Try `{ctx.prefix}tutorial quickstart`!"
        for tutorial in self.tutorials.values():
            embed.add_field(name=tutorial.name, value=tutorial.description, inline=False)
        await ctx.send(embed=embed)

    @tutorial.command(name='skip')
    @checks.feature_flag('command.tutorial.enabled')
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
        result = await confirm(ctx, "Are you sure you want to skip the current tutorial objective? (Reply with yes/no)")
        if not result:
            return await ctx.send("Ok, aborting.")
        # run tutorial state transition
        # commit new state map
        await state.transition(ctx, user_state)

    @tutorial.command(name='end')
    @checks.feature_flag('command.tutorial.enabled')
    async def tutorial_end(self, ctx):
        """Ends the current tutorial."""
        user_state = await TutorialStateMap.from_ctx(ctx)
        if user_state is None:
            return await ctx.send("You are not currently running a tutorial.")
        # confirm
        result = await confirm(ctx, "Are you sure you want to end the current tutorial? (Reply with yes/no)")
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

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        await self.send_welcome_message(guild)

    # ==== helpers ====
    def get_tutorial_and_state(self, user_state):
        tutorial = self.tutorials.get(user_state.tutorial_key)
        if tutorial is None:
            return None, None
        state = tutorial.states.get(user_state.state_key)
        return tutorial, state

    async def send_welcome_message(self, guild):
        owner = await get_guild_member(guild, guild.owner_id)
        if owner is None:
            return
        flag_on = await self.bot.ldclient.variation('cog.tutorials.guild_join.enabled', discord_user_to_dict(owner),
                                                    default=False)
        if not flag_on:
            return
        prefix = await self.bot.get_guild_prefix(guild)
        prefix_is_default = prefix == config.DEFAULT_PREFIX

        embed = discord.Embed()
        embed.set_author(name=self.bot.user.name, icon_url=self.bot.user.display_avatar.url)
        embed.colour = discord.Colour.blurple()
        embed.description = textwrap.dedent(f"""
        :wave: Hi there! Thanks for adding me to {guild.name}!
        
        I'm ready to roll, but before we get started, let's take a look at some of the things I can do! 
        """).strip()

        if not prefix_is_default:
            embed.add_field(
                name="Prefix", inline=False,
                value=f"Looks like you've added me to {guild.name} in the past before. On {guild.name}, my prefix is "
                      f"`{prefix}`, but by default, it's `{config.DEFAULT_PREFIX}`. You can reset it with "
                      f"`{prefix}prefix {config.DEFAULT_PREFIX}`, or roll with it using the examples below!"
            )

        embed.add_field(
            name="Rolling Dice", inline=False,
            value=f"Want to get rolling as soon as possible? Just use the `{prefix}roll` command to get started! "
                  f"Here's some examples: ```\n"
                  f"{prefix}roll 1d20\n"
                  f"{prefix}roll 4d6kh3\n"
                  f"{prefix}roll 1d20+1 adv\n"
                  f"{prefix}r 1d10[cold]+2d6[piercing]\n"
                  f"```"
        )

        embed.add_field(
            name="Quickstart", inline=False,
            value=f"I can do more than just roll dice, too! If you'd like to learn more about importing a "
                  f"character and rolling checks, saves, and attacks, try out the Quickstart tutorial!"
                  f"```\n{prefix}tutorial quickstart\n```"
        )

        embed.add_field(
            name="Content Lookup", inline=False,
            value=f"You can look up any spell, item, creature, and more right in Discord! Just use the `{prefix}spell`"
                  f", `{prefix}item`, `{prefix}monster`, or other lookup command! You can see a full list with "
                  f"`{prefix}help Lookup`.\n\n"
                  f"I'll even link with your D&D Beyond account to give you access to everything you've unlocked, "
                  f"all for free! To get started, try out the D&D Beyond tutorial."
                  f"```\n{prefix}tutorial beyond\n```\n"
                  f"\u203b By default, for servers with less than 250 members, a monster's full stat block will be "
                  f"hidden unless you have a Discord role named `Dungeon Master`. You can turn this off or change the "
                  f"DM role with `{prefix}servsettings`."
        )

        embed.add_field(
            name="Initiative Tracking", inline=False,
            value=f"Once you're familiar with the basics, to learn how to get started with initiative tracking, "
                  f"try out the initiative tutorial! You can choose between a Dungeon Master's or a player's "
                  f"perspective."
                  f"```\n{prefix}tutorial initiative\n```"
        )

        embed.add_field(
            name="Custom Commands", inline=False,
            value=f"Want to do even more? Check out the list of user-made commands at "
                  f"https://avrae.io/dashboard/workshop, and add them to Discord with one click!"
        )

        embed.add_field(
            name="More Resources", inline=False,
            value=f"If you ever want a refresher on a command or feature, use the `{prefix}help` command for help on a "
                  f"command, or `{prefix}tutorial` for a list of available tutorials.\n\n"
                  f"For even more resources, come join us in the development Discord at <https://support.avrae.io>!"
        )

        try:
            await owner.send(embed=embed)
        except discord.HTTPException:
            pass


# discord ext boilerplate
def setup(bot):
    cog = Tutorials(bot)
    bot.add_cog(cog)
    bot.help_command.cog = cog
