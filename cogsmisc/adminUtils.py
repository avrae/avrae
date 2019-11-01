"""
Created on Sep 23, 2016

@author: andrew
"""
import asyncio
import logging

import discord
from discord.errors import NotFound
from discord.ext import commands

from cogs5e.funcs.lookupFuncs import compendium
from utils import checks
from utils.functions import discord_trim

log = logging.getLogger(__name__)


class AdminUtils(commands.Cog):
    """
    Administrative Utilities.
    """

    def __init__(self, bot):
        self.bot = bot
        bot.loop.create_task(self.load_admin())
        self.blacklisted_serv_ids = set()
        self.whitelisted_serv_ids = set()

    async def load_admin(self):
        await self.bot.wait_until_ready()
        self.bot.muted = set(await self.bot.rdb.jget('muted', []))
        self.blacklisted_serv_ids = set(await self.bot.rdb.jget('blacklist', []))
        self.whitelisted_serv_ids = set(await self.bot.rdb.jget('server-whitelist', []))

        loglevels = await self.bot.rdb.jget('loglevels', {})
        for logger, level in loglevels.items():
            try:
                logging.getLogger(logger).setLevel(level)
            except:
                log.warning(f"Failed to reset loglevel of {logger}")

    @commands.command(hidden=True)
    @checks.is_owner()
    async def blacklist(self, ctx, _id: int):
        self.blacklisted_serv_ids = set(await self.bot.rdb.jget('blacklist', []))
        self.blacklisted_serv_ids.add(_id)
        await self.bot.rdb.jset('blacklist', list(self.blacklisted_serv_ids))
        await ctx.send(':ok_hand:')

    @commands.command(hidden=True)
    @checks.is_owner()
    async def whitelist(self, ctx, _id: int):
        whitelist = set(await self.bot.rdb.jget('server-whitelist', []))
        whitelist.add(_id)
        await self.bot.rdb.jset('server-whitelist', list(whitelist))
        await ctx.send(':ok_hand:')

    @commands.command(hidden=True)
    @checks.is_owner()
    async def chanSay(self, ctx, channel: int, *, message: str):
        """Like .say, but works across servers. Requires channel id."""
        chan = self.bot.get_channel(channel)
        if not chan:
            return await ctx.send("Channel not found.")
        await chan.send(message)
        await ctx.send(f"Sent message to {chan.name}.")

    @commands.command(hidden=True)
    @checks.is_owner()
    async def servInfo(self, ctx, server: int):
        out = ''
        page = None
        if server < 9999:
            page = server

        if page:  # grab all server info
            all_servers = self.bot.guilds
            members = sum(len(g.members) for g in all_servers)
            out += f"I am in {len(all_servers)} servers, with {members} members."
            for s in sorted(all_servers, key=lambda k: len(k.members), reverse=True):
                out += "\n{} ({}, {} members, {} bot)".format(s.name, s.id, len(s.members),
                                                              sum(1 for m in s.members if m.bot))
        else:  # grab one server info
            guild = self.bot.get_guild(server)
            user = None
            if not guild:
                channel = self.bot.get_channel(server)
                if not channel:
                    user = self.bot.get_user(server)
                else:
                    guild = channel.guild

            if (not guild) and (not user):
                return await ctx.send("Not found.")

            if user:
                return await ctx.send("{} - {}".format(str(user), user.id))
            else:
                try:
                    invite = (
                        await next(c for c in guild.channels if isinstance(c, discord.TextChannel)).create_invite()).url
                except:
                    invite = None

                if invite:
                    out += "\n\n**{} ({}, {})**".format(guild.name, guild.id, invite)
                else:
                    out += "\n\n**{} ({})**".format(guild.name, guild.id)
                out += "\n{} members, {} bot".format(len(guild.members), sum(1 for m in guild.members if m.bot))
                for c in guild.channels:
                    out += '\n|- {} ({})'.format(c.name, c.id)
        out = discord_trim(out)
        if page is None:
            for m in out:
                await ctx.send(m)
        else:
            await ctx.send(out[page - 1])

    @commands.command(hidden=True, name='leave')
    @checks.is_owner()
    async def leave_server(self, ctx, guild_id: int):
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return await ctx.send("Guild not found.")
        await guild.leave()
        await ctx.send(f"Left {guild.name}.")

    @commands.command(hidden=True)
    @checks.is_owner()
    async def mute(self, ctx, target: int):
        """Mutes a person by ID."""
        self.bot.muted = set(await self.bot.rdb.jget('muted', []))
        try:
            target_user = await self.bot.fetch_user(target)
        except NotFound:
            target_user = "Not Found"
        if target in self.bot.muted:
            self.bot.muted.remove(target)
            await ctx.send("{} ({}) unmuted.".format(target, target_user))
        else:
            self.bot.muted.add(target)
            await ctx.send("{} ({}) muted.".format(target, target_user))
        await self.bot.rdb.jset('muted', list(self.bot.muted))

    @commands.command(hidden=True)
    @checks.is_owner()
    async def loglevel(self, ctx, level: int, logger=None):
        """Changes the loglevel. Do not pass logger for global. Default: 20"""
        loglevels = await self.bot.rdb.jget('loglevels', {})
        loglevels[logger] = level
        await self.bot.rdb.jset('loglevels', loglevels)
        logging.getLogger(logger).setLevel(level)
        await ctx.send(f"Set level of {logger} to {level}.")

    @commands.command(hidden=True)
    @checks.is_owner()
    async def changepresence(self, ctx, status=None, *, msg=None):
        """Changes Avrae's presence. Status: online, idle, dnd"""
        statuslevel = {'online': discord.Status.online, 'idle': discord.Status.idle, 'dnd': discord.Status.dnd}
        status = statuslevel.get(status)
        await self.bot.change_presence(status=status, activity=discord.Game(msg or "D&D 5e | !help"))
        await ctx.send("Changed presence.")

    @commands.command(hidden=True)
    @checks.is_owner()
    async def reload_static(self, ctx):
        await compendium.reload(self.bot.mdb)
        await ctx.send("Reloaded static data.")

    @commands.Cog.listener()
    async def on_guild_join(self, server):
        if server.id in self.blacklisted_serv_ids:
            return await server.leave()
        elif server.id in self.whitelisted_serv_ids:
            return
        bots = sum(1 for m in server.members if m.bot)
        members = len(server.members)
        ratio = bots / members
        if ratio >= 0.6 and members >= 20:
            log.info("Detected bot collection server ({}), ratio {}. Leaving.".format(server.id, ratio))
            try:
                await server.owner.send("Please do not add me to bot collection servers. "
                                        "Your server was flagged for having over 60% bots. "
                                        "If you believe this is an error, please PM the bot author.")
            except:
                pass
            await asyncio.sleep(members / 200)
            await server.leave()


def setup(bot):
    bot.add_cog(AdminUtils(bot))
