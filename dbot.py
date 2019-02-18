import asyncio
import logging
import os
import sys
import traceback

import discord
import motor.motor_asyncio
import redis
from aiohttp import ClientResponseError
from discord.errors import Forbidden, HTTPException, InvalidArgument, NotFound
from discord.ext import commands
from discord.ext.commands.errors import CommandInvokeError

from cogs5e.models.errors import AvraeException, EvaluationError
from utils.functions import discord_trim, gen_error_message, get_positivity
from utils.redisIO import RedisIO

TESTING = get_positivity(os.environ.get("TESTING", False))
if 'test' in sys.argv:
    TESTING = True
SHARD_COUNT = 20 if not TESTING else 1
prefix = '!' if not TESTING else '#'

# -----COGS-----
DYNAMIC_COGS = ["cogs5e.dice", "cogs5e.charGen", "cogs5e.homebrew", "cogs5e.lookup", "cogs5e.pbpUtils",
                "cogs5e.gametrack", "cogs5e.initTracker", "cogs5e.sheetManager", "cogsmisc.customization"]
STATIC_COGS = ["cogsmisc.core", "cogsmisc.publicity", "cogsmisc.stats", "cogsmisc.repl", "cogsmisc.adminUtils",
               "cogsmisc.permissions", "utils.help"]


def get_prefix(b, message):
    if not message.guild:
        return commands.when_mentioned_or(prefix)(b, message)
    gp = b.prefixes.get(str(message.guild.id), '!')
    return commands.when_mentioned_or(gp)(b, message)


class Avrae(commands.AutoShardedBot):
    def __init__(self, prefix, formatter=None, description=None, pm_help=False, testing=False,
                 **options):
        super(Avrae, self).__init__(prefix, formatter, description, pm_help, **options)
        self.remove_command("help")
        self.testing = testing
        self.state = "init"
        self.credentials = Credentials()
        if TESTING:
            self.rdb = RedisIO(testing=True, test_database_url=self.credentials.test_redis_url)
            self.mclient = motor.motor_asyncio.AsyncIOMotorClient(self.credentials.test_mongo_url)
        else:
            self.rdb = RedisIO()
            self.mclient = motor.motor_asyncio.AsyncIOMotorClient("mongodb://localhost:27017")

        self.mdb = self.mclient.avrae  # let's just use the avrae db
        self.dynamic_cog_list = DYNAMIC_COGS
        self.owner = None
        self.prefixes = self.rdb.not_json_get("prefixes", {})

    def get_server_prefix(self, msg):
        return get_prefix(self, msg)[-1]


class Credentials:
    def __init__(self):
        try:
            import credentials
        except ImportError:
            raise Exception("Credentials not found.")
        self.token = credentials.officialToken
        self.test_redis_url = credentials.test_redis_url
        self.test_mongo_url = credentials.test_mongo_url
        if TESTING:
            self.token = credentials.testToken
        if 'ALPHA_TOKEN' in os.environ:
            self.token = os.environ.get("ALPHA_TOKEN")


desc = '''Avrae, a D&D 5e utility bot made by @zhu.exe#4211.
A full command list can be found [here](https://avrae.io/commands)!
Invite Avrae to your server [here](https://discordapp.com/oauth2/authorize?&client_id=261302296103747584&scope=bot&permissions=36727808)!
Join the official testing server [here](https://discord.gg/pQbd4s6)!
Love the bot? Donate to me [here](https://www.paypal.me/avrae)! \u2764
'''
bot = Avrae(prefix=get_prefix, description=desc, pm_help=True,
            shard_count=int(SHARD_COUNT), testing=TESTING, activity=discord.Game(name='D&D 5e | !help'))

log_formatter = logging.Formatter('%(asctime)s %(levelname)s:%(name)s: %(message)s')
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(log_formatter)
filehandler = logging.FileHandler(f"temp/log_build_{bot.rdb.get('build_num')}.log", mode='w')
filehandler.setFormatter(log_formatter)
logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(handler)
logger.addHandler(filehandler)

log = logging.getLogger('bot')
msglog = logging.getLogger('messages')


@bot.event
async def on_ready():
    print('Logged in as')
    print(bot.user.name)
    print(bot.user.id)
    print('------')
    if not bot.owner:
        await enter()


async def enter():
    await bot.wait_until_ready()
    appInfo = await bot.application_info()
    bot.owner = appInfo.owner


@bot.event
async def on_resumed():
    log.info('resumed.')


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    log.debug("Error caused by message: `{}`".format(ctx.message.content))
    log.debug('\n'.join(traceback.format_exception(type(error), error, error.__traceback__)))
    if isinstance(error, AvraeException):
        return await ctx.send(str(error))
    tb = ''.join(traceback.format_exception(type(error), error, error.__traceback__))
    if isinstance(error,
                    (commands.MissingRequiredArgument, commands.BadArgument, commands.NoPrivateMessage, ValueError)):
        return await ctx.send("Error: " + str(
            error) + f"\nUse `{ctx.prefix}help " + ctx.command.qualified_name + "` for help.")
    elif isinstance(error, commands.CheckFailure):
        return await ctx.send("Error: You are not allowed to run this command.")
    elif isinstance(error, commands.CommandOnCooldown):
        return await ctx.send("This command is on cooldown for {:.1f} seconds.".format(error.retry_after))
    elif isinstance(error, CommandInvokeError):
        original = error.original
        if isinstance(original, EvaluationError):  # PM an alias author tiny traceback
            e = original.original
            if not isinstance(e, AvraeException):
                tb = f"```py\n{''.join(traceback.format_exception(type(e), e, e.__traceback__, limit=0, chain=False))}\n```"
                try:
                    await ctx.author.send(tb)
                except Exception as e:
                    log.info(f"Error sending traceback: {e}")
        if isinstance(original, AvraeException):
            return await ctx.send(str(original))
        if isinstance(original, Forbidden):
            try:
                return await ctx.author.send(
                    f"Error: I am missing permissions to run this command. "
                    f"Please make sure I have permission to send messages to <#{ctx.channel.id}>."
                )
            except:
                try:
                    return await ctx.send(f"Error: I cannot send messages to this user.")
                except:
                    return
        if isinstance(original, NotFound):
            return await ctx.send("Error: I tried to edit or delete a message that no longer exists.")
        if isinstance(original, ValueError) and str(original) in ("No closing quotation", "No escaped character"):
            return await ctx.send("Error: No closing quotation.")
        if isinstance(original, AttributeError) and str(original) in ("'NoneType' object has no attribute 'name'",):
            return await ctx.send("Error in Discord API. Please try again.")
        if isinstance(original, (ClientResponseError, InvalidArgument, asyncio.TimeoutError)):
            return await ctx.send("Error in Discord API. Please try again.")
        if isinstance(original, HTTPException):
            if original.response.status == 400:
                return await ctx.send("Error: Message is too long, malformed, or empty.")
            if original.response.status == 500:
                return await ctx.send("Error: Internal server error on Discord's end. Please try again.")
        if isinstance(original, redis.ResponseError):
            await ctx.send(
                "Error: I am having an issue writing to my database. Please report this to the dev!")
            return await bot.owner.send(f"Database error!\n{repr(original)}")
        if isinstance(original, OverflowError):
            return await ctx.send(
                f"Error: A number is too large for me to store. "
                f"This generally means you've done something terribly wrong.")

    error_msg = gen_error_message()

    await ctx.send(
        f"Error: {str(error)}\nUh oh, that wasn't supposed to happen! "
        f"Please join <http://support.avrae.io> and tell the developer that {error_msg}!")
    try:
        await bot.owner.send(
            f"**{error_msg}**\n" \
            + "Error in channel {} ({}), server {} ({}): {}\nCaused by message: `{}`".format(
                ctx.channel, ctx.channel.id, ctx.guild,
                ctx.guild.id, repr(error),
                ctx.message.content))
    except AttributeError:
        await bot.owner.send(f"**{error_msg}**\n" \
                             + "Error in PM with {} ({}), shard 0: {}\nCaused by message: `{}`".format(
            ctx.author.mention, str(ctx.author), repr(error), ctx.message.content))
    for o in discord_trim(tb):
        await bot.owner.send(o)
    log.error("Error caused by message: `{}`".format(ctx.message.content))
    traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)


@bot.event
async def on_message(message):
    try:
        msglog.debug(
            "chan {0.channel} ({0.channel.id}), serv {0.guild} ({0.guild.id}), author {0.author} ({0.author.id}): "
            "{0.content}".format(message))
    except AttributeError:
        msglog.debug("PM with {0.author} ({0.author.id}): {0.content}".format(message))
    if str(message.author.id) in bot.get_cog("AdminUtils").muted:
        return
    await bot.process_commands(message)


@bot.event
async def on_command(ctx):
    bot.rdb.incr('commands_used_life')
    try:
        log.debug(
            "cmd: chan {0.message.channel} ({0.message.channel.id}), serv {0.message.guild} ({0.message.guild.id}), "
            "auth {0.message.author} ({0.message.author.id}): {0.message.content}".format(
                ctx))
    except AttributeError:
        log.debug("Command in PM with {0.message.author} ({0.message.author.id}): {0.message.content}".format(ctx))


for cog in DYNAMIC_COGS:
    bot.load_extension(cog)

for cog in STATIC_COGS:
    bot.load_extension(cog)

if __name__ == '__main__':
    bot.state = "run"
    if not bot.rdb.exists('build_num'): bot.rdb.set('build_num', 114)  # this was added in build 114
    bot.rdb.incr('build_num')
    bot.run(bot.credentials.token)
