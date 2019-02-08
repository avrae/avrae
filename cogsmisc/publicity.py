"""
Created on Dec 29, 2016

@author: andrew
"""
import asyncio
import logging
import time

log = logging.getLogger(__name__)


class Publicity:
    """
    Sends updates to bot repos.
    """

    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self.background_update())

    async def backup(self):
        backup_chan = self.bot.get_channel(298542945479557120)
        if backup_chan is None or self.bot.testing: return
        await backup_chan.send('{0} - {1}'.format(time.time(), len(self.bot.guilds)))

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
