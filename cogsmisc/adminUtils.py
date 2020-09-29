"""
Created on Sep 23, 2016

@author: andrew
"""
import asyncio
import copy
import itertools
import logging
import re
from math import floor

import discord
from discord.errors import NotFound
from discord.ext import commands

import utils.redisIO as redis
from gamedata.compendium import compendium
from utils import checks, config
from utils.functions import confirm

log = logging.getLogger(__name__)

COMMAND_PUBSUB_CHANNEL = f"admin-commands:{config.ENVIRONMENT}"  # >:c


class AdminUtils(commands.Cog):
    """
    Administrative Utilities.
    """

    def __init__(self, bot):
        self.bot = bot
        bot.loop.create_task(self.load_admin())
        bot.loop.create_task(self.admin_pubsub())
        self.blacklisted_serv_ids = set()
        self.whitelisted_serv_ids = set()

        # pubsub stuff
        self._ps_cmd_map = {}  # set up in admin_pubsub()
        self._ps_requests_pending = {}

    # ==== setup tasks ====
    async def load_admin(self):
        self.bot.muted = set(await self.bot.rdb.jget('muted', []))
        self.blacklisted_serv_ids = set(await self.bot.rdb.jget('blacklist', []))
        self.whitelisted_serv_ids = set(await self.bot.rdb.jget('server-whitelist', []))

        loglevels = await self.bot.rdb.jget('loglevels', {})
        for logger, level in loglevels.items():
            try:
                logging.getLogger(logger).setLevel(level)
            except:
                log.warning(f"Failed to reset loglevel of {logger}")

    async def admin_pubsub(self):
        self._ps_cmd_map = {
            "leave": self._leave,
            "loglevel": self._loglevel,
            "changepresence": self._changepresence,
            "reload_static": self._reload_static,
            "reload_lists": self._reload_lists,
            "serv_info": self._serv_info,
            "whois": self._whois,
            "ping": self._ping,
            "restart_shard": self._restart_shard,
            "kill_cluster": self._kill_cluster
        }
        while True:  # if we ever disconnect from pubsub, wait 5s and try reinitializing
            try:  # connect to the pubsub channel
                channel = (await self.bot.rdb.subscribe(COMMAND_PUBSUB_CHANNEL))[0]
            except:
                log.warning("Could not connect to pubsub! Waiting to reconnect...")
                await asyncio.sleep(5)
                continue

            log.info("Connected to pubsub.")
            async for msg in channel.iter(encoding="utf-8"):
                try:
                    await self._ps_recv(msg)
                except Exception as e:
                    log.error(str(e))
            log.warning("Disconnected from Redis pubsub! Waiting to reconnect...")
            await asyncio.sleep(5)

    # ==== commands ====
    @commands.command(hidden=True)
    @checks.is_owner()
    async def pingall(self, ctx):
        resp = await self.pscall("ping")
        embed = discord.Embed(title="Cluster Pings")
        for cluster, pings in sorted(resp.items(), key=lambda i: i[0]):
            pingstr = "\n".join(f"Shard {shard}: {floor(ping * 1000)}ms" for shard, ping in pings.items())
            avgping = floor((sum(pings.values()) / len(pings)) * 1000)
            embed.add_field(name=f"Cluster {cluster}: {avgping}ms", value=pingstr)
        await ctx.send(embed=embed)

    @commands.command(hidden=True)
    @checks.is_owner()
    async def changepresence(self, ctx, status=None, *, msg=None):
        """Changes Avrae's presence. Status: online, idle, dnd"""
        resp = await self.pscall("changepresence", kwargs={"status": status, "msg": msg})
        await self._send_replies(ctx, resp)

    @commands.group(hidden=True, invoke_without_command=True)
    @checks.is_owner()
    async def admin(self, ctx):
        """Owner-only admin commands."""
        await ctx.send("hello yes please give me a subcommand")

    @admin.command(hidden=True)
    @checks.is_owner()
    async def blacklist(self, ctx, _id: int):
        self.blacklisted_serv_ids.add(_id)
        await self.bot.rdb.jset('blacklist', list(self.blacklisted_serv_ids))
        resp = await self.pscall("reload_lists")
        await self._send_replies(ctx, resp)

    @admin.command(hidden=True)
    @checks.is_owner()
    async def whitelist(self, ctx, _id: int):
        self.whitelisted_serv_ids.add(_id)
        await self.bot.rdb.jset('server-whitelist', list(self.whitelisted_serv_ids))
        resp = await self.pscall("reload_lists")
        await self._send_replies(ctx, resp)

    @admin.command(hidden=True)
    @checks.is_owner()
    async def chanSay(self, ctx, channel: int, *, message: str):
        """Low-level calls `bot.http.send_message()`."""
        await self.bot.http.send_message(channel, message)
        await ctx.send(f"Sent message.")

    @admin.command(hidden=True)
    @checks.is_owner()
    async def servInfo(self, ctx, guild_id: int):
        resp = await self.pscall("serv_info", kwargs={"guild_id": guild_id}, expected_replies=1)
        await self._send_replies(ctx, resp)

    @admin.command(hidden=True)
    @checks.is_owner()
    async def whois(self, ctx, user_id: int):
        user = await self.bot.fetch_user(user_id)
        resp = await self.pscall("whois", kwargs={"user_id": user_id})
        await self._send_replies(ctx, resp, base=f"{user_id} is {user}:")

    @admin.command(hidden=True, name='leave')
    @checks.is_owner()
    async def leave_server(self, ctx, guild_id: int):
        resp = await self.pscall("leave", kwargs={"guild_id": guild_id}, expected_replies=1)
        await self._send_replies(ctx, resp)

    @admin.command(hidden=True)
    @checks.is_owner()
    async def mute(self, ctx, target: int):
        """Mutes a person by ID."""
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
        resp = await self.pscall("reload_lists")
        await self._send_replies(ctx, resp)

    @admin.command(hidden=True)
    @checks.is_owner()
    async def loglevel(self, ctx, level: int, logger=None):
        """Changes the loglevel. Do not pass logger for global. Default: 20"""
        loglevels = await self.bot.rdb.jget('loglevels', {})
        loglevels[logger] = level
        await self.bot.rdb.jset('loglevels', loglevels)
        resp = await self.pscall("loglevel", args=[level], kwargs={"logger": logger})
        await self._send_replies(ctx, resp)

    @admin.command(hidden=True)
    @checks.is_owner()
    async def reload_static(self, ctx):
        resp = await self.pscall("reload_static")
        await self._send_replies(ctx, resp)

    @admin.command(hidden=True, name='su')
    @checks.is_owner()
    async def admin_su(self, ctx, member: discord.Member, *, content):
        msg = copy.copy(ctx.message)
        msg.author = member
        msg.content = content
        new_ctx = await self.bot.get_context(msg)
        # copied from dbot#on_message()
        if new_ctx.command is not None:
            await self.bot.invoke(new_ctx)
        elif new_ctx.invoked_with:
            from aliasing.helpers import handle_aliases
            await handle_aliases(ctx)

    # ---- cluster management ----
    @admin.command(hidden=True, name="restart-shard")
    @checks.is_owner()
    async def admin_restart_shard(self, ctx, shard_id: int):
        """Forces a shard to disconnect from the Discord API and reconnect."""
        if not await confirm(ctx, f"Are you sure you want to restart shard {shard_id}?"):
            return await ctx.send("ok, not restarting")
        resp = await self.pscall("restart_shard", kwargs={"shard_id": shard_id}, expected_replies=1)
        await self._send_replies(ctx, resp)

    @admin.command(hidden=True, name="kill-cluster")
    @checks.is_owner()
    async def admin_kill_cluster(self, ctx, cluster_id: int):
        """Forces a cluster to restart by killing it."""
        num_shards = len(self.bot.shard_ids) if self.bot.shard_ids is not None else 1
        if not await confirm(ctx, f"Are you absolutely sure you want to kill cluster {cluster_id}?\n"
                                  f"**This will terminate approximately {num_shards} shards, which "
                                  f"will take at least {num_shards * 5} seconds to restart, and "
                                  f"impact about {len(self.bot.guilds)} servers.**"):
            return await ctx.send("ok, not killing")
        resp = await self.pscall("kill_cluster", kwargs={"cluster_id": cluster_id}, expected_replies=1)
        await self._send_replies(ctx, resp)

    # ---- workshop ----
    @admin.group(name='workshop', invoke_without_command=True)
    @checks.is_owner()
    async def admin_workshop(self, ctx):
        await ctx.send("subcommands: `tags`, `tags add <slug> <name> <category>`, `tags remove <slug>`")

    @admin_workshop.group(name='tags', invoke_without_command=True)
    @checks.is_owner()
    async def admin_workshop_tags(self, ctx):
        """Lists all tags in the workshop."""
        embed = discord.Embed()
        tags = await self.bot.mdb.workshop_tags.find().to_list(None)
        for category, c_tags in itertools.groupby(tags, lambda t: t['category']):
            out = []
            for tag in c_tags:
                out.append(f"`{tag['slug']}`: {tag['name']}")
            out = '\n'.join(out)
            embed.add_field(name=category, value=out)

        if not tags:
            embed.description = "There are no tags"

        await ctx.send(embed=embed)

    @admin_workshop_tags.command(name='add')
    @checks.is_owner()
    async def admin_workshop_tags_add(self, ctx, slug, name, category):
        """
        Adds a tag to the workshop.

        Slug must be only alphanum + `-` characters, and not start with `-`.
        """
        if not re.match(r'\w[\w\d\-]*', slug):
            return await ctx.send("Tag must be alnum and not start with -")
        tag = {"slug": slug, "name": name, "category": category}
        await self.bot.mdb.workshop_tags.insert_one(tag)
        await ctx.send(f"Added tag `{slug}`")

    @admin_workshop_tags.command(name='remove')
    @checks.is_owner()
    async def admin_workshop_tags_remove(self, ctx, slug):
        """
        Removes a tag from the workshop.
        """
        result = await self.bot.mdb.workshop_tags.delete_many({"slug": slug})
        await ctx.send(f"Deleted {result.deleted_count} tags")

    # ==== listener ====
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

    # ==== helper ====
    @staticmethod
    async def _send_replies(ctx, resp, base=None):
        sorted_replies = sorted(resp.items(), key=lambda i: i[0])
        out = '\n'.join(f"{cid}: {rep}" for cid, rep in sorted_replies)
        if base:
            out = f"{base}\n{out}"
        await ctx.send(out)

    # ==== methods (called by pubsub) ====
    async def _leave(self, guild_id):
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return False
        await guild.leave()
        return f"Left {guild.name}."

    @staticmethod
    async def _loglevel(level, logger=None):
        logging.getLogger(logger).setLevel(level)
        return f"Set level of {logger} to {level}."

    async def _changepresence(self, status=None, msg=None):
        statuslevel = {'online': discord.Status.online, 'idle': discord.Status.idle, 'dnd': discord.Status.dnd}
        status = statuslevel.get(status)
        await self.bot.change_presence(status=status, activity=discord.Game(msg or "D&D 5e | !help"))
        return "Changed presence."

    async def _reload_static(self):
        await compendium.reload(self.bot.mdb)
        return "OK"

    async def _reload_lists(self):
        self.blacklisted_serv_ids = set(await self.bot.rdb.jget('blacklist', []))
        self.whitelisted_serv_ids = set(await self.bot.rdb.jget('server-whitelist', []))
        self.bot.muted = set(await self.bot.rdb.jget('muted', []))
        return "OK"

    async def _serv_info(self, guild_id):
        guild = self.bot.get_guild(guild_id)
        if not guild:
            channel = self.bot.get_channel(guild_id)
            if not channel:
                return False
            else:
                guild = channel.guild

        try:
            invite = (
                await next(c for c in guild.channels if isinstance(c, discord.TextChannel)).create_invite()).url
        except:
            invite = None

        if invite:
            out = f"{guild.name} ({guild.id}, <{invite}>)"
        else:
            out = f"{guild.name} ({guild.id})"
        out += f"\n{len(guild.members)} members, {sum(m.bot for m in guild.members)} bot"
        return out

    async def _whois(self, user_id):
        return [guild.id for guild in self.bot.guilds if user_id in {user.id for user in guild.members}]

    async def _ping(self):
        return dict(self.bot.latencies)

    async def _restart_shard(self, shard_id: int):
        if (shard := self.bot.get_shard(shard_id)) is None:
            return False
        await shard.reconnect()
        return f"Reconnected shard {shard.id}"

    async def _kill_cluster(self, cluster_id: int):
        if cluster_id != self.bot.cluster_id:
            return False
        import os
        import signal
        os.kill(os.getpid(), signal.SIGTERM)  # please shut down gracefully
        return "Shutting down..."

    # ==== pubsub ====
    async def pscall(self, command, args=None, kwargs=None, *, expected_replies=config.NUM_CLUSTERS or 1, timeout=30):
        """Makes an IPC call to all clusters. Returns a dict of {cluster_id: reply_data}."""
        request = redis.PubSubCommand.new(self.bot, command, args, kwargs)
        self._ps_requests_pending[request.id] = {}
        await self.bot.rdb.publish(COMMAND_PUBSUB_CHANNEL, request.to_json())

        for _ in range(timeout * 10):  # timeout after 30 sec
            if len(self._ps_requests_pending[request.id]) >= expected_replies:
                break
            else:
                await asyncio.sleep(0.1)

        return self._ps_requests_pending.pop(request.id)

    async def _ps_recv(self, message):
        redis.pslogger.debug(message)
        msg = redis.deserialize_ps_msg(message)
        if msg.type == 'reply':
            await self._ps_reply(msg)
        elif msg.type == 'cmd':
            await self._ps_cmd(msg)

    async def _ps_reply(self, message: redis.PubSubReply):
        if message.reply_to not in self._ps_requests_pending:
            return
        self._ps_requests_pending[message.reply_to][message.sender] = message.data

    async def _ps_cmd(self, message: redis.PubSubCommand):
        if message.command not in self._ps_cmd_map:
            return
        command = self._ps_cmd_map[message.command]
        result = await command(*message.args, **message.kwargs)

        if result is not False:
            response = redis.PubSubReply.new(self.bot, reply_to=message.id, data=result)
            await self.bot.rdb.publish(COMMAND_PUBSUB_CHANNEL, response.to_json())


# ==== setup ====
def setup(bot):
    bot.add_cog(AdminUtils(bot))
