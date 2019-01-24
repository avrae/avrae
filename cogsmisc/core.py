"""
Created on Dec 26, 2016

@author: andrew
"""
import random
import time
from datetime import timedelta, datetime
from math import floor

import discord
import psutil
from discord.channel import PrivateChannel
from discord.ext import commands

PATRON_EYLESIS = "227168575469780992"


class Core:
    """
    Core utilty and general commands.
    """

    def __init__(self, bot):
        self.bot = bot
        self.start_time = time.monotonic()

    async def on_message(self, message):
        if message.author.id == PATRON_EYLESIS and message.content.lower().startswith("hey avrae"):
            await self.bot.send_message(message.channel,
                                        "No, I will not reseed the RNG, even if you gave me all those cookies.")
            random.seed()  # I lied

    @commands.command(pass_context=True, aliases=['feedback'])
    async def bug(self, ctx, *, report: str):
        """Reports a bug to the developer."""
        if not isinstance(ctx.message.channel, PrivateChannel):
            await self.bot.send_message(self.bot.owner,
                                        "Bug reported by {} ({}) from {} ({}):\n{}".format(ctx.message.author.mention,
                                                                                           str(ctx.message.author),
                                                                                           ctx.message.server,
                                                                                           ctx.message.server.id,
                                                                                           report))
        else:
            await self.bot.send_message(self.bot.owner,
                                        "Bug reported by {} ({}):\n{}".format(ctx.message.author.mention,
                                                                              str(ctx.message.author), report))
        await self.bot.say("Bug report sent to developer! For faster response, check out <http://support.avrae.io>!")

    @commands.command(hidden=True, pass_context=True)
    async def avatar(self, ctx, user: discord.User = None):
        """Gets a user's avatar.
        Usage: !avatar <USER>"""
        if user is None:
            user = ctx.message.author
        if user.avatar_url is not "":
            await self.bot.say(user.avatar_url)
        else:
            await self.bot.say(user.display_name + " is using the default avatar.")

    @commands.command(pass_context=True)
    async def ping(self, ctx):
        """Checks the ping time to the bot."""
        now = datetime.utcnow()
        pong = await self.bot.say("Pong.")
        delta = datetime.utcnow() - now
        msec = floor(delta.total_seconds() * 1000)
        await self.bot.edit_message(pong, "Pong.\nPing = {} ms.".format(msec))

    @commands.command()
    async def invite(self):
        """Prints a link to invite Avrae to your server."""
        await self.bot.say(
            "You can invite Avrae to your server here:\nhttps://discordapp.com/oauth2/authorize?&client_id=261302296103747584&scope=bot&permissions=36727808")

    @commands.command()
    async def donate(self):
        """Prints a link to donate to the bot developer."""
        await self.bot.say("You can donate to me here:\n<https://www.paypal.me/avrae>\n\u2764")

    @commands.command(aliases=['stats', 'info'])
    async def about(self):
        """Information about the bot."""
        botStats = {}
        statKeys = ["dice_rolled_life", "spells_looked_up_life", "monsters_looked_up_life", "commands_used_life",
                    "items_looked_up_life",
                    "rounds_init_tracked_life", "turns_init_tracked_life"]
        for k in statKeys:
            botStats[k] = int(self.bot.rdb.get(k, "0"))
        embed = discord.Embed(description='Avrae, a bot to streamline D&D 5e online.')
        embed.title = "Invite Avrae to your server!"
        embed.url = "https://discordapp.com/oauth2/authorize?&client_id=261302296103747584&scope=bot&permissions=36727808"
        embed.colour = 0x7289da
        embed.set_author(name=str(self.bot.owner), icon_url=self.bot.owner.avatar_url)
        total_members = sum(len(s.members) for s in self.bot.servers)
        total_online = sum(1 for m in self.bot.get_all_members() if m.status != discord.Status.offline)
        unique_members = set(self.bot.get_all_members())
        unique_online = sum(1 for m in unique_members if m.status != discord.Status.offline)
        text = len([c for c in self.bot.get_all_channels() if c.type is discord.ChannelType.text])
        voice = len([c for c in self.bot.get_all_channels() if c.type is discord.ChannelType.voice])
        members = '%s total\n%s online\n%s unique\n%s unique online' % (
            total_members, total_online, len(unique_members), unique_online)
        embed.add_field(name='Shard Members', value=members)
        embed.add_field(name='Shard Channels', value='{} total\n{} text\n{} voice'.format(text + voice, text, voice))
        embed.add_field(name='Uptime', value=str(timedelta(seconds=round(time.monotonic() - self.start_time))))
        motd = random.choice(["May the RNG be with you", "May your rolls be high",
                              "Will give higher rolls for cookies", ">:3",
                              "Does anyone even read these?"])
        embed.set_footer(
            text='{} | Build {} | Shard {}'.format(motd, self.bot.rdb.get('build_num'),
                                                   getattr(self.bot, 'shard_id', 0)))
        commands_run = "{commands_used_life} total\n{dice_rolled_life} dice rolled\n{spells_looked_up_life} spells looked up\n{monsters_looked_up_life} monsters looked up\n{items_looked_up_life} items looked up\n{rounds_init_tracked_life} rounds of initiative tracked ({turns_init_tracked_life} turns)".format(
            **botStats)
        embed.add_field(name="Commands Run", value=commands_run)
        embed.add_field(name="Servers", value=str(len(self.bot.servers)) + ' on this shard\n' + str(
            sum(a for a in self.bot.rdb.jget('shard_servers', {0: len(self.bot.servers)}).values())) + ' total')
        memory_usage = psutil.Process().memory_full_info().uss / 1024 ** 2
        embed.add_field(name='Memory Usage', value='{:.2f} MiB'.format(memory_usage))
        embed.add_field(name='About', value='Bot coded by @zhu.exe#4211\nFound a bug? Report it with `!bug`!\n'
                                            'Help me buy a cup of coffee [here](https://www.paypal.me/avrae)!\n'
                                            'Join the official testing server [here](https://discord.gg/pQbd4s6)!',
                        inline=False)

        await self.bot.say(embed=embed)


def setup(bot):
    bot.add_cog(Core(bot))
