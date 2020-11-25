import asyncio
import logging

from pymongo.errors import DuplicateKeyError

import ddb
from ddb.gamelog.context import GameLogEventContext
from ddb.gamelog.errors import CampaignAlreadyLinked, LinkNotAllowed, NoCampaignLink
from ddb.gamelog.events import GameLogEvent
from ddb.gamelog.link import CampaignLink

GAME_LOG_PUBSUB_CHANNEL = 'game-log'
AVRAE_EVENT_SOURCE = 'avrae'
log = logging.getLogger(__name__)
log.setLevel(10)  # todo remove this - sets loglevel to debug in dev


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

    def init(self):
        self.loop.create_task(self.main_loop())

    # ==== campaign helpers ====
    async def create_campaign_link(self, ctx, campaign_id: str):
        # is the current user authorized to link this campaign?
        ddb_user = await self.ddb.get_ddb_user(ctx, ctx.author.id)
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
            raise CampaignAlreadyLinked()
        return link

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
        if (channel := guild.get_channel(campaign.channel_id)) is None:
            log.info(f"Could not find channel {campaign.channel_id} in guild {guild.id} - discarding event")
            return

        # process the event
        await channel.send(f"Received message: {msg}")  # todo remove this debug line
        if event.event_type not in self._event_handlers:
            log.warning(f"No callback registered for event {event.event_type!r}")
            return

        gctx = GameLogEventContext(self.bot, event, guild, channel)  # todo character
        await self._event_handlers[event.event_type](gctx)

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

    def deregister_callback(self, event_type):
        """
        Deregisters a callback. If a callback for the given event type is not registered, does nothing.

        :param str event_type:
        """
        if event_type not in self._event_handlers:
            return
        del self._event_handlers[event_type]
