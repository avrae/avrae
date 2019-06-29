"""
This file sets up the "globals" we need for our tests
namely, it creates the Avrae instance and overrides its http and gateway handlers
"""
import asyncio
import logging
import re

import pytest
from discord import Message
from discord.gateway import DiscordWebSocket
from discord.http import HTTPClient

import credentials

TEST_CHANNEL_ID = 594236068627218447
TEST_GUILD_ID = 269275778867396608
MESSAGE_ID = "123456789012345678"
DEFAULT_USER = {
    "id": str(credentials.owner_id),
    "username": "zhu.exe",
    "discriminator": "4211",
    "avatar": None
}

log = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def event_loop():
    return asyncio.get_event_loop()


class Request:
    def __init__(self, method, url, data=None):
        self.method = method
        self.url = url
        self.data = data

    def __str__(self):
        return f"{self.method} {self.url}\n{self.data}"


class DiscordHTTPProxy(HTTPClient):
    """
    This class handles receiving responses from the bot and keeping it happy.
    It should be used to check that the bot sends what we want.
    """

    def __init__(self, *args, **kwargs):
        super(DiscordHTTPProxy, self).__init__(*args, **kwargs)
        # set up a way for us to track our requests
        self._requests = []
        self._last_request = None

    async def request(self, route, *, files=None, header_bypass_delay=None, **kwargs):
        req = Request(route.method, route.url, kwargs.get('data') or kwargs.get('json'))
        log.info(str(req))
        self._requests.append(req)
        self._last_request = req
        return await super(DiscordHTTPProxy, self).request(route, files=files, header_bypass_delay=header_bypass_delay,
                                                           **kwargs)

    def clear(self):
        self._last_request = None
        self._requests = []

    async def receive_message(self, content=None, *, regex=None):  # todo handle embeds
        """
        Assert that the bot sends a message, and that it is the message we expect.
        """
        # make sure we get the message we want
        while not self._last_request:
            await asyncio.sleep(0.1)

        assert self._last_request.method == "POST"
        assert self._last_request.url.endswith(f"/channels/{TEST_CHANNEL_ID}/messages")
        if regex:
            assert re.match(regex, self._last_request.data['content'])
        else:
            assert self._last_request.data['content'] == content

        self._last_request = None

    async def receive_edit(self, content=None, message_id=None, *, regex=None):
        """
        Assert that the bot edits a message, and that it is the message we expect.
        """
        # make sure we get the message we want
        while not self._last_request:
            await asyncio.sleep(0.1)

        assert self._last_request.method == "PATCH"
        if message_id:
            assert self._last_request.url.endswith(f"/channels/{TEST_CHANNEL_ID}/messages/{message_id}")
        if regex:
            assert re.match(regex, self._last_request.data['content'])
        else:
            assert self._last_request.data['content'] == content

        self._last_request = None

    async def receive_delete(self):
        """
        Assert that the bot deletes a message.
        """
        # make sure we get the message we want
        while not self._last_request:
            await asyncio.sleep(0.1)
        assert self._last_request.method == "DELETE"
        self._last_request = None


class DiscordWSProxy(DiscordWebSocket):
    """I love subclassing classes that say "Library users should never create this manually" in the docs"""
    pass


@pytest.fixture(scope="session")
def dhttp():
    """
    The HTTP proxy
    We use this to check what the bot has sent and make sure it's right
    """
    return DiscordHTTPProxy()


# methods to monkey-patch in to send messages to the bot without sending
def message(self, message_content):
    message_content = f"{self.prefixes.get(str(TEST_GUILD_ID), '!')}{message_content}"
    log.info(f"Sending message {message_content}")
    # pretend we just received a message in our testing channel
    self._connection.parse_message_create({
        "attachments": [],
        "tts": False,
        "embeds": [],
        "timestamp": "2017-07-11T17:27:07.299000+00:00",
        "mention_everyone": False,
        "id": MESSAGE_ID,
        "pinned": False,
        "edited_timestamp": None,
        "author": DEFAULT_USER,
        "mention_roles": [],
        "content": message_content,
        "channel_id": str(TEST_CHANNEL_ID),
        "mentions": [],
        "type": 0
    })


def event(self, event_type, content):
    pass


@pytest.fixture(scope="session")
async def avrae(dhttp):
    from dbot import bot  # runs all bot setup

    # set up a way for us to send events to Avrae
    # monkey-patch in .message and .event
    bot.message = message.__get__(bot, type(bot))
    bot.event = event.__get__(bot, type(bot))

    # set up http
    bot.http = dhttp
    bot._connection.http = dhttp

    bot.state = "run"
    await bot.login(bot.credentials.token)
    coro = DiscordWebSocket.from_client(bot, shard_id=bot.shard_id)
    bot.ws = await asyncio.wait_for(coro, timeout=180.0, loop=bot.loop)
    while not (bot.get_channel(TEST_CHANNEL_ID)):
        await bot.ws.poll_event()
    log.info("Ready for testing")
    yield bot
    await bot.logout()
