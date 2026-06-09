import socket

import aiohttp
import pytest

from utils import config
from utils.health import HealthServer

pytestmark = pytest.mark.unit


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def test_health_endpoint_returns_ok(monkeypatch):
    port = _free_port()
    monkeypatch.setattr(config, "HEALTHCHECK_PORT", port)

    server = HealthServer(bot=None)
    await server.start()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://127.0.0.1:{port}/health") as resp:
                assert resp.status == 200
                assert await resp.text() == "ok"
    finally:
        await server.close()


async def test_health_server_disabled_when_port_unset(monkeypatch):
    # When HEALTHCHECK_PORT is unset the server must no-op (local dev / tests), binding nothing.
    monkeypatch.setattr(config, "HEALTHCHECK_PORT", None)

    server = HealthServer(bot=None)
    await server.start()
    assert server._runner is None
    await server.close()
