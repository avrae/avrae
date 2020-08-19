import asyncio
import faulthandler
import logging
import sys
import traceback

# this hooks a lot of weird things and needs to be imported early
import utils.newrelic

utils.newrelic.hook_all()
from utils import clustering, config

import aioredis
import d20
import discord
import motor.motor_asyncio
import sentry_sdk
from aiohttp import ClientOSError, ClientResponseError
from discord.errors import Forbidden, HTTPException, InvalidArgument, NotFound
from discord.ext import commands
from discord.ext.commands.errors import CommandInvokeError

from aliasing.helpers import handle_alias_exception, handle_alias_required_licenses, handle_aliases
from cogs5e.models.errors import AvraeException, RequiresLicense
from aliasing.errors import CollectableRequiresLicenses, EvaluationError
from gamedata.compendium import compendium
from gamedata.ddb import BeyondClient, BeyondClientBase
from gamedata.lookuputils import handle_required_license
from utils.aldclient import AsyncLaunchDarklyClient
from utils.help import help_command
from utils.redisIO import RedisIO

# -----COGS-----
COGS = (
    "cogs5e.dice", "cogs5e.charGen", "cogs5e.homebrew", "cogs5e.lookup", "cogs5e.pbpUtils",
    "cogs5e.gametrack", "cogs5e.initTracker", "cogs5e.sheetManager", "cogsmisc.customization", "cogsmisc.core",
    "cogsmisc.publicity", "cogsmisc.stats", "cogsmisc.repl", "cogsmisc.adminUtils"
)


async def get_prefix(the_bot, message):
    if not message.guild:
        return commands.when_mentioned_or(config.DEFAULT_PREFIX)(the_bot, message)
    guild_id = str(message.guild.id)
    if guild_id in the_bot.prefixes:
        gp = the_bot.prefixes.get(guild_id, config.DEFAULT_PREFIX)
    else:  # load from db and cache
        gp_obj = await the_bot.mdb.prefixes.find_one({"guild_id": guild_id})
        if gp_obj is None:
            gp = config.DEFAULT_PREFIX
        else:
            gp = gp_obj.get("prefix", config.DEFAULT_PREFIX)
        the_bot.prefixes[guild_id] = gp
    return commands.when_mentioned_or(gp)(the_bot, message)


class Avrae(commands.AutoShardedBot):
    def __init__(self, prefix, description=None, testing=False, **options):
        super(Avrae, self).__init__(prefix, help_command=help_command, description=description, **options)
        self.testing = testing
        self.state = "init"
        self.mclient = motor.motor_asyncio.AsyncIOMotorClient(config.MONGO_URL)
        self.mdb = self.mclient[config.MONGODB_DB_NAME]
        self.rdb = self.loop.run_until_complete(self.setup_rdb())
        self.prefixes = dict()
        self.muted = set()
        self.cluster_id = 0

        # sentry
        if config.SENTRY_DSN is not None:
            release = None
            if config.GIT_COMMIT_SHA:
                release = f"avrae-bot@{config.GIT_COMMIT_SHA}"
            sentry_sdk.init(dsn=config.SENTRY_DSN, environment=config.ENVIRONMENT.title(), release=release)

        # ddb entitlements
        if config.TESTING and config.DDB_AUTH_SERVICE_URL is None:
            self.ddb = BeyondClientBase()
        else:
            self.ddb = BeyondClient(self.loop)

        # launchdarkly
        self.ldclient = AsyncLaunchDarklyClient(self.loop, sdk_key=config.LAUNCHDARKLY_SDK_KEY)

    async def setup_rdb(self):
        return RedisIO(await aioredis.create_redis_pool(config.REDIS_URL, db=config.REDIS_DB_NUM))

    async def get_server_prefix(self, msg):
        return (await get_prefix(self, msg))[-1]

    async def launch_shards(self):
        # set up my shard_ids
        async with clustering.coordination_lock(self.rdb):
            await clustering.coordinate_shards(self)
            if self.shard_ids is not None:
                log.info(f"Launching {len(self.shard_ids)} shards! ({set(self.shard_ids)})")
            await super(Avrae, self).launch_shards()
            log.info(f"Launched {len(self.shards)} shards!")

        if self.is_cluster_0:
            await self.rdb.incr('build_num')

    async def close(self):
        await super().close()
        await self.ddb.close()
        self.ldclient.close()

    @property
    def is_cluster_0(self):
        if self.cluster_id is None:  # we're not running in clustered mode anyway
            return True
        return self.cluster_id == 0

    @staticmethod
    def log_exception(exception=None, context: commands.Context = None):
        if config.SENTRY_DSN is None:
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


desc = '''
Avrae, a D&D 5e utility bot designed to help you and your friends play D&D online.
A full command list can be found [here](https://avrae.io/commands)!
Invite Avrae to your server [here](https://invite.avrae.io)!
Join the official development server [here](https://support.avrae.io)!
'''
bot = Avrae(prefix=get_prefix, description=desc, pm_help=True, testing=config.TESTING,
            activity=discord.Game(name=f'D&D 5e | {config.DEFAULT_PREFIX}help'),
            allowed_mentions=discord.AllowedMentions(everyone=False, users=False, roles=False))  # by default, none

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

    elif isinstance(error, commands.MaxConcurrencyReached):
        return await ctx.send(f"Only {error.number} instance{'s' if error.number > 1 else ''} of this command per "
                              f"{error.per.name} can be running at a time.")

    elif isinstance(error, CommandInvokeError):
        original = error.original
        if isinstance(original, EvaluationError):  # PM an alias author tiny traceback
            return await handle_alias_exception(ctx, original)

        elif isinstance(original, RequiresLicense):
            return await handle_required_license(ctx, original)

        elif isinstance(original, CollectableRequiresLicenses):
            return await handle_alias_required_licenses(ctx, original)

        elif isinstance(original, AvraeException):
            return await ctx.send(str(original))

        elif isinstance(original, d20.RollError):
            return await ctx.send(f"Error in roll: {original}")

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
            elif 499 < original.response.status < 600:
                return await ctx.send("Error: Internal server error on Discord's end. Please try again.")

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

    # we override the default command processing to handle aliases
    if message.author.bot:
        return

    ctx = await bot.get_context(message)
    if ctx.command is not None:  # builtins first
        await bot.invoke(ctx)
    elif ctx.invoked_with:  # then aliases if there is some word (and not just the prefix)
        await handle_aliases(ctx)


@bot.event
async def on_command(ctx):
    try:
        log.debug(
            "cmd: chan {0.message.channel} ({0.message.channel.id}), serv {0.message.guild} ({0.message.guild.id}), "
            "auth {0.message.author} ({0.message.author.id}): {0.message.content}".format(
                ctx))
    except AttributeError:
        log.debug("Command in PM with {0.message.author} ({0.message.author.id}): {0.message.content}".format(ctx))


for cog in COGS:
    bot.load_extension(cog)

if __name__ == '__main__':
    faulthandler.enable()  # assumes we log errors to stderr, traces segfaults
    bot.state = "run"
    bot.loop.create_task(compendium.reload_task(bot.mdb))
    bot.run(config.TOKEN)
