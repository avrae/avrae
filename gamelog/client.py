import asyncio
import logging

from pymongo.errors import DuplicateKeyError

from gamelog.campaign import CampaignLink
from gamelog.errors import CampaignAlreadyLinked
from utils import config

GAME_LOG_PUBSUB_CHANNEL = f"game-log:{config.ENVIRONMENT}"
log = logging.getLogger(__name__)
log.setLevel(10)  # todo remove this - sets loglevel to debug in dev


class GameLogClient:
    def __init__(self, bot):
        """
        :param bot: Avrae instance
        """
        self.bot = bot
        self.rdb = bot.rdb
        self.loop = bot.loop
        self.http = None  # todo

    def init(self):
        self.loop.create_task(self.main_loop())

    # ==== campaign helpers ====
    async def create_campaign_link(self, ctx, campaign_id: str):
        # todo - is the current user authorized to link this campaign?
        campaign_name = f"Campaign {campaign_id}"  # todo get campaign name from metadata
        link = CampaignLink(campaign_id, campaign_name, ctx.channel.id, ctx.guild.id, ctx.author.id)
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
        # todo

        # check: is this campaign id for an event that is handled by this cluster?
        campaign = await CampaignLink.from_id(self.bot.mdb, msg['gameId'])
