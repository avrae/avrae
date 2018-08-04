import logging
import os
import sys
import traceback

import discord
import redis
from aiohttp import ClientResponseError
from discord.errors import Forbidden, NotFound, HTTPException, InvalidArgument
from discord.ext import commands
from discord.ext.commands.errors import CommandInvokeError

from cogs5e.models.errors import AvraeException, EvaluationError
from utils.dataIO import DataIO
from utils.functions import discord_trim, get_positivity, list_get, gen_error_message

STATE = "init"
TESTING = get_positivity(os.environ.get("TESTING", False))
if 'test' in sys.argv:
    TESTING = True
prefix = '!' if not TESTING else '#'
shard_id = 0
shard_count = 1
SHARDED = False
if '-s' in sys.argv:
    temp_shard_id = list_get(sys.argv.index('-s') + 1, None, sys.argv)
    if temp_shard_id is not None:
        shard_count = os.environ.get('SHARDS', 1)
        shard_id = temp_shard_id if int(temp_shard_id) < int(shard_count) else 0
        SHARDED = True

description = '''Avrae, a D&D 5e utility bot made by @zhu.exe#4211.
A full command list can be found [here](https://avrae.io/commands)!
Invite Avrae to your server [here](https://discordapp.com/oauth2/authorize?&client_id=261302296103747584&scope=bot&permissions=36727808)!
Join the official testing server [here](https://discord.gg/pQbd4s6)!
Love the bot? Donate to me [here](https://www.paypal.me/avrae)! \u2764
'''
if not SHARDED:
    bot = commands.Bot(command_prefix=commands.when_mentioned_or(prefix), description=description, pm_help=True,
                       shard_id=0, shard_count=1, max_messages=1000)
else:
    bot = commands.Bot(command_prefix=commands.when_mentioned_or(prefix), description=description, pm_help=True,
                       shard_id=int(shard_id), shard_count=int(shard_count), max_messages=1000)
bot.prefix = prefix
bot.remove_command('help')
bot.testing = TESTING


class Credentials:
    pass


# CREDENTIALS
try:
    # noinspection PyUnresolvedReferences
    import credentials

    bot.credentials = Credentials()
    bot.credentials.token = credentials.officialToken
    bot.credentials.test_database_url = credentials.test_database_url
    if TESTING:
        bot.credentials.token = credentials.testToken
    if 'ALPHA_TOKEN' in os.environ:
        bot.credentials.token = os.environ.get("ALPHA_TOKEN")
except ImportError:
    raise Exception("Credentials not found.")

bot.db = DataIO() if not TESTING else DataIO(testing=True, test_database_url=bot.credentials.test_database_url)

log_formatter = logging.Formatter(
    '%(asctime)s s.{}:%(levelname)s:%(name)s: %(message)s'.format(getattr(bot, 'shard_id', 0)))
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(log_formatter)
filehandler = logging.FileHandler(f"temp/log_shard_{bot.shard_id}_build_{bot.db.get('build_num')}.log", mode='w')
filehandler.setFormatter(log_formatter)
logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(handler)
logger.addHandler(filehandler)

log = logging.getLogger('bot')
msglog = logging.getLogger('messages')

# -----COGS-----
DYNAMIC_COGS = ["cogs5e.dice", "cogs5e.charGen", "cogs5e.gametrack", "cogs5e.homebrew", "cogs5e.initTracker",
                "cogs5e.lookup", "cogs5e.pbpUtils", "cogs5e.sheetManager", "cogsmisc.customization"]
STATIC_COGS = ["cogsmisc.adminUtils", "cogsmisc.core", "cogsmisc.permissions", "cogsmisc.publicity", "cogsmisc.repl",
               "cogsmisc.stats"]


@bot.event
async def on_ready():
    print('Logged in as')
    print(bot.user.name)
    print(bot.user.id)
    print('Shard ' + str(getattr(bot, 'shard_id', 0)))
    print('------')
    await enter()


async def enter():
    await bot.wait_until_ready()
    appInfo = await bot.application_info()
    bot.owner = appInfo.owner
    if not bot.db.exists('build_num'): bot.db.set('build_num', 114)  # this was added in build 114
    if getattr(bot, "shard_id", 0) == 0: bot.db.incr('build_num')
    await bot.change_presence(game=discord.Game(name='D&D 5e | !help'))


@bot.event
async def on_resumed():
    log.info('resumed.')


@bot.event
async def on_command_error(error, ctx):
    if isinstance(error, commands.CommandNotFound):
        return
    log.debug("Error caused by message: `{}`".format(ctx.message.content))
    log.debug('\n'.join(traceback.format_exception(type(error), error, error.__traceback__)))
    if isinstance(error, AvraeException):
        return await bot.send_message(ctx.message.channel, str(error))
    tb = ''.join(traceback.format_exception(type(error), error, error.__traceback__))
    if isinstance(error, commands.CheckFailure):
        await bot.send_message(ctx.message.channel,
                               "Error: Either you do not have the permissions to run this command, the command is disabled, or something went wrong internally.")
        return
    elif isinstance(error,
                    (commands.MissingRequiredArgument, commands.BadArgument, commands.NoPrivateMessage, ValueError)):
        return await bot.send_message(ctx.message.channel, "Error: " + str(
            error) + "\nUse `!help " + ctx.command.qualified_name + "` for help.")
    elif isinstance(error, commands.CommandOnCooldown):
        return await bot.send_message(ctx.message.channel,
                                      "This command is on cooldown for {:.1f} seconds.".format(error.retry_after))
    elif isinstance(error, CommandInvokeError):
        original = error.original
        if isinstance(original, EvaluationError):  # PM an alias author tiny traceback
            e = original.original
            if not isinstance(e, AvraeException):
                tb = f"```py\n{''.join(traceback.format_exception(type(e), e, e.__traceback__, limit=0, chain=False))}\n```"
                try:
                    await bot.send_message(ctx.message.author, tb)
                except Exception as e:
                    log.info(f"Error sending traceback: {e}")
        if isinstance(original, AvraeException):
            return await bot.send_message(ctx.message.channel, str(original))
        if isinstance(original, Forbidden):
            try:
                return await bot.send_message(ctx.message.author,
                                              "Error: I am missing permissions to run this command. Please make sure I have permission to send messages to <#{}>.".format(
                                                  ctx.message.channel.id))
            except:
                try:
                    return await bot.send_message(ctx.message.channel, f"Error: I cannot send messages to this user.")
                except:
                    return
        if isinstance(original, NotFound):
            return await bot.send_message(ctx.message.channel,
                                          "Error: I tried to edit or delete a message that no longer exists.")
        if isinstance(original, ValueError) and str(original) in ("No closing quotation", "No escaped character"):
            return await bot.send_message(ctx.message.channel, "Error: No closing quotation.")
        if isinstance(original, AttributeError) and str(original) in ("'NoneType' object has no attribute 'name'",):
            return await bot.send_message(ctx.message.channel, "Error in Discord API. Please try again.")
        if isinstance(original, (ClientResponseError, InvalidArgument)):
            return await bot.send_message(ctx.message.channel, "Error in Discord API. Please try again.")
        if isinstance(original, HTTPException):
            if original.response.status == 400:
                return await bot.send_message(ctx.message.channel, "Error: Message is too long, malformed, or empty.")
            if original.response.status == 500:
                return await bot.send_message(ctx.message.channel,
                                              "Error: Internal server error on Discord's end. Please try again.")
        if isinstance(original, redis.ResponseError):
            await bot.send_message(ctx.message.channel,
                                   "Error: I am having an issue writing to my database. Please report this to the dev!")
            return await bot.send_message(bot.owner, f"Database error!\n{repr(original)}")

    error_msg = gen_error_message()

    await bot.send_message(ctx.message.channel,
                           f"Error: {str(error)}\nUh oh, that wasn't supposed to happen! "
                           f"Please join <https://support.avrae.io> and tell the developer that {error_msg}!")
    try:
        await bot.send_message(bot.owner,
                               f"**{error_msg}**\n" \
                               + "Error in channel {} ({}), server {} ({}), shard {}: {}\nCaused by message: `{}`".format(
                                   ctx.message.channel, ctx.message.channel.id, ctx.message.server,
                                   ctx.message.server.id, getattr(bot, 'shard_id', 0), repr(error),
                                   ctx.message.content))
    except AttributeError:
        await bot.send_message(bot.owner, f"**{error_msg}**\n" \
                               + "Error in PM with {} ({}), shard 0: {}\nCaused by message: `{}`".format(
            ctx.message.author.mention, str(ctx.message.author), repr(error), ctx.message.content))
    for o in discord_trim(tb):
        await bot.send_message(bot.owner, o)
    log.error("Error caused by message: `{}`".format(ctx.message.content))
    traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)


@bot.event
async def on_message(message):
    try:
        msglog.debug(
            "chan {0.channel} ({0.channel.id}), serv {0.server} ({0.server.id}), author {0.author} ({0.author.id}): "
            "{0.content}".format(message))
    except AttributeError:
        msglog.debug("PM with {0.author} ({0.author.id}): {0.content}".format(message))
    if message.author.id in bot.get_cog("AdminUtils").muted:
        return
    if not hasattr(bot, 'global_prefixes'):  # bot's still starting up!
        return
    try:
        guild_prefix = bot.global_prefixes.get(message.server.id, bot.prefix)
    except:
        guild_prefix = bot.prefix
    if message.content.startswith(guild_prefix):
        message.content = message.content.replace(guild_prefix, bot.prefix, 1)
    elif message.content.startswith(bot.prefix):
        return
    if message.content.startswith(bot.prefix) and STATE == "init":
        return await bot.send_message(message.channel, "Bot is initializing, try again in a few seconds!")
    await bot.process_commands(message)


@bot.event
async def on_command(command, ctx):
    bot.db.incr('commands_used_life')
    try:
        log.debug(
            "Command called in channel {0.message.channel} ({0.message.channel.id}), server {0.message.server} ({0.message.server.id}): {0.message.content}".format(
                ctx))
    except AttributeError:
        log.debug("Command in PM with {0.message.author} ({0.message.author.id}): {0.message.content}".format(ctx))


for cog in DYNAMIC_COGS:
    bot.load_extension(cog)

for cog in STATIC_COGS:
    bot.load_extension(cog)

if SHARDED: log.info("I am shard {} of {}.".format(str(int(bot.shard_id) + 1), str(bot.shard_count)))

STATE = "run"
bot.run(bot.credentials.token)
