import asyncio
from datetime import timedelta, datetime, tzinfo
import json
import logging
from math import floor
import os
import random
import sys
import time
import traceback

import discord
from discord.ext import commands
import psutil

from cogs5e.charGen import CharGenerator
from cogs5e.diceAlgorithm import Dice
from cogs5e.initiativeTracker import InitTracker
from cogs5e.lookup import Lookup
from cogsmisc.adminUtils import AdminUtils
from cogsmisc.core import Core
from cogsmisc.permissions import Permissions
from cogsmisc.publicity import Publicity
import credentials
from utils import checks
from utils.dataIO import DataIO
from utils.functions import make_sure_path_exists, discord_trim


TESTING = False
if 'test' in sys.argv:
    TESTING = True
prefix = '!' if not TESTING else '#'

# TODO: 
# more flavor text
# More Breath Weapons
description = '''Avrae, a D&D 5e utility bot made by @zhu.exe#4211.'''
bot = commands.Bot(command_prefix=commands.when_mentioned_or(prefix), description=description, pm_help=True)
bot.prefix = prefix

if os.path.isfile('./resources.txt'):
    with open('./resources.txt', 'r') as f:  # this is really inefficient
        resource = list(f)
        bot.mask = int(resource[0], base=2)
else:
    bot.mask = 0x00
    
bot.db = DataIO() if not TESTING else DataIO(testing=True)

logger = logging.getLogger('discord')
logger.setLevel(logging.INFO)
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

#-----COGS-----
diceCog = Dice(bot)
charGenCog = CharGenerator(bot)
initiativeTrackerCog = InitTracker(bot)
adminUtilsCog = AdminUtils(bot)
lookupCog = Lookup(bot)
coreCog = Core(bot)
permissionsCog = Permissions(bot)
publicityCog = Publicity(bot)
cogs = [diceCog,
        charGenCog,
        initiativeTrackerCog,
        adminUtilsCog,
        lookupCog,
        coreCog,
        permissionsCog,
        publicityCog]

@bot.event
async def on_ready():
    print('Logged in as')
    print(bot.user.name)
    print(bot.user.id)
    print('------')
    await enter()

async def enter():
    await bot.wait_until_ready()
    appInfo = await bot.application_info()
    bot.owner = appInfo.owner
    bot.botStats = bot.db.get_whole_dict('botStats')
    statKeys = ["dice_rolled_session", "spells_looked_up_session", "monsters_looked_up_session", "commands_used_session", "dice_rolled_life", "spells_looked_up_life", "monsters_looked_up_life", "commands_used_life"]
    for k in statKeys:
        if k not in bot.botStats.keys():
            bot.botStats[k] = 0
    bot.botStats["dice_rolled_session"] = bot.botStats["spells_looked_up_session"] = bot.botStats["monsters_looked_up_session"] = bot.botStats["commands_used_session"] = 0
    for stat in bot.botStats.keys():
        bot.botStats[stat] = int(bot.botStats[stat])
    bot.db.set_dict('botStats', bot.botStats)
    await bot.change_status(game=discord.Game(name='D&D 5e | !help'))
    
@bot.event
async def on_command_error(error, ctx):
    traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)
    tb = ''.join(traceback.format_exception(type(error), error, error.__traceback__))
    if bot.mask & coreCog.verbose_mask:
        await bot.send_message(ctx.message.channel, "Error: " + str(error))
    elif bot.mask & coreCog.quiet_mask:
        return
    else:
        if isinstance(error, commands.CommandNotFound):
            return
        elif isinstance(error, commands.CheckFailure):
            await bot.send_message(ctx.message.channel, "Error: Either you do not have the permissions to run this command or the command is disabled.")
            return
        elif isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument, commands.NoPrivateMessage)):
            await bot.send_message(ctx.message.channel, "Error: " + str(error) + "\nUse !help " + ctx.command.qualified_name + " for help.")
        elif bot.mask & coreCog.debug_mask:
            await bot.send_message(ctx.message.channel, "Error: " + str(error) + "\nThis incident has been reported to the developer.")
            try:
                await bot.send_message(bot.owner, "Error in channel {} ({}), server {} ({}): {}\nCaused by message: `{}`".format(ctx.message.channel, ctx.message.channel.id, ctx.message.server, ctx.message.server.id, repr(error), ctx.message.content))
            except AttributeError:
                await bot.send_message(bot.owner, "Error in PM with {} ({}): {}\nCaused by message: `{}`".format(ctx.message.author.mention, str(ctx.message.author), repr(error), ctx.message.content))
            for o in discord_trim(tb):
                await bot.send_message(bot.owner, o)
        else:
            await bot.send_message(ctx.message.channel, "Error: " + str(error))
                
@bot.event
async def on_message(message):
    if message.author in adminUtilsCog.muted:
        return
    if message.content.startswith('avraepls'):
        if coreCog.verbose_mask & bot.mask:
            await bot.send_message(message.channel, "`Reseeding RNG...`")
        random.seed()
    if not hasattr(bot, 'global_prefixes'): # bot's still starting up!
        return
    try:
        guild_prefix = bot.global_prefixes.get(message.server.id, bot.prefix)
    except:
        guild_prefix = bot.prefix
    if message.content.startswith(guild_prefix):
        message.content = message.content.replace(guild_prefix, bot.prefix, 1)
    elif message.content.startswith(bot.prefix): return
    await bot.process_commands(message)
    
@bot.event
async def on_command(command, ctx):
    bot.botStats['commands_used_session'] += 1
    bot.botStats['commands_used_life'] += 1
        
async def save_stats():
    await bot.wait_until_ready()
    while not bot.is_closed:
        await asyncio.sleep(3600) #every hour
        bot.db.set_dict('botStats', bot.botStats)
        
        
bot.loop.create_task(save_stats())
            
for cog in cogs:
    bot.add_cog(cog)


if not TESTING:        
    bot.run(credentials.officialToken)  # official token
else:
    bot.run(credentials.testToken) #test token
