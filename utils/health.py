import logging

from aiohttp import web

from utils import config

log = logging.getLogger(__name__)


class HealthServer:
    """Loopback liveness endpoint probed by the ECS container healthCheck.

    Must run on the bot's own event loop: a blocked loop can't schedule the handler, so the probe fails and ECS
    replaces the task. Running it on a separate thread would keep answering while the loop is wedged, defeating it.
    """

    def __init__(self, bot):
        self.bot = bot
        self._runner = None

    async def start(self):
        if config.HEALTHCHECK_PORT is None:  # disabled locally / in tests
            return
        app = web.Application()
        app.add_routes([web.get("/health", self._handle_health)])
        # access_log=None: the probe runs every few seconds; without this aiohttp logs a line per request and floods Datadog
        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        await web.TCPSite(self._runner, "127.0.0.1", config.HEALTHCHECK_PORT).start()
        log.info("Health check server listening on 127.0.0.1:%s", config.HEALTHCHECK_PORT)

    async def _handle_health(self, request):
        # Liveness only: do NOT await DB/Redis/Discord here - a slow dependency would cause a false unhealthy and an
        # unnecessary task kill. Reaching this handler at all is what proves the event loop is still scheduling work.
        return web.Response(text="ok")

    async def close(self):
        if self._runner is not None:
            await self._runner.cleanup()
