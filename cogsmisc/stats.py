"""
Created on Jul 17, 2017

@author: andrew
"""
import time
from collections import Counter

from discord.ext import commands


class Stats:
    """Statistics about bot usage."""

    def __init__(self, bot):
        self.bot = bot
        self.command_stats = Counter()
        self.socket_stats = Counter()
        self.socket_bandwidth = Counter()
        self.start_time = time.monotonic()

    async def on_command(self, ctx):
        command = ctx.command.qualified_name
        self.command_stats[command] += 1

    async def on_socket_response(self, msg):
        self.socket_stats[msg.get('t')] += 1
        self.socket_bandwidth[msg.get('t')] += len(str(msg).encode())

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


def setup(bot):
    bot.add_cog(Stats(bot))
