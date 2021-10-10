import asyncio
import datetime
import logging
import traceback

import aiohttp
from pymongo.errors import DuplicateKeyError

import ddb
from ddb.gamelog.constants import AVRAE_EVENT_SOURCE, GAME_LOG_PUBSUB_CHANNEL
from ddb.gamelog.context import GameLogEventContext
from ddb.gamelog.errors import CampaignAlreadyLinked, CampaignLinkException, IgnoreEvent, LinkNotAllowed, NoCampaignLink
from ddb.gamelog.event import GameLogEvent
from ddb.gamelog.link import CampaignLink
from ddb.utils import ddb_id_to_discord_id
from utils.config import DDB_GAMELOG_ENDPOINT

log = logging.getLogger(__name__)


class GameLogClient:
    def __init__(self, bot):
        """
        :param bot: Avrae instance
        """
        self.bot = bot
        self.ddb = bot.ddb  # type: ddb.BeyondClient
        self.rdb = bot.rdb
        self.loop = bot.loop
        self._event_handlers = {}

        self.http = None
        self.loop.run_until_complete(self._initialize())

    def init(self):
        self.loop.create_task(self.main_loop())

    async def _initialize(self):
        """Initialize our async resources: aiohttp"""
        self.http = aiohttp.ClientSession()  # this wants to run in a coroutine
        log.info("Game Log client initialized")

    # ==== campaign helpers ====
    async def create_campaign_link(self, ctx, campaign_id: str, overwrite=False):
        """
        Creates a campaign link for the given campaign ID to the current channel.

        :type ctx: discord.ext.commands.Context
        :param str campaign_id: The ID of the DDB campaign to connect
        :param bool overwrite: Whether to overwrite an existing link or error.
        :rtype: CampaignLink
        """
        # is the current user authorized to link this campaign?
        ddb_user = await self.ddb.get_ddb_user(ctx, ctx.author.id)
        if ddb_user is None:
            raise CampaignLinkException("You do not have a D&D Beyond account connected to your Discord account. "
                                        "Connect your accounts at <https://www.dndbeyond.com/account>!")
        active_campaigns = await self.ddb.get_active_campaigns(ctx, ddb_user)
        the_campaign = next((c for c in active_campaigns if c.id == campaign_id), None)

        if the_campaign is None:  # the user is not in the campaign
            raise LinkNotAllowed("You are not in this campaign, or this campaign does not exist.")
        elif the_campaign.dm_id != ddb_user.user_id:  # the user is not the DM
            raise LinkNotAllowed("Only the DM of a campaign is allowed to link a campaign to a Discord channel.")

        # create the link
        link = CampaignLink(campaign_id, the_campaign.name, ctx.channel.id, ctx.guild.id, ctx.author.id)
        try:
            await self.bot.mdb.gamelog_campaigns.insert_one(link.to_dict())
        except DuplicateKeyError:
            if overwrite:
                await self.bot.mdb.gamelog_campaigns.replace_one(
                    {"campaign_id": campaign_id},
                    link.to_dict()
                )
            else:
                raise CampaignAlreadyLinked()
        return link

    # ==== http ====
    async def post_message(self, ddb_user, message):
        """
        Posts a message to the game log. Silently logs errors to not interfere with operation of commands.

        :type ddb_user: ddb.auth.BeyondUser
        :type message: GameLogEvent
        """
        if DDB_GAMELOG_ENDPOINT is None or ddb_user is None:  # i.e. running on a limited-stack dev machine
            return

        try:
            data = message.to_dict()
            log.debug(f"Sending gamelog event {message.id!r}: {data}")
            async with self.http.post(f"{DDB_GAMELOG_ENDPOINT}/postMessage",
                                      headers={"Authorization": f"Bearer {ddb_user.token}"},
                                      json=data) as resp:
                log.debug(f"Game Log returned {resp.status} for request ID {message.id!r}")
                if not 199 < resp.status < 300:
                    log.warning(f"Game Log returned {resp.status}: {await resp.text()}")
        except aiohttp.ServerTimeoutError:
            log.warning("Timed out connecting to Game Log")
        except Exception as e:
            self.bot.log_exception(e)

    # ==== game log event loop ====
    async def main_loop(self):
        while True:  # if we ever disconnect from pubsub, wait 5s and try reinitializing
            try:  # connect to the pubsub channel
                channel = (await self.rdb.subscribe(GAME_LOG_PUBSUB_CHANNEL))[0]
            except:
                log.warning("Could not connect to pubsub! Waiting to reconnect...")
                await asyncio.sleep(5)
                continue

            log.info(f"Connected to pubsub channel: {GAME_LOG_PUBSUB_CHANNEL}.")
            async for msg in channel.iter(encoding="utf-8"):
                try:
                    await self._recv(msg)
                except Exception as e:
                    log.error(str(e))
            log.warning("Disconnected from Redis pubsub! Waiting to reconnect...")
            await asyncio.sleep(5)

    async def _recv(self, msg):
        log.debug(f"Received message: {msg}")
        # deserialize message into event
        event = GameLogEvent.from_gamelog_message(msg)

        # check: is this event from us (ignore it)?
        if event.source == AVRAE_EVENT_SOURCE:
            return

        # check: do we have a callback for this event?
        if event.event_type not in self._event_handlers:
            log.debug(f"No callback registered for event {event.event_type!r} - discarding event")
            return

        # check: is this campaign linked to a channel?
        try:
            campaign = await CampaignLink.from_id(self.bot.mdb, event.game_id)
        except NoCampaignLink:
            return

        # check: is this campaign id for an event that is handled by this cluster?
        if (guild := self.bot.get_guild(campaign.guild_id)) is None:
            log.debug(f"Guild {campaign.guild_id} is not in this cluster - ignoring")
            return

        # check: is the channel still there?
        if (channel := guild.get_channel_or_thread(campaign.channel_id)) is None:
            log.debug(f"Could not find channel {campaign.channel_id} in guild {guild.id} - discarding event")
            return

        # check: do I have permissions to send messages to the channel?
        if not channel.permissions_for(guild.me).send_messages:
            log.debug(f"No permissions to send messages in channel {campaign.channel_id} - discarding event")
            return

        # set up the event context
        discord_user_id = await ddb_id_to_discord_id(self.bot.mdb, event.user_id)
        if discord_user_id is None:
            log.debug(f"No discord user associated with event {event.event_type!r} - discarding event")
            return
        gctx = GameLogEventContext(self.bot, event, campaign, guild, channel, discord_user_id)

        # process the event
        try:
            await self._event_handlers[event.event_type](gctx)
        except IgnoreEvent as e:
            log.info(f"Event ID {event.id!r} was ignored: {e}")
            return
        except Exception as e:
            traceback.print_exc()
            self.bot.log_exception(e)
            return

        # do analytics
        await self._event_analytics(gctx)

    async def _event_analytics(self, gctx):
        """
        Called for each event that is successfully processed. Logs the event type, ddb user, ddb campaign,
        discord user id, discord guild id, discord channel id, event id, and timestamp.
        """
        await self.bot.mdb.analytics_gamelog_events.insert_one({
            "event_type": gctx.event.event_type,
            "ddb_user": gctx.event.user_id,
            "ddb_campaign": gctx.event.game_id,
            "discord_user": gctx.discord_user_id,
            "guild_id": gctx.guild.id,
            "channel_id": gctx.channel.id,
            "event_id": gctx.event.id,
            "timestamp": datetime.datetime.now()
        })

    # ==== game log callback registration ====
    def register_callback(self, event_type, handler):
        """
        Registers a coroutine as the callback for some event. If a callback is already registered for the given
        event type, raises a ValueError.

        :param str event_type: The event type to register.
        :param handler: The coroutine to call.
        :type handler: Callable[[ddb.gamelog.context.GameLogEventContext], Awaitable[Any]]
        """
        if event_type in self._event_handlers:
            raise ValueError(f"A callback is already registered for {event_type!r}")
        self._event_handlers[event_type] = handler
        log.debug(f"Registered callback for {event_type!r}")

    def deregister_callback(self, event_type):
        """
        Deregisters a callback. If a callback for the given event type is not registered, does nothing.

        :param str event_type:
        """
        if event_type not in self._event_handlers:
            return
        del self._event_handlers[event_type]
        log.debug(f"Deregistered callback for {event_type!r}")
