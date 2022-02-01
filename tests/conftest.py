"""
This file sets up the "globals" we need for our tests
namely, it creates the Avrae instance and overrides its http and gateway handlers
and defines a bunch of helper methods
"""
import asyncio
import copy
import json
import logging
import os
import random
import re
import urllib.parse
from contextlib import contextmanager
from fnmatch import fnmatchcase

import discord
import pytest
from discord import DiscordException, Embed
from discord.ext import commands
from discord.http import HTTPClient, Route

# setup bot
from dbot import bot

pass  # here to prevent pycharm from moving around my imports >:C

from cogs5e.models.character import Character  # noqa: E402
from cogs5e.models.errors import AvraeException  # noqa: E402
from cogs5e.initiative import Combat  # noqa: E402
from tests.setup import *  # noqa: E4
from utils.config import DEFAULT_PREFIX  # noqa: E402

SENTINEL = object()

log = logging.getLogger(__name__)
dir_path = os.path.dirname(os.path.realpath(__file__))


@pytest.fixture(scope="session")
def event_loop():
    return asyncio.get_event_loop()


class Request:
    def __init__(self, method, url, data=None):
        self.method = method
        self.url = url
        self.data = data

    def __repr__(self):
        return f"{self.method} {self.url}\n{self.data}"


# assertations
def compare_embeds(request_embed, embed, *, regex: bool = True):
    """Recursively checks to ensure that two embeds have the same structure."""
    assert type(request_embed) == type(embed)

    if isinstance(embed, dict):
        for k, v in embed.items():
            if k == 'inline':
                continue
            elif isinstance(v, (dict, list)):
                compare_embeds(request_embed[k], embed[k])
            elif isinstance(v, str) and regex:
                assert re.match(embed[k], request_embed[k])
            else:
                assert request_embed[k] == embed[k]
    elif isinstance(embed, list):  # list of fields, usually
        assert len(embed) <= len(request_embed)
        for e, r in zip(embed, request_embed):
            compare_embeds(r, e)
    else:
        assert request_embed == embed


def embed_assertations(embed):
    """Checks to ensure that the embed is valid."""
    assert len(embed) <= 6000
    assert len(embed.title) <= 256
    assert len(embed.description) <= 4096
    assert len(embed.fields) <= 25
    for field in embed.fields:
        assert 0 < len(field.name) <= 256
        assert 0 < len(field.value) <= 1024
    if embed.footer:
        assert len(embed.footer.text) <= 2048
    if embed.author:
        assert len(embed.author.name) <= 256


def message_content_check(request: Request, content: str = None, *, regex: bool = True, embed: Embed = None):
    match = None
    if content:
        if regex:
            match = re.match(content, request.data.get('content'))
            assert match
        else:
            assert request.data.get('content') == content
    if embed:
        embed_data = request.data.get('embeds')
        assert embed_data is not None and embed_data
        embed_assertations(discord.Embed.from_dict(embed_data[0]))
        compare_embeds(embed_data[0], embed.to_dict(), regex=regex)
    return match


class DiscordHTTPProxy(HTTPClient):
    """
    This class handles receiving responses from the bot and keeping it happy.
    It should be used to check that the bot sends what we want.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # set up a way for us to track our requests
        self._request_check_queue = asyncio.Queue()

    # override d.py's request logic to implement our own
    async def request(self, route, *, files=None, header_bypass_delay=None, **kwargs):
        req = Request(route.method, route.url, kwargs.get('data') or kwargs.get('json'))
        log.info(str(req))
        await self._request_check_queue.put(req)

        request_route = f"{req.method} {req.url.split(Route.BASE)[-1]}"
        try:
            endpoint = next(k for k in RESPONSES if fnmatchcase(request_route, k))
        except StopIteration:
            raise RuntimeError("Bot requested an endpoint we don't have a test for")

        return RESPONSES[endpoint](req.data)

    # helper functions
    def clear(self):
        self._request_check_queue = asyncio.Queue()

    async def drain(self):
        """Waits until all requests have been sent and clears the queue."""
        to_wait = set()
        to_cancel = set()
        for task in asyncio.all_tasks():
            # note: we compare to repr(task) instead of the task's name since this contains information
            # about the function that created the task
            # if a bunch of tests are suddenly failing, this is often the culprit because of task names changing
            if "disnake" in repr(task):  # tasks started by disnake in reply to an event
                to_wait.add(task)
            elif "Message.delete" in repr(task):  # Messagable.send(..., delete_after=x)
                to_cancel.add(task)

        for task in to_cancel:
            task.cancel()

        try:
            await asyncio.wait_for(asyncio.gather(*to_wait), timeout=10)
        except asyncio.TimeoutError:
            log.info(f"Tasks we were waiting on when we timed out: {to_wait!r}")
            raise
        self.clear()

    async def get_request(self):
        try:
            return await asyncio.wait_for(self._request_check_queue.get(), timeout=10)
        except asyncio.TimeoutError as e:
            raise TimeoutError("Timed out waiting for Avrae response") from e

    async def receive_message(self, content: str = None, *, regex: bool = True, dm=False, embed: Embed = None):
        """
        Assert that the bot sends a message, and that it is the message we expect.
        If a regex is passed, this method returns the match object against the content.
        :param content The text or regex to match the message content against
        :param regex Whether to interpret content checking fields as a regex
        :param dm Whether it was a Direct Message that was received or not
        :param embed An embed to check against
        """
        request = await self.get_request()
        channel = TEST_DMCHANNEL_ID if dm else TEST_CHANNEL_ID

        assert request.method == "POST"
        assert request.url.endswith(f"/channels/{channel}/messages")

        return message_content_check(request, content, regex=regex, embed=embed)

    async def receive_edit(self, content: str = None, *, regex: bool = True, dm=False, embed: Embed = None):
        """
        Assert that the bot edits a message, and that it is the message we expect.
        If a regex is passed, this method returns the match object against the content.
        :param content The text or regex to match the message content against
        :param regex Whether to interpret content checking fields as a regex
        :param dm Whether it was a Direct Message that was edited or not
        :param embed An embed to check against
        """
        request = await self.get_request()
        channel = TEST_DMCHANNEL_ID if dm else TEST_CHANNEL_ID

        assert request.method == "PATCH"
        assert request.url.endswith(f"/channels/{channel}/messages/{MESSAGE_ID}")

        return message_content_check(request, content, regex=regex, embed=embed)

    async def receive_delete(self, dm=False):
        """
        Assert that the bot deletes a message.
        """
        request = await self.get_request()
        channel = TEST_DMCHANNEL_ID if dm else TEST_CHANNEL_ID

        assert request.method == "DELETE"
        assert request.url.endswith(f"/channels/{channel}/messages/{MESSAGE_ID}")

    async def receive_pin(self, dm=False):
        """
        Assert that the bot pins a message.
        """
        request = await self.get_request()
        channel = TEST_DMCHANNEL_ID if dm else TEST_CHANNEL_ID

        assert request.method == "PUT"
        assert request.url.endswith(f"/channels/{channel}/pins/{MESSAGE_ID}")

    async def receive_unpin(self, dm=False):
        """
        Assert that the bot unpins a message.
        """
        request = await self.get_request()
        channel = TEST_DMCHANNEL_ID if dm else TEST_CHANNEL_ID

        assert request.method == "DELETE"
        assert request.url.endswith(f"/channels/{channel}/pins/{MESSAGE_ID}")

    async def receive_typing(self, dm=False):
        """
        Assert that the bot sends typing.
        """
        request = await self.get_request()
        channel = TEST_DMCHANNEL_ID if dm else TEST_CHANNEL_ID

        assert request.method == "POST"
        assert request.url.endswith(f"/channels/{channel}/typing")

    async def receive_reaction(self, emoji, dm=False):
        """
        Assert that the bot sends a reaction.

        For unicode emoji, pass the unicode str; otherwise pass the emoji as ``name:id``
        """
        request = await self.get_request()
        channel = TEST_DMCHANNEL_ID if dm else TEST_CHANNEL_ID
        encoded_emoji = urllib.parse.quote(emoji)

        assert request.method == "PUT"
        assert request.url.endswith(f"/channels/{channel}/messages/{MESSAGE_ID}/reactions/{encoded_emoji}/@me")

    def queue_empty(self):
        return self._request_check_queue.empty()


# the http fixture
@pytest.fixture(scope="session")
def dhttp():
    """
    The HTTP proxy
    We use this to check what the bot has sent and make sure it's right
    """
    return DiscordHTTPProxy()


class MockAsyncLaunchDarklyClient:
    def __init__(self):
        self.flag_store = {}

    @contextmanager
    def flags(self, flags: dict):
        """Async context manager that sets the global value of a feature flag in the context."""
        old_flag_store = copy.deepcopy(self.flag_store)
        self.flag_store.update(flags)
        try:
            yield
        finally:
            self.flag_store = old_flag_store

    async def variation(self, key, user, default):
        return self.flag_store.get(key, default)

    def close(self):
        pass


# the ldclient fixture
@pytest.fixture(scope="session")
def mock_ldclient():
    """
    We use this to supply feature flags
    """
    return MockAsyncLaunchDarklyClient()


# methods to monkey-patch in to send messages to the bot without sending
def message(self, message_content, as_owner=False, dm=False):
    if message_content.startswith("!"):  # use the right prefix
        if not dm:
            message_content = f"{self.prefixes.get(str(TEST_GUILD_ID), '!')}{message_content[1:]}"
        else:
            message_content = f"{DEFAULT_PREFIX}{message_content[1:]}"

    log.info(f"Sending message {message_content}")
    # pretend we just received a message in our testing channel
    data = {
        'type': 0,
        'tts': False,
        'timestamp': '2021-09-08T20:33:57.337000+00:00',
        'referenced_message': None,
        'pinned': False,
        'nonce': 'blah',
        'mentions': [],
        'mention_roles': [],
        'mention_everyone': False,
        'id': MESSAGE_ID,
        'flags': 0,
        'embeds': [],
        'edited_timestamp': None,
        'content': message_content,
        'components': [],
        'channel_id': str(TEST_CHANNEL_ID) if not dm else str(TEST_DMCHANNEL_ID),
        'author': DEFAULT_USER if not as_owner else OWNER_USER,
        'attachments': []
    }
    if not dm:
        data['guild_id'] = TEST_GUILD_ID

    self._connection.parse_message_create(data)
    return MESSAGE_ID


def add_reaction(self, emoji, as_owner=False, dm=False):
    log.info(f"Adding reaction {emoji}")
    data = {
        'user_id': str(DEFAULT_USER_ID) if not as_owner else str(config.OWNER_ID),
        'channel_id': str(TEST_CHANNEL_ID) if not dm else str(TEST_DMCHANNEL_ID),
        'message_id': str(MESSAGE_ID),
        'emoji': {  # no custom emoji for now
            'id': None,
            'name': emoji
        }
    }
    if not dm:
        data['guild_id'] = TEST_GUILD_ID

    self._connection.parse_message_reaction_add(data)


# another error handler so unhandled errors bubble up correctly
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandInvokeError):
        error = error.original

    if isinstance(error, (AvraeException, DiscordException)):
        return
    pytest.fail(f"Command raised an error: {error}")
    raise error


@pytest.fixture(scope="session")
async def avrae(dhttp, mock_ldclient):
    # set up a way for us to send events to Avrae
    # monkey-patch in .message and .add_reaction
    bot.message = message.__get__(bot, type(bot))
    bot.add_reaction = add_reaction.__get__(bot, type(bot))

    # add error event listener
    bot.add_listener(on_command_error, "on_command_error")

    # set up http
    bot.http = dhttp
    # noinspection PyProtectedMember
    bot._connection.http = dhttp

    # feature flags monkey-patch
    bot.ldclient = mock_ldclient

    bot.state = "run"
    await bot.login(config.TOKEN)  # handled by our http proxy

    # we never do initialize the websocket - we just replay discord's login sequence
    # to initialize a "channel" to send testing messages to
    # in this case, we initialize a testing guild and dummy DMChannel

    # noinspection PyProtectedMember
    bot._connection.parse_ready(DUMMY_READY)
    # noinspection PyProtectedMember
    bot._connection.parse_guild_create(DUMMY_GUILD_CREATE)
    # noinspection PyProtectedMember
    bot._connection.add_dm_channel(DUMMY_DMCHANNEL_CREATE)
    # noinspection PyProtectedMember
    # used to allow the delay_ready task to progress
    bot._connection.shards_launched.set()

    log.info("Ready for testing")
    yield bot
    await bot.close()


# ===== Character Fixture =====
@pytest.fixture(
    scope="class",
    params=["ara", "drakro"]
)
def character(request, avrae):
    """Sets up an active character in the user's context, to be used in tests. Cleans up after itself."""
    filename = os.path.join(dir_path, "static", f"char-{request.param}.json")
    with open(filename) as f:
        char = Character.from_dict(json.load(f))
    char.owner = DEFAULT_USER_ID
    char._active = True
    avrae.mdb.characters.delegate.update_one(
        {"owner": char.owner, "upstream": char.upstream},
        {"$set": char.to_dict()},
        upsert=True
    )
    if request.cls is not None:
        request.cls.character = char
    yield char
    avrae.mdb.characters.delegate.delete_one(
        {"owner": char.owner, "upstream": char.upstream}
    )
    Character._cache.clear()


# ===== Init Fixture/Utils =====
@pytest.fixture(scope="class")
async def init_fixture(avrae):
    """Ensures we clean up before and after ourselves. Init tests should be grouped in a class."""
    await avrae.mdb.combats.delete_one({"channel": str(TEST_CHANNEL_ID)})
    yield
    await avrae.mdb.combats.delete_one({"channel": str(TEST_CHANNEL_ID)})
    Combat._cache.clear()


async def start_init(avrae, dhttp):
    dhttp.clear()
    avrae.message("!init begin")
    await dhttp.receive_delete()
    await dhttp.receive_message()
    await dhttp.receive_edit()
    await dhttp.receive_pin()
    await dhttp.receive_message()


async def end_init(avrae, dhttp):
    dhttp.clear()
    avrae.message("!init end")
    await dhttp.receive_delete()
    await dhttp.receive_message()
    avrae.message("y")
    await dhttp.receive_delete()
    await dhttp.receive_delete()
    await dhttp.receive_message()
    await dhttp.receive_message(dm=True)
    await dhttp.receive_edit()
    await dhttp.receive_unpin()
    await dhttp.receive_edit()


# ===== Global Fixture =====
@pytest.fixture(autouse=True, scope="function")
async def global_fixture(avrae, dhttp, request):
    """Things to do before and after every test."""
    log.info(f"Starting test: {request.function.__name__}")
    dhttp.clear()
    random.seed(123)  # we want to make our tests as deterministic as possible, so each one uses the same RNG seed
    yield
    await dhttp.drain()
    log.info(f"Finished test: {request.function.__name__}")
