"""
Created on Dec 29, 2016

@author: andrew
"""
import asyncio
import logging
import time

log = logging.getLogger(__name__)

DISCORD_BOTS_API = 'https://bots.discord.pw/api'
CARBONITEX_API_BOTDATA = 'https://www.carbonitex.net/discord/data/botdata.php'


class Publicity:
    """
    Sends updates to bot repos.
    """

    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self.background_update())

    async def backup(self):
        shard_servers = self.bot.db.jget('shard_servers', {0: len(self.bot.servers)})
        shard_servers[self.bot.shard_id] = len(self.bot.servers)
        self.bot.db.jset('shard_servers', shard_servers)

        backup_chan = self.bot.get_channel('298542945479557120')
        if backup_chan is None or self.bot.testing: return
        await self.bot.send_message(backup_chan, '{0} - {1}'.format(time.time(), sum(
            a for a in self.bot.db.jget('shard_servers', {0: len(self.bot.servers)}).values())))

    async def background_update(self):
        try:
            await self.bot.wait_until_ready()
            while not self.bot.is_closed:
                await asyncio.sleep(3600)  # every hour
                await self.backup()
        except asyncio.CancelledError:
            pass

    async def on_ready(self):
        await self.backup()

    async def on_server_join(self, server):
        log.info('Joined server {}: {}, {} members ({} bot)'.format(server, server.id, len(server.members),
                                                                    sum(1 for m in server.members if m.bot)))

    async def on_server_remove(self, server):
        log.info('Left server {}: {}, {} members ({} bot)'.format(server, server.id, len(server.members),
                                                                  sum(1 for m in server.members if m.bot)))


def setup(bot):
    bot.add_cog(Publicity(bot))
