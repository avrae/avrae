"""
Created on Dec 29, 2016

@author: andrew
"""
import asyncio
import json
import logging
import time

import aiohttp


log = logging.getLogger(__name__)

DISCORD_BOTS_API =       'https://bots.discord.pw/api'
CARBONITEX_API_BOTDATA = 'https://www.carbonitex.net/discord/data/botdata.php'

class Publicity:
    """
    Sends updates to bot repos.
    """
    
    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self.bot.loop.create_task(self.background_update())
        
    def __unload(self):
        # pray it closes
        self.bot.loop.create_task(self.session.close())

    async def update(self):
        shard_servers = self.bot.db.jget('shard_servers', {0: len(self.bot.servers)})
        shard_servers[str(getattr(self.bot, 'shard_id'))] = len(self.bot.servers)
        self.bot.db.jset('shard_servers', shard_servers)
        if self.bot.testing: return
        
        if getattr(self.bot, "shard_id", 0) == 0:
            carbon_payload = {
                'key': self.bot.credentials.carbon_key,
                'servercount': sum(a for a in shard_servers.values())
            }
            
            carbon_headers = {
                'content-type': 'application/json'
            }
    
            async with self.session.post(CARBONITEX_API_BOTDATA, data=carbon_payload, headers=carbon_headers) as resp:
                log.info('Carbon statistics returned {0.status}'.format(resp))

        payload = json.dumps({
            'shard_id': getattr(self.bot, 'shard_id', 0),
            'shard_count': getattr(self.bot, 'shard_count', 1),
            'server_count': len(self.bot.servers)
        })

        headers = {
            'authorization': self.bot.credentials.discord_bots_key,
            'content-type': 'application/json'
        }

        url = '{0}/bots/{1.user.id}/stats'.format(DISCORD_BOTS_API, self.bot)
        async with self.session.post(url, data=payload, headers=headers) as resp:
            log.info('DBots statistics returned {0.status} for {1}'.format(resp, payload))
    
    async def backup(self):
        backup_chan = self.bot.get_channel('298542945479557120')
        if backup_chan is None or self.bot.testing: return
        await self.bot.send_message(backup_chan, '{0} - {1}'.format(time.time(), sum(a for a in self.bot.db.jget('shard_servers', {0: len(self.bot.servers)}).values())))
#         backup_keys = ['cmd_aliases', 'damage_snippets', 'char_vars']
#         for k in backup_keys:
#             path = './{}-backup.json'.format(k)
#             with open(path, mode='w') as f:
#                 f.write(self.bot.db.get(k))
#             await self.bot.send_file(backup_chan, path)
        
        
    async def background_update(self):
        try:
            await self.bot.wait_until_ready()
            while not self.bot.is_closed:
                await asyncio.sleep(3600)  # every hour
                await self.update()
                await self.backup()
        except asyncio.CancelledError:
            pass
    
    async def on_ready(self):
        await self.update()
        await self.backup()
        
    async def on_server_join(self, server):
        log.info('Joined server {}: {}, {} members ({} bot)'.format(server, server.id, len(server.members), sum(1 for m in server.members if m.bot)))
        
    async def on_server_remove(self, server):
        log.info('Left server {}: {}, {} members ({} bot)'.format(server, server.id, len(server.members), sum(1 for m in server.members if m.bot)))