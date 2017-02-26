'''
Created on Dec 29, 2016

@author: andrew
'''
import aiohttp
import asyncio
import json


DISCORD_BOTS_API =       'https://bots.discord.pw/api'
CARBONITEX_API_BOTDATA = 'https://www.carbonitex.net/discord/data/botdata.php'

class Publicity:
    '''
    Sends updates to bot repos.
    '''
    
    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        
    def __unload(self):
        # pray it closes
        self.bot.loop.create_task(self.session.close())

    async def update(self):
        
        if self.bot.testing: return
        
        carbon_payload = {
            'key': self.bot.credentials.carbon_key,
            'servercount': len(self.bot.servers)
        }
        
        carbon_headers = {
            'content-type': 'application/json'
        }

        async with self.session.post(CARBONITEX_API_BOTDATA, data=carbon_payload, headers=carbon_headers) as resp:
            print('Carbon statistics returned {0.status}'.format(resp))

        payload = json.dumps({
            'server_count': len(self.bot.servers)
        })

        headers = {
            'authorization': self.bot.credentials.discord_bots_key,
            'content-type': 'application/json'
        }

        url = '{0}/bots/{1.user.id}/stats'.format(DISCORD_BOTS_API, self.bot)
        async with self.session.post(url, data=payload, headers=headers) as resp:
            print('DBots statistics returned {0.status} for {1}'.format(resp, payload))

    async def background_update(self):
        try:
            await self.bot.wait_until_ready()
            while not self.bot.is_closed:
                await asyncio.sleep(3600)  # every hour
                await self.update()
        except asyncio.CancelledError:
            pass
    
    async def on_ready(self):
        await self.update()
        self.bot.loop.create_task(self.background_update())
        
    async def on_server_join(self, server):
        print('Joined server {}: {}, {} members'.format(server, server.id, len(server.members)))
        
    async def on_server_remove(self, server):
        print('Left server {}: {}, {} members'.format(server, server.id, len(server.members)))