"""
Created on Jul 17, 2017

@author: andrew
"""
import asyncio
import datetime
import time
from collections import Counter

from discord.ext import commands


class Stats(commands.Cog):
    """Statistics and analytics about bot usage."""

    def __init__(self, bot):
        self.bot = bot
        self.start_time = time.monotonic()

        self.command_stats = Counter()
        self.socket_stats = Counter()
        self.socket_bandwidth = Counter()

        self.bot.loop.create_task(self.scheduled_update())

    # ===== listeners =====
    @commands.Cog.listener()
    async def on_command(self, ctx):
        command = ctx.command.qualified_name
        self.command_stats[command] += 1
        await self.user_activity(ctx)
        await self.guild_activity(ctx)
        await self.command_activity(ctx)

    @commands.Cog.listener()
    async def on_socket_response(self, msg):
        t = msg.get('t')
        self.socket_stats[t] += 1
        self.socket_bandwidth[t] += len(msg)

    # ===== tasks =====
    async def scheduled_update(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await self.update_hourly()
            await asyncio.sleep(60 * 60)  # every hour

    # ===== analytic loggers =====
    async def user_activity(self, ctx):
        await self.bot.mdb.analytics_user_activity.update_one(
            {"user_id": ctx.author.id},
            {
                "$inc": {"commands_called": 1},
                "$currentDate": {"last_command_time": True}
            },
            upsert=True
        )

    async def guild_activity(self, ctx):
        if ctx.guild is None:
            guild_id = 0
        else:
            guild_id = ctx.guild.id

        await self.bot.mdb.analytics_guild_activity.update_one(
            {"guild_id": guild_id},
            {
                "$inc": {"commands_called": 1},
                "$currentDate": {"last_command_time": True}
            },
            upsert=True
        )

    async def command_activity(self, ctx):
        await self.increase_stat(ctx, "commands_used_life")
        await self.bot.mdb.analytics_command_activity.update_one(
            {"name": ctx.command.qualified_name},
            {
                "$inc": {"num_invocations": 1},  # yay, atomic operations
                "$currentDate": {"last_invoked_time": True}
            },
            upsert=True
        )

    async def update_hourly(self):
        class _ContextProxy:
            def __init__(self, bot):
                self.bot = bot

        ctx = _ContextProxy(self.bot)

        commands_used_life = await self.get_statistic(ctx, "commands_used_life")
        num_characters = await self.bot.mdb.characters.estimated_document_count()  # fast

        try:
            num_inits_began = (await self.bot.mdb.analytics_command_activity.find_one({"name": "init begin"})) \
                .get("num_invocations", 0)
        except AttributeError:
            num_inits_began = 0


        data = {
            "timestamp": datetime.datetime.now(),
            "num_unique_members": len(self.bot.users),
            "num_commands_called": commands_used_life,
            "num_servers": len(self.bot.guilds),
            "num_characters": num_characters,
            "num_inits_began": num_inits_began,
            "num_init_turns": await self.get_statistic(ctx, "turns_init_tracked_life"),
            "num_init_rounds": await self.get_statistic(ctx, "rounds_init_tracked_life")
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

        output = '\n'.join('{0:<{1}}: {2}'.format(k, width, c) for k, c in common)
        await ctx.send(f'```\n{output}\n{total} total\n```')

    @commands.command(hidden=True)
    async def socketstats(self, ctx):
        minutes = round(time.monotonic() - self.start_time) / 60
        total = sum(self.socket_stats.values())
        cpm = total / minutes
        await ctx.send(
            '{0} socket events observed ({1:.2f}/minute):\n{2}'
                .format(total, cpm, self.socket_stats))

    @commands.command(hidden=True)
    async def socketbandwidth(self, ctx):
        minutes = round(time.monotonic() - self.start_time) / 60
        total = sum(self.socket_bandwidth.values())
        cpm = total / minutes
        await ctx.send('{0} bytes of socket events observed ({1:.2f}/minute):\n{2}'
                       .format(total, cpm, self.socket_bandwidth))

    @staticmethod
    async def increase_stat(ctx, stat):
        await ctx.bot.mdb.random_stats.update_one(
            {"key": stat},
            {"$inc": {"value": 1}},
            upsert=True
        )

    @staticmethod
    async def get_statistic(ctx, stat):
        try:
            value = int(
                (await ctx.bot.mdb.random_stats.find_one({"key": stat}))
                    .get("value", 0)
            )
        except AttributeError:
            value = 0
        return value


def setup(bot):
    bot.add_cog(Stats(bot))
