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

import adminUtils
import checks
from cogs5e import charGen
from cogs5e import diceAlgorithm
from cogs5e import initiativeTracker
from cogs5e import lookup
from cogs5e import spellParse
import credentials
from functions import make_sure_path_exists


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
initiativeTrackerCog = initiativeTracker.InitTracker(bot)
adminUtilsCog = adminUtils.AdminUtils(bot)
lookupCog = lookup.Lookup(bot)
cogs = [diceCog,
        charGenCog,
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
    
@bot.event
async def on_command(command, ctx):
    bot.botStats['commands_used_session'] += 1
    bot.botStats['commands_used_life'] += 1
        
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
    
@bot.command(aliases=['stats'])
async def about():
    """Information about the bot."""
    embed = discord.Embed(description='Avrae, a bot to streamline D&D 5e online.')
    embed.title = "Invite Avrae to your server!"
    embed.url = "https://discordapp.com/oauth2/authorize?&client_id=***REMOVED***&scope=bot"
    embed.colour = 0xec3333
    embed.set_author(name=str(owner), icon_url=owner.avatar_url)
    total_members = sum(len(s.members) for s in bot.servers)
    total_online  = sum(1 for m in bot.get_all_members() if m.status != discord.Status.offline)
    unique_members = set(bot.get_all_members())
    unique_online = sum(1 for m in unique_members if m.status != discord.Status.offline)
    text = len([c for c in bot.get_all_channels() if c.type is discord.ChannelType.text])
    voice = len([c for c in bot.get_all_channels() if c.type is discord.ChannelType.voice])
    members = '%s total\n%s online\n%s unique\n%s unique online' % (total_members, total_online, len(unique_members), unique_online)
    embed.add_field(name='Members', value=members)
    embed.add_field(name='Channels', value='{} total\n{} text\n{} voice'.format(text + voice, text, voice))
    embed.add_field(name='Uptime', value=str(timedelta(seconds=round(time.monotonic() - start_time))))
    embed.set_footer(text='May the RNG be with you', icon_url='http://www.clipartkid.com/images/25/six-sided-dice-clip-art-at-clker-com-vector-clip-art-online-royalty-tUAGdd-clipart.png')
    commands_run = "{commands_used_life} total\n{dice_rolled_life} dice rolled\n{spells_looked_up_life} spells looked up\n{monsters_looked_up_life} monsters looked up".format(**bot.botStats)
    embed.add_field(name="Commands Run", value=commands_run)
    embed.add_field(name="Servers", value=len(bot.servers))
    memory_usage = psutil.Process().memory_full_info().uss / 1024**2
    embed.add_field(name='Memory Usage', value='{:.2f} MiB'.format(memory_usage))
    
    await bot.say(embed=embed)
    
async def save_stats():
    await bot.wait_until_ready()
    while not bot.is_closed:
        await asyncio.sleep(3600) #every hour
        make_sure_path_exists('./saves/stats/')
        path = './saves/stats/botStats.avrae'
        with open(path, mode='w', encoding='utf-8') as f:
            json.dump(bot.botStats, f, sort_keys=True, indent=4)
        
        
bot.loop.create_task(save_stats())
            
for cog in cogs:
    bot.add_cog(cog)


if not TESTING:        
    bot.run(credentials.officialToken)  # official token
else:
    bot.run(credentials.testToken) #test token
