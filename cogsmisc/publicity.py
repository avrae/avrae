'''
Created on Dec 29, 2016

@author: andrew
'''
import aiohttp
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
            print('Carbon statistics returned {0.status} for {1}'.format(resp, carbon_payload))

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

    async def on_server_join(self, server):
        await self.update()

    async def on_server_remove(self, server):
        await self.update()

    async def on_ready(self):
        await self.update()
