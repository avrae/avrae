"""
This file sets up the "globals" we need for our tests
namely, it creates the Avrae instance and overrides its http and gateway handlers
and defines a bunch of helper methods
"""
import asyncio
import logging
import re
from queue import Queue

import pytest
from discord import DiscordException
from discord.ext import commands
from discord.http import HTTPClient, Route

from cogs5e.models.errors import AvraeException
from tests.utils import *

SENTINEL = object()

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
        self._request_check_queue = Queue()

    # override d.py's request logic to implement our own
    async def request(self, route, *, files=None, header_bypass_delay=None, **kwargs):
        req = Request(route.method, route.url, kwargs.get('data') or kwargs.get('json'))
        log.info(str(req))
        self._request_check_queue.put(req)

        endpoint = req.url.split(Route.BASE)[-1]
        if f"{req.method} {endpoint}" in RESPONSES:
            return RESPONSES[f"{req.method} {endpoint}"](req.data)
        raise RuntimeError("Bot requested an endpoint we don't have a test for")

    # helper functions
    def clear(self):
        self._request_check_queue = Queue()

    async def get_request(self):
        while self._request_check_queue.empty():
            await asyncio.sleep(0.1)
        return self._request_check_queue.get()

    async def receive_message(self, content=None, *, regex=None, dm=False):  # todo handle embeds
        """
        Assert that the bot sends a message, and that it is the message we expect.
        """
        request = await self.get_request()
        channel = TEST_DMCHANNEL_ID if dm else TEST_CHANNEL_ID

        assert request.method == "POST"
        assert request.url.endswith(f"/channels/{channel}/messages")

        if regex:
            assert re.match(regex, request.data['content'])
        elif content:
            assert request.data['content'] == content

    async def receive_edit(self, content=None, *, regex=None, dm=False):
        """
        Assert that the bot edits a message, and that it is the message we expect.
        """
        request = await self.get_request()
        channel = TEST_DMCHANNEL_ID if dm else TEST_CHANNEL_ID

        assert request.method == "PATCH"
        assert request.url.endswith(f"/channels/{channel}/messages/{MESSAGE_ID}")

        if regex:
            assert re.match(regex, request.data['content'])
        elif content:
            assert request.data['content'] == content

    async def receive_delete(self, dm=False):
        """
        Assert that the bot deletes a message.
        """
        request = await self.get_request()
        channel = TEST_DMCHANNEL_ID if dm else TEST_CHANNEL_ID

        assert request.method == "DELETE"
        assert request.url.endswith(f"/channels/{channel}/messages/{MESSAGE_ID}")


# the http fixture
@pytest.fixture(scope="session")
def dhttp():
    """
    The HTTP proxy
    We use this to check what the bot has sent and make sure it's right
    """
    return DiscordHTTPProxy()


# methods to monkey-patch in to send messages to the bot without sending
def message(self, message_content, as_owner=False):
    if message_content.startswith("!"):  # use the right prefix
        message_content = f"{self.prefixes.get(str(TEST_GUILD_ID), '!')}{message_content[1:]}"

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
        "author": DEFAULT_USER if not as_owner else OWNER_USER,
        "mention_roles": [],
        "content": message_content,
        "channel_id": str(TEST_CHANNEL_ID),
        "mentions": [],
        "type": 0
    })
    return MESSAGE_ID


def event(self, event_type, content):
    pass


# another error handler so unhandled errors bubble up correctly
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandInvokeError):
        error = error.original

    if isinstance(error, (AvraeException, DiscordException)):
        return
    raise error


@pytest.fixture(scope="session")
async def avrae(dhttp):
    from dbot import bot  # runs all bot setup

    # set up a way for us to send events to Avrae
    # monkey-patch in .message and .event
    bot.message = message.__get__(bot, type(bot))
    bot.event = event.__get__(bot, type(bot))

    # add error event listener
    bot.add_listener(on_command_error, "on_command_error")

    # set up http
    bot.http = dhttp
    # noinspection PyProtectedMember
    bot._connection.http = dhttp

    bot.state = "run"
    await bot.login(bot.credentials.token)  # handled by our http proxy

    # we never do initialize the websocket - we just replay discord's login sequence
    # to initialize a "channel" to send testing messages to
    # in this case, we initialize a testing guild

    # noinspection PyProtectedMember
    bot._connection.parse_ready(DUMMY_READY)
    # noinspection PyProtectedMember
    bot._connection.parse_guild_create(DUMMY_GUILD_CREATE)

    log.info("Ready for testing")
    yield bot
    await bot.logout()
