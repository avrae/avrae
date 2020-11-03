import asyncio
import logging

from utils import config

GAME_LOG_PUBSUB_CHANNEL = f"game-log:{config.ENVIRONMENT}"
log = logging.getLogger(__name__)


class GameLogClient:
    def __init__(self, rdb, loop):
        """
        :param rdb: RedisIO instance for pubsub
        :param loop: asyncio loop
        """
        self.rdb = rdb
        self.loop = loop

    def init(self):
        self.loop.create_task(self.main_loop())

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
        pass
