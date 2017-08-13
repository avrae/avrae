import re

import discord
from discord.ext import commands

from utils.dataIO import DataIO

bot = commands.Bot(command_prefix=commands.when_mentioned, description="Avrae Beta Helper.", pm_help=True, shard_id=0, shard_count=1)

class Credentials:
    pass

import credentials
bot.credentials = Credentials()
bot.credentials.testToken = credentials.testToken
bot.credentials.test_database_url = credentials.test_database_url

bot.db = DataIO(testing=True, test_database_url=bot.credentials.test_database_url)

@bot.event
async def on_ready():
    print('Logged in as')
    print(bot.user.name)
    print(bot.user.id)
    print('------')

@bot.event
async def on_message(message):
    if not message.channel.id == '346421545343647765': return # beta registration listener only
    if not re.match(r'\d{17,18}', message.content): return await bot.delete_message(message) # only look for server IDs
    beta_server_ids = bot.db.jget('beta_server_ids', [])
    beta_server_ids.append(message.content)
    bot.db.jset('beta_server_ids', beta_server_ids)
    try:
        await bot.send_message(message.author, f"Added {message.content} to the beta server list.")
        await bot.send_message(message.author, "You can now invite the beta bot to your server here: <https://discordapp.com/oauth2/authorize?&client_id=219251784445591553&scope=bot&permissions=268561430>")
    except:
        await bot.send_message(message.channel, f"Added {message.content} to the beta server list.")
    beta_role = discord.utils.get(message.server.roles, id='345012069801656323')
    await bot.add_roles(message.author, beta_role)

@bot.event
async def on_server_join(server):
    beta_server_ids = bot.db.jget('beta_server_ids', [])
    if not server.id in beta_server_ids:
        try:
            await bot.send_message(server.owner, "Someone just tried to add me to your server but the server is not part of the Beta Test.")
        except:
            pass
        await bot.leave_server(server)

bot.run(bot.credentials.testToken)  # test token