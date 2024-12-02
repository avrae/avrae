import asyncio
import faulthandler
import logging
import random
import sys
import time
import traceback


from redis import asyncio as redis
import d20
import disnake
import motor.motor_asyncio
import psutil
import sentry_sdk
from aiohttp import ClientOSError, ClientResponseError
from disnake import ApplicationCommandInteraction
from disnake.errors import Forbidden, HTTPException, NotFound
from disnake.ext import commands
from disnake.ext.commands import CommandSyncFlags
from disnake.ext.commands.errors import CommandInvokeError

from aliasing.errors import CollectableRequiresLicenses, EvaluationError
from aliasing.helpers import handle_alias_exception, handle_alias_required_licenses, handle_aliases
from cogs5e.models.errors import AvraeException, RequiresLicense
from ddb import BeyondClient, BeyondClientBase
from ddb.gamelog import GameLogClient
from gamedata.compendium import compendium
from gamedata.lookuputils import handle_required_license
from utils import clustering, config, context
from utils.feature_flags import AsyncLaunchDarklyClient
from utils.help import help_command
from utils.redisIO import RedisIO

# This method will load the variables from .env into the environment for running in local
# from dotenv import load_dotenv
# load_dotenv()


# -----COGS-----
COGS = (
    "cogs5e.dice",
    "cogs5e.charGen",
    "cogs5e.homebrew",
    "cogs5e.lookup",
    "cogs5e.pbpUtils",
    "cogs5e.gametrack",
    "cogs5e.initiative",
    "cogs5e.sheetManager",
    "cogs5e.gamelog",
    "cogsmisc.customization",
    "cogsmisc.core",
    "cogsmisc.publicity",
    "cogsmisc.stats",
    "cogsmisc.adminUtils",
    "cogsmisc.tutorials",
)


async def get_prefix(the_bot, message):
    if not message.guild:
        return commands.when_mentioned_or(config.DEFAULT_PREFIX)(the_bot, message)
    gp = await the_bot.get_guild_prefix(message.guild)
    return commands.when_mentioned_or(gp)(the_bot, message)


class Avrae(commands.AutoShardedBot):
    def __init__(self, prefix, description=None, **options):
        sync_flags = CommandSyncFlags(
            sync_commands=False,  # this is set by launch_shard below, to prevent multiple clusters racing).
            sync_commands_debug=config.TESTING,
        )
        super().__init__(
            prefix,
            help_command=help_command,
            description=description,
            command_sync_flags=sync_flags,
            activity=options.get("activity"),
            allowed_mentions=options.get("allowed_mentions"),
            intents=options.get("intents"),
            chunk_guilds_at_startup=options.get("chunk_guilds_at_startup"),
        )
        self.pm_help = options.get("pm_help")
        self.testing = options.get("testing")
        self.state = "init"

        # dbs
        self.mclient = motor.motor_asyncio.AsyncIOMotorClient(config.MONGO_URL, retryWrites=False)

        self.mdb = self.mclient[config.MONGODB_DB_NAME]
        self.rdb = self.loop.run_until_complete(self.setup_rdb())

        # misc caches
        self.prefixes = dict()
        self.muted = set()
        self.cluster_id = 0

        # launch concurrency
        self.launch_max_concurrency = 1

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

        # ddb game log
        self.glclient = GameLogClient(self)
        self.glclient.init()

    async def setup_rdb(self):
        return RedisIO(await redis.from_url(url=config.REDIS_URL, health_check_interval=60))

    async def get_guild_prefix(self, guild: disnake.Guild) -> str:
        guild_id = str(guild.id)
        if guild_id in self.prefixes:
            return self.prefixes.get(guild_id, config.DEFAULT_PREFIX)
        # load from db and cache
        gp_obj = await self.mdb.prefixes.find_one({"guild_id": guild_id})
        if gp_obj is None:
            gp = config.DEFAULT_PREFIX
        else:
            gp = gp_obj.get("prefix", config.DEFAULT_PREFIX)
        self.prefixes[guild_id] = gp
        return gp

    @property
    def is_cluster_0(self):
        if self.cluster_id is None:  # we're not running in clustered mode anyway
            return True
        return self.cluster_id == 0

    @staticmethod
    def log_exception(exception=None, ctx: context.AvraeContext = None):
        if config.SENTRY_DSN is None:
            return

        with sentry_sdk.push_scope() as scope:
            if ctx:
                # noinspection PyDunderSlots,PyUnresolvedReferences
                # for some reason pycharm doesn't pick up the attribute setter here
                scope.user = {"id": ctx.author.id, "username": str(ctx.author)}
                scope.set_tag("message.content", ctx.message.content)
                scope.set_tag("is_private_message", ctx.guild is None)
                scope.set_tag("channel.id", ctx.channel.id)
                scope.set_tag("channel.name", str(ctx.channel))
                if ctx.guild is not None:
                    scope.set_tag("guild.id", ctx.guild.id)
                    scope.set_tag("guild.name", str(ctx.guild))
            sentry_sdk.capture_exception(exception)

    async def launch_shards(self, ignore_session_start_limit: bool = False):
        # set up my shard_ids
        async with clustering.coordination_lock(self.rdb):
            await clustering.coordinate_shards(self)
            log.info(f"I am cluster {self.cluster_id}.")
            if self.shard_ids is not None:
                log.info(f"Launching {len(self.shard_ids)} shards! ({self.shard_ids})")

        # if we are cluster 0, we are responsible for handling application command sync
        if self.is_cluster_0:
            self._command_sync_flags.sync_commands = True

        # release lock and launch
        await super().launch_shards()
        log.info(f"Launched {len(self.shards)} shards!")

        if self.is_cluster_0:
            await self.rdb.incr("build_num")

    async def before_identify_hook(self, shard_id, *, initial=False):
        bucket_id = shard_id % self.launch_max_concurrency
        # dummy call to initialize monitoring - see note on returning 0.0 at
        # https://psutil.readthedocs.io/en/latest/index.html#psutil.cpu_percent
        psutil.cpu_percent()

        async def pre_lock_check(first=False):
            """
            Before attempting a lock, CPU utilization should be <75% to prevent a huge spike in CPU when connecting
            up to 16 shards at once. This also allows multiple clusters to startup concurrently.
            """
            if not first:
                await asyncio.sleep(0.2)
            wait_start = time.monotonic()
            while psutil.cpu_percent() > 75:
                t = random.uniform(5, 15)
                log.info(f"[C{self.cluster_id}] CPU usage is high, waiting {t:.2f}s!")
                await asyncio.sleep(t)
                if time.monotonic() - wait_start > 300:  # liveness: wait no more than 5 minutes
                    break

        # wait until the bucket is available and try to acquire the lock
        await clustering.wait_bucket_available(shard_id, bucket_id, self.rdb, pre_lock_hook=pre_lock_check)

    async def get_context(self, *args, **kwargs) -> context.AvraeContext:
        return await super().get_context(*args, cls=context.AvraeContext, **kwargs)

    async def close(self):
        # note: when closing the bot 2 errors are emitted:
        #
        # ERROR:asyncio: An open stream object is being garbage collected; call "stream.close()" explicitly.
        # ERROR:asyncio: An open stream object is being garbage collected; call "stream.close()" explicitly.
        #
        # These are caused by aioredis streams being GC'ed when discord.py cancels the tasks that create them
        # (because of course d.py decides it wants to cancel *all* tasks on its loop...)
        await super().close()
        await self.ddb.close()
        await self.rdb.close()
        await self.glclient.close()
        self.mclient.close()
        self.ldclient.close()


desc = (
    "Play D&D over Discord! Featuring advanced dice, initiative tracking, D&D Beyond integration, and more, you'll"
    " never need another D&D bot.\nView the full list of commands [here](https://avrae.io/commands)!\nInvite Avrae to"
    " your server [here](https://invite.avrae.io)!\nJoin the official development server"
    " [here](https://support.avrae.io)!\n[Privacy"
    " Policy](https://company.wizards.com/en/legal/wizards-coasts-privacy-policy) | [Terms of"
    " Use](https://company.wizards.com/en/legal/terms)"
)
intents = disnake.Intents(
    guilds=True,
    members=True,
    messages=True,
    message_content=True,
    reactions=True,
    bans=False,
    emojis=False,
    integrations=False,
    webhooks=False,
    invites=False,
    voice_states=False,
    presences=False,
    typing=False,
)  # https://discord.com/developers/docs/topics/gateway#gateway-intents
bot = Avrae(
    prefix=get_prefix,
    description=desc,
    pm_help=True,
    testing=config.TESTING,
    activity=disnake.Game(name=f"D&D 5e | {config.DEFAULT_PREFIX}help"),
    allowed_mentions=disnake.AllowedMentions.none(),
    intents=intents,
    chunk_guilds_at_startup=False,
)

log_formatter = logging.Formatter("%(levelname)s:%(name)s: %(message)s")
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(log_formatter)
logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(handler)
log = logging.getLogger("bot")


@bot.event
async def on_ready():
    log.info("Logged in as")
    log.info(bot.user.name)
    log.info(bot.user.id)
    log.info("------")


@bot.listen("on_command_error")
@bot.listen("on_slash_command_error")
async def command_errors(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return

    elif isinstance(error, AvraeException):
        return await ctx.send(str(error))

    elif isinstance(error, (commands.UserInputError, commands.NoPrivateMessage, ValueError)):
        return await ctx.send(
            f"Error: {str(error)}\nUse `{ctx.prefix}help " + ctx.command.qualified_name + "` for help."
        )

    elif isinstance(error, commands.CheckFailure):
        msg = str(error) or "You are not allowed to run this command."
        return await ctx.send(f"Error: {msg}")

    elif isinstance(error, commands.CommandOnCooldown):
        return await ctx.send("This command is on cooldown for {:.1f} seconds.".format(error.retry_after))

    elif isinstance(error, commands.MaxConcurrencyReached):
        return await ctx.send(str(error))

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
                    "Error: I am missing permissions to run this command. "
                    f"Please make sure I have permission to send messages to <#{ctx.channel.id}>."
                )
            except HTTPException:
                try:
                    return await ctx.send(f"Error: I cannot send messages to this user.")
                except HTTPException:
                    return

        elif isinstance(original, NotFound):
            return await ctx.send("Error: I tried to edit or delete a message that no longer exists.")

        elif isinstance(original, (ClientResponseError, asyncio.TimeoutError, ClientOSError)):
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
        "Please join <https://support.avrae.io> and let us know about the error!"
    )

    if isinstance(ctx, ApplicationCommandInteraction):
        log.warning(f"Error caused by slash command: `/{ctx.data.name}` with options: {ctx.options}")
    else:
        log.warning(f"Error caused by message: `{ctx.message.content}`")
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
    if ctx.valid:  # builtins first
        await bot.invoke(ctx)
    elif ctx.invoked_with:  # then aliases if there is some word (and not just the prefix)
        await handle_aliases(ctx)


@bot.event
async def on_command(ctx):
    try:
        log.debug(
            "cmd: chan {0.message.channel} ({0.message.channel.id}), serv {0.message.guild} ({0.message.guild.id}), "
            "auth {0.message.author} ({0.message.author.id}): {0.message.content}".format(ctx)
        )
    except AttributeError:
        log.debug("Command in PM with {0.message.author} ({0.message.author.id}): {0.message.content}".format(ctx))


for cog in COGS:
    bot.load_extension(cog)

if __name__ == "__main__":
    faulthandler.enable()  # assumes we log errors to stderr, traces segfaults
    bot.state = "run"
    bot.loop.create_task(compendium.reload_task(bot.mdb))
    bot.run(config.TOKEN)
