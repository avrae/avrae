import asyncio
from datetime import timedelta, datetime, tzinfo
import json
import logging
import os
import random
import time

import discord
from discord.ext import commands

import adminUtils
import checks
from cogs5e import charGen
from cogs5e import diceAlgorithm
from cogs5e import initiativeTracker
from cogs5e import lookup
from cogs5e import monsterParse
from cogs5e import spellParse
import credentials
from math import floor


TESTING = False
prefix = '.' if not TESTING else '#'

# TODO: 
# more flavor text
# More Breath Weapons
description = '''Avrae, a D&D 5e utility bot made by @zhu.exe#4211.'''
bot = commands.Bot(command_prefix=commands.when_mentioned_or(prefix), description=description, pm_help=True)

changelog = "```I'm too lazy to update the changelog.```"

start_time = time.monotonic()
atDM = "<@187421759484592128>"
owner = None
appInfo = None

userStats = None # dict with struct {user: {stat: val}} - stats: favMon, favSpell, numCrits, numCrails

if os.path.isfile('./resources.txt'):
    with open('./resources.txt', 'r') as f:  # this is really inefficient
        resource = list(f)
        mask = int(resource[0], base=2)
else:
    mask = 0x00
logger = logging.getLogger('discord')
logger.setLevel(logging.INFO)
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

quiet_mask = 0x01
verbose_mask = 0x02
debug_mask = 0x04
monitor_mask = 0x08

#-----COGS-----
diceCog = diceAlgorithm.Dice(bot)
charGenCog = charGen.CharGenerator(bot)
monsterParseCog = monsterParse.MonsterParser(bot)
spellParseCog = spellParse.SpellParser(bot)
initiativeTrackerCog = initiativeTracker.InitTracker(bot)
adminUtilsCog = adminUtils.AdminUtils(bot)
lookupCog = lookup.Lookup(bot)
cogs = [diceCog,
        charGenCog,
        monsterParseCog,
        spellParseCog,
        initiativeTrackerCog,
        adminUtilsCog,
        lookupCog]

@bot.event
async def on_ready():
    print('Logged in as')
    print(bot.user.name)
    print(bot.user.id)
    print('------')
    await enter()

async def enter():
    global appInfo
    global userStats
    global owner
    await bot.wait_until_ready()
    appInfo = await bot.application_info()
    owner = appInfo.owner
    if os.path.isfile("./userStats.json"):
        with open('./userStats.json', mode='r', encoding='utf-8') as f:
            userStats = json.load(f)
    else:
        userStats = {}
    await bot.change_status(game=discord.Game(name='D&D 5e'))
    
@bot.event
async def on_command_error(error, ctx):
    if mask & verbose_mask:
        await bot.send_message(ctx.message.channel, "Error: " + str(error))
    elif mask & quiet_mask:
        print("Error: " + repr(error))
    else:
        if isinstance(error, commands.CommandNotFound):
            print("Error: " + repr(error))
            return
        elif isinstance(error, commands.CheckFailure):
            await bot.send_message(ctx.message.channel, "Error: Missing permissions. Use .help <COMMAND> to check permission requirements.")
        else:
            await bot.send_message(ctx.message.channel, "Error: " + str(error))
        if mask & debug_mask:
            try:
                await bot.send_message(owner, "Error in channel {} ({}), server {} ({}): {}\nCaused by message: `{}`".format(ctx.message.channel, ctx.message.channel.id, ctx.message.server, ctx.message.server.id, repr(error), ctx.message.content))
            except AttributeError:
                await bot.send_message(owner, "Error in PM with {}: {}\nCaused by message: `{}`".format(ctx.message.author.mention, repr(error), ctx.message.content))

@bot.event
async def on_message(message):
    if message.author in adminUtilsCog.muted:
        return
    if message.content.startswith('avraepls'):
        if verbose_mask & mask:
            await bot.send_message(message.channel, "`Reseeding RNG...`")
        random.seed()
    
    await bot.process_commands(message)
        
@bot.command(pass_context=True)
@checks.admin_or_permissions(manage_messages=True)
async def purge(ctx, num):
    """Purges messages from the channel.
    Usage: .purge <Number of messages to purge>
    Requires: Bot Admin or Manage Messages"""
    if mask & monitor_mask:
        await bot.send_message(owner, "Purging {} messages from {}.".format(str(int(num) + 1), ctx.message.server))
    try:
        await bot.purge_from(ctx.message.channel, limit=(int(num) + 1))
    except Exception as e:
        await bot.say('Failed to purge: ' + str(e))
    
@bot.command(pass_context=True, hidden=True)
@checks.is_owner()
async def bitmask(ctx, *args):
    """Edits/shows the bitmask.
    Requires: Owner"""
    global mask
    if args:
        mask = int(args[0], base=2)
        if not len(args[0]) == 8:
            await bot.say("Invalid bitmask!")
        else:
            with open('./resources.txt', 'w') as f:
                f.write("{0:0>8b}".format(mask))
    await bot.say("```Bitmask: {0:0>8b}```".format(mask))
    
@bot.command(pass_context=True, hidden=True)
@checks.is_owner()
async def toggle_flag(ctx, flag : str):
    """Toggles a bitmask flag.
    Requires: Owner"""
    global mask
    if flag.lower() == 'verbose':
        mask = mask ^ verbose_mask
    elif flag.lower() == 'quiet':
        mask = mask ^ quiet_mask
    elif flag.lower() == 'debug':
        mask = mask ^ debug_mask
    elif flag.lower() == 'monitor':
        mask = mask ^ monitor_mask
    with open('./resources.txt', 'w') as f:
        f.write("{0:0>8b}".format(mask))
    await bot.say('Toggled flag ' + flag + "```Bitmask: {0:0>8b}```".format(mask))
    
@bot.command()
async def changes():
    """Shows the latest changelog."""
    await bot.say(changelog)
    
@bot.command(pass_context=True)
async def bug(ctx, *, report:str):
    """Reports a bug to the developer."""
    await bot.send_message(owner, "Bug reported by {} from {}:\n{}".format(ctx.message.author.mention, ctx.message.server, report))
    await bot.say("Bug report sent to developer! You can ping him here: " + atDM)
    
@bot.command()
async def uptime():
    """Says how long Avrae has been online."""
    end_time = time.monotonic()
    await bot.say("Up for {0}.".format(str(timedelta(seconds=round(end_time - start_time)))))
        
@bot.command()
async def temp():
    """Get's Avrae's temperature."""
    with open('/sys/class/thermal/thermal_zone0/temp') as f:
        tempC = int(f.read()) / 1e3
    await bot.say("`Temp: {} ºC`".format(tempC))
    
@bot.command(hidden=True)
@checks.mod_or_permissions(manage_nicknames=True)
async def avatar(user : discord.User):
    """Gets a user's avatar.
    Usage: .avatar <USER>
    Requires: Bot Mod or Manage Nicknames"""
    if user.avatar_url is not "":
        await bot.say(user.avatar_url)
    else:
        await bot.say(user.display_name + " is using the default avatar.")

@bot.command(pass_context=True)
async def ping(ctx):
    """Checks the ping time to the bot."""
    now = datetime.utcnow()
    pong = await bot.say("Pong.")
    delta = pong.timestamp - now
    msec = floor(delta.total_seconds() * 1000)
    await bot.edit_message(pong, "Pong.\nPing = {} ms.".format(msec))
    
@bot.command()
async def invite():
    """Prints a link to invite Avrae to your server."""
    await bot.say("https://discordapp.com/oauth2/authorize?&client_id=***REMOVED***&scope=bot")
            
for cog in cogs:
    bot.add_cog(cog)


if not TESTING:        
    bot.run(credentials.officialToken)  # official token
else:
    bot.run(credentials.testToken) #test token
