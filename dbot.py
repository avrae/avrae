import asyncio
import faulthandler
import logging
import os
import sys
import traceback

# this hooks a lot of weird things and needs to be imported early
import utils.newrelic
utils.newrelic.hook_all()

import discord
import motor.motor_asyncio
import sentry_sdk
from aiohttp import ClientOSError, ClientResponseError
from discord.errors import Forbidden, HTTPException, InvalidArgument, NotFound
from discord.ext import commands
from discord.ext.commands.errors import CommandInvokeError

from cogs5e.funcs.lookupFuncs import compendium
from cogs5e.models.errors import AvraeException, EvaluationError
from utils.functions import get_positivity
from utils.help import help_command
from utils.redisIO import RedisIO

TESTING = get_positivity(os.environ.get("TESTING", False))
if 'test' in sys.argv:
    TESTING = True
SHARD_COUNT = None if not TESTING else 1
DEFAULT_PREFIX = os.getenv('DEFAULT_PREFIX', '!')
SENTRY_DSN = os.getenv('SENTRY_DSN') or None

# -----COGS-----
DYNAMIC_COGS = ["cogs5e.dice", "cogs5e.charGen", "cogs5e.homebrew", "cogs5e.lookup", "cogs5e.pbpUtils",
                "cogs5e.gametrack", "cogs5e.initTracker", "cogs5e.sheetManager", "cogsmisc.customization"]
STATIC_COGS = ["cogsmisc.core", "cogsmisc.publicity", "cogsmisc.stats", "cogsmisc.repl", "cogsmisc.adminUtils"]


async def get_prefix(the_bot, message):
    if not message.guild:
        return commands.when_mentioned_or(DEFAULT_PREFIX)(the_bot, message)
    guild_id = str(message.guild.id)
    if guild_id in the_bot.prefixes:
        gp = the_bot.prefixes.get(guild_id, DEFAULT_PREFIX)
    else:  # load from db and cache
        gp_obj = await the_bot.mdb.prefixes.find_one({"guild_id": guild_id})
        if gp_obj is None:
            gp = DEFAULT_PREFIX
        else:
            gp = gp_obj.get("prefix", DEFAULT_PREFIX)
        the_bot.prefixes[guild_id] = gp
    return commands.when_mentioned_or(gp)(the_bot, message)


class Avrae(commands.AutoShardedBot):
    def __init__(self, prefix, description=None, testing=False, **options):
        super(Avrae, self).__init__(prefix, help_command=help_command, description=description, **options)
        self.testing = testing
        self.state = "init"
        self.credentials = Credentials()
        if TESTING:
            self.rdb = RedisIO(testing=True, database_url=self.credentials.test_redis_url)
            self.mclient = motor.motor_asyncio.AsyncIOMotorClient(self.credentials.test_mongo_url)
        else:
            self.rdb = RedisIO(database_url=os.getenv('REDIS_URL', ''))
            self.mclient = motor.motor_asyncio.AsyncIOMotorClient(os.getenv('MONGO_URL', "mongodb://localhost:27017"))

        self.mdb = self.mclient.avrae  # let's just use the avrae db
        self.dynamic_cog_list = DYNAMIC_COGS
        self.prefixes = dict()
        self.muted = set()

        if SENTRY_DSN is not None:
            sentry_sdk.init(dsn=SENTRY_DSN, environment="Development" if TESTING else "Production")

    async def get_server_prefix(self, msg):
        return (await get_prefix(self, msg))[-1]

    async def launch_shards(self):
        if self.shard_count is None:
            recommended_shards, _ = await self.http.get_bot_gateway()
            if recommended_shards >= 96 and not recommended_shards % 16:
                # half, round up to nearest 16
                self.shard_count = recommended_shards // 2 + (16 - (recommended_shards // 2) % 16)
            else:
                self.shard_count = max(recommended_shards // 2, 1)
        log.info(f"Launching {self.shard_count} shards!")
        await super(Avrae, self).launch_shards()

    @staticmethod
    def log_exception(exception=None, context: commands.Context = None):
        if SENTRY_DSN is None:
            return

        with sentry_sdk.push_scope() as scope:
            if context:
                # noinspection PyDunderSlots,PyUnresolvedReferences
                # for some reason pycharm doesn't pick up the attribute setter here
                scope.user = {"id": context.author.id, "username": str(context.author)}
                scope.set_tag("message.content", context.message.content)
                scope.set_tag("is_private_message", context.guild is None)
                scope.set_tag("channel.id", context.channel.id)
                scope.set_tag("channel.name", str(context.channel))
                if context.guild is not None:
                    scope.set_tag("guild.id", context.guild.id)
                    scope.set_tag("guild.name", str(context.guild))
            sentry_sdk.capture_exception(exception)


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


desc = '''
Avrae, a D&D 5e utility bot designed to help you and your friends play D&D online.
A full command list can be found [here](https://avrae.io/commands)!
Invite Avrae to your server [here](https://invite.avrae.io)!
Join the official development server [here](https://support.avrae.io)!
'''
bot = Avrae(prefix=get_prefix, description=desc, pm_help=True,
            shard_count=SHARD_COUNT, testing=TESTING, activity=discord.Game(name='D&D 5e | !help'))

log_formatter = logging.Formatter('%(levelname)s:%(name)s: %(message)s')
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(log_formatter)
logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(handler)
log = logging.getLogger('bot')


@bot.event
async def on_ready():
    log.info('Logged in as')
    log.info(bot.user.name)
    log.info(bot.user.id)
    log.info('------')


@bot.event
async def on_resumed():
    log.info('resumed.')


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return

    elif isinstance(error, AvraeException):
        return await ctx.send(str(error))

    elif isinstance(error, (commands.UserInputError, commands.NoPrivateMessage, ValueError)):
        return await ctx.send(
            f"Error: {str(error)}\nUse `{ctx.prefix}help " + ctx.command.qualified_name + "` for help.")

    elif isinstance(error, commands.CheckFailure):
        msg = str(error) or "You are not allowed to run this command."
        return await ctx.send(f"Error: {msg}")

    elif isinstance(error, commands.CommandOnCooldown):
        return await ctx.send("This command is on cooldown for {:.1f} seconds.".format(error.retry_after))

    elif isinstance(error, CommandInvokeError):
        original = error.original
        if isinstance(original, EvaluationError):  # PM an alias author tiny traceback
            e = original.original
            if not isinstance(e, AvraeException):
                tb = f"```py\nError when parsing expression {original.expression}:\n" \
                     f"{''.join(traceback.format_exception(type(e), e, e.__traceback__, limit=0, chain=False))}\n```"
                try:
                    await ctx.author.send(tb)
                except Exception as e:
                    log.info(f"Error sending traceback: {e}")
            return await ctx.send(str(original))

        elif isinstance(original, AvraeException):
            return await ctx.send(str(original))

        elif isinstance(original, Forbidden):
            try:
                return await ctx.author.send(
                    f"Error: I am missing permissions to run this command. "
                    f"Please make sure I have permission to send messages to <#{ctx.channel.id}>."
                )
            except HTTPException:
                try:
                    return await ctx.send(f"Error: I cannot send messages to this user.")
                except HTTPException:
                    return

        elif isinstance(original, NotFound):
            return await ctx.send("Error: I tried to edit or delete a message that no longer exists.")

        elif isinstance(original, (ClientResponseError, InvalidArgument, asyncio.TimeoutError, ClientOSError)):
            return await ctx.send("Error in Discord API. Please try again.")

        elif isinstance(original, HTTPException):
            if original.response.status == 400:
                return await ctx.send(f"Error: Message is too long, malformed, or empty.\n{original.text}")
            elif original.response.status == 500:
                return await ctx.send("Error: Internal server error on Discord's end. Please try again.")

        elif isinstance(original, OverflowError):
            return await ctx.send(f"Error: A number is too large for me to store.")

    # send error to sentry.io
    if isinstance(error, CommandInvokeError):
        bot.log_exception(error.original, ctx)
    else:
        bot.log_exception(error, ctx)

    await ctx.send(
        f"Error: {str(error)}\nUh oh, that wasn't supposed to happen! "
        f"Please join <http://support.avrae.io> and let us know about the error!")

    log.warning("Error caused by message: `{}`".format(ctx.message.content))
    for line in traceback.format_exception(type(error), error, error.__traceback__):
        log.warning(line)


@bot.event
async def on_message(message):
    if message.author.id in bot.muted:
        return
    await bot.process_commands(message)


@bot.event
async def on_command(ctx):
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
    faulthandler.enable()  # assumes we log errors to stderr, traces segfaults
    bot.state = "run"
    if not bot.rdb.exists('build_num'):
        bot.rdb.set('build_num', 0)
    bot.rdb.incr('build_num')
    bot.loop.create_task(compendium.reload_task(bot.mdb))
    bot.run(bot.credentials.token)
