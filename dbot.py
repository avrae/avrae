import asyncio
from datetime import timedelta, datetime, tzinfo
import json
import logging
from math import floor
import os
import random
import time

import discord
from discord.ext import commands
import psutil

from cogs5e import charGen
from cogs5e import diceAlgorithm
from cogs5e import initiativeTracker
from cogs5e import lookup
from cogsmisc import adminUtils, core
import credentials
from utils import checks
from utils.dataIO import DataIO
from utils.functions import make_sure_path_exists


TESTING = False
prefix = '!' if not TESTING else '#'

# TODO: 
# more flavor text
# More Breath Weapons
description = '''Avrae, a D&D 5e utility bot made by @zhu.exe#4211.'''
bot = commands.Bot(command_prefix=commands.when_mentioned_or(prefix), description=description, pm_help=True)

if os.path.isfile('./resources.txt'):
    with open('./resources.txt', 'r') as f:  # this is really inefficient
        resource = list(f)
        bot.mask = int(resource[0], base=2)
else:
    bot.mask = 0x00
    
bot.db = DataIO() if not TESTING else None

logger = logging.getLogger('discord')
logger.setLevel(logging.INFO)
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

#-----COGS-----
diceCog = diceAlgorithm.Dice(bot)
charGenCog = charGen.CharGenerator(bot)
initiativeTrackerCog = initiativeTracker.InitTracker(bot)
adminUtilsCog = adminUtils.AdminUtils(bot)
lookupCog = lookup.Lookup(bot)
coreCog = core.Core(bot)
cogs = [diceCog,
        charGenCog,
        initiativeTrackerCog,
        adminUtilsCog,
        lookupCog,
        coreCog]

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
    if TESTING:
        make_sure_path_exists("./saves/stats/")
        if os.path.isfile("./saves/stats/botStats.avrae"):
            with open('./saves/stats/botStats.avrae', mode='r', encoding='utf-8') as f:
                bot.botStats = json.load(f)
            bot.botStats["dice_rolled_session"] = bot.botStats["spells_looked_up_session"] = bot.botStats["monsters_looked_up_session"] = bot.botStats["commands_used_session"] = 0
    
        else:
            bot.botStats = {"dice_rolled_session":0,
                            "spells_looked_up_session":0,
                            "monsters_looked_up_session":0,
                            "commands_used_session":0,
                            "dice_rolled_life":0,
                            "spells_looked_up_life":0,
                            "monsters_looked_up_life":0,
                            "commands_used_life":0}
    else:
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
    if bot.mask & coreCog.verbose_mask:
        await bot.send_message(ctx.message.channel, "Error: " + str(error))
    elif bot.mask & coreCog.quiet_mask:
        print("Error: " + repr(error))
    else:
        if isinstance(error, commands.CommandNotFound):
            print("Error: " + repr(error))
            return
        elif isinstance(error, commands.CheckFailure):
            await bot.send_message(ctx.message.channel, "Error: Missing permissions. Use .help <COMMAND> to check permission requirements.")
        else:
            await bot.send_message(ctx.message.channel, "Error: " + str(error))
        if bot.mask & coreCog.debug_mask:
            try:
                await bot.send_message(bot.owner, "Error in channel {} ({}), server {} ({}): {}\nCaused by message: `{}`".format(ctx.message.channel, ctx.message.channel.id, ctx.message.server, ctx.message.server.id, repr(error), ctx.message.content))
            except AttributeError:
                await bot.send_message(bot.owner, "Error in PM with {}: {}\nCaused by message: `{}`".format(ctx.message.author.mention, repr(error), ctx.message.content))

@bot.event
async def on_message(message):
    if message.author in adminUtilsCog.muted:
        return
    if message.content.startswith('avraepls'):
        if coreCog.verbose_mask & bot.mask:
            await bot.send_message(message.channel, "`Reseeding RNG...`")
        random.seed()
    
    await bot.process_commands(message)
    
@bot.event
async def on_command(command, ctx):
    bot.botStats['commands_used_session'] += 1
    bot.botStats['commands_used_life'] += 1
        
async def save_stats():
    await bot.wait_until_ready()
    while not bot.is_closed:
        await asyncio.sleep(3600) #every hour
        if TESTING:
            make_sure_path_exists('./saves/stats/')
            path = './saves/stats/botStats.avrae'
            with open(path, mode='w', encoding='utf-8') as f:
                json.dump(bot.botStats, f, sort_keys=True, indent=4)
        else:
            bot.db.set_dict('botStats', bot.botStats)
        
        
bot.loop.create_task(save_stats())
            
for cog in cogs:
    bot.add_cog(cog)


if not TESTING:        
    bot.run(credentials.officialToken)  # official token
else:
    bot.run(credentials.testToken) #test token
