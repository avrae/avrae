"""
Created on Jul 17, 2017

@author: andrew
"""

import asyncio
import datetime
import time
from collections import Counter

from disnake.ext import commands

from utils import config

GUILD_RDB_KEY = "stats.cluster_guilds"


class Stats(commands.Cog):
    """Statistics and analytics about bot usage."""

    def __init__(self, bot):
        """
        :type bot: :class:`dbot.Avrae`
        """
        self.bot = bot
        self.start_time = time.monotonic()
        self.command_stats = Counter()
        self.bot.loop.create_task(self.scheduled_update())

    # ===== listeners =====
    @commands.Cog.listener()
    async def on_command(self, ctx):
        command = ctx.command.qualified_name
        self.command_stats[command] += 1
        await self.user_activity(ctx)
        await self.guild_activity(ctx)
        await self.command_activity(ctx)

    # ===== tasks =====
    async def scheduled_update(self):
        await self.bot.wait_until_ready()
        if self.bot.is_cluster_0:
            await self.clean_published_stats()
        while not self.bot.is_closed():
            if self.bot.is_cluster_0:
                await self.update_hourly()
            await self.publish_shared_statistics()
            await asyncio.sleep(60 * 60)  # every hour

    # ===== internal stat sharing =====
    async def clean_published_stats(self):
        cluster_servers = await self.bot.rdb.get_whole_dict(GUILD_RDB_KEY)
        for cluster_id in cluster_servers:
            if int(cluster_id) >= (config.NUM_CLUSTERS or 1):
                await self.bot.rdb.hdel(GUILD_RDB_KEY, cluster_id)

    async def publish_shared_statistics(self):
        cluster_servers = len(self.bot.guilds)
        await self.bot.rdb.hset(GUILD_RDB_KEY, str(self.bot.cluster_id), cluster_servers)

    # ===== analytic loggers =====
    async def user_activity(self, ctx):
        await self.bot.mdb.analytics_user_activity.update_one(
            {"user_id": ctx.author.id},
            {"$inc": {"commands_called": 1}, "$currentDate": {"last_command_time": True}},
            upsert=True,
        )

    async def guild_activity(self, ctx):
        if ctx.guild is None:
            guild_id = 0
        else:
            guild_id = ctx.guild.id

        await self.bot.mdb.analytics_guild_activity.update_one(
            {"guild_id": guild_id},
            {"$inc": {"commands_called": 1}, "$currentDate": {"last_command_time": True}},
            upsert=True,
        )

    async def command_activity(self, ctx):
        await self.increase_stat(ctx, "commands_used_life")
        # log command lifetime stat
        await self.bot.mdb.analytics_command_activity.update_one(
            {"name": ctx.command.qualified_name},
            {"$inc": {"num_invocations": 1}, "$currentDate": {"last_invoked_time": True}},  # yay, atomic operations
            upsert=True,
        )
        # log event
        guild_id = 0 if ctx.guild is None else ctx.guild.id
        await self.bot.mdb.analytics_command_events.insert_one({
            "timestamp": datetime.datetime.utcnow(),
            "command_name": ctx.command.qualified_name,
            "user_id": ctx.author.id,
            "guild_id": guild_id,
        })

    async def update_hourly(self):
        class _ContextProxy:
            def __init__(self, bot):
                self.bot = bot

        ctx = _ContextProxy(self.bot)

        commands_used_life = await self.get_statistic(ctx, "commands_used_life")
        num_characters = await self.bot.mdb.characters.estimated_document_count()  # fast

        try:
            num_inits_began = (await self.bot.mdb.analytics_command_activity.find_one({"name": "init begin"})).get(
                "num_invocations", 0
            )
        except AttributeError:
            num_inits_began = 0

        data = {
            "timestamp": datetime.datetime.now(),
            "num_commands_called": commands_used_life,
            "num_servers": await self.get_guild_count(self.bot),
            "num_characters": num_characters,
            "num_inits_began": num_inits_began,
            "num_init_turns": await self.get_statistic(ctx, "turns_init_tracked_life"),
            "num_init_rounds": await self.get_statistic(ctx, "rounds_init_tracked_life"),
        }
        await self.bot.mdb.analytics_over_time.insert_one(data)

    # ===== bot commands =====
    @commands.command(hidden=True)
    async def commandstats(self, ctx, limit=20):
        """Shows command stats.
        Use a negative number for bottom instead of top.
        This is only for the current session.
        """
        counter = self.command_stats
        width = len(max(counter, key=len))
        total = sum(counter.values())

        if limit > 0:
            common = counter.most_common(limit)
        else:
            common = counter.most_common()[limit:]

        output = "\n".join("{0:<{1}}: {2}".format(k, width, c) for k, c in common)
        await ctx.send(f"```\n{output}\n{total} total\n```")

    # ===== event listeners =====
    # we can update our server count as we join/leave servers
    @commands.Cog.listener()
    async def on_guild_join(self, _):
        await self.bot.rdb.hincrby(GUILD_RDB_KEY, str(self.bot.cluster_id), 1)

    @commands.Cog.listener()
    async def on_guild_remove(self, _):
        await self.bot.rdb.hincrby(GUILD_RDB_KEY, str(self.bot.cluster_id), -1)

    # ===== utils =====
    @staticmethod
    async def increase_stat(ctx, stat):
        await ctx.bot.mdb.random_stats.update_one({"key": stat}, {"$inc": {"value": 1}}, upsert=True)

    @staticmethod
    async def get_statistic(ctx, stat):
        try:
            value = int((await ctx.bot.mdb.random_stats.find_one({"key": stat})).get("value", 0))
        except AttributeError:
            value = 0
        return value

    @staticmethod
    async def get_guild_count(bot):
        """Returns the total number of guilds the entire bot can see, across all shards."""
        cluster_servers = await bot.rdb.get_whole_dict(GUILD_RDB_KEY)
        return sum(int(v) for v in cluster_servers.values())

    @staticmethod
    async def count_ddb_link(ctx, user_id, ddb_user):
        await ctx.bot.mdb.analytics_ddb_activity.update_one(
            {"user_id": user_id},
            {
                "$set": {"ddb_id": ddb_user.user_id},
                "$inc": {"link_usage": 1},
                "$currentDate": {"last_link_time": True},
                "$setOnInsert": {"first_link_time": datetime.datetime.utcnow()},
            },
            upsert=True,
        )


def setup(bot):
    bot.add_cog(Stats(bot))
