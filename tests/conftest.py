"""
This file sets up the "globals" we need for our tests
namely, it creates the Avrae instance and overrides its http and gateway handlers
and defines a bunch of helper methods
"""

import asyncio
import json
import logging
import os
import pathlib
import random

import pytest

# setup bot
from dbot import bot

# here to prevent pycharm from moving around my imports >:C
pass

from cogs5e.models.character import Character  # noqa: E402
from cogs5e.initiative import Combat  # noqa: E402
from tests.discord_mock_data import *  # noqa: E4
from tests.mocks import MockAsyncLaunchDarklyClient, MockDiscordHTTP  # noqa: E402
from tests.monkey import add_reaction, message, on_command_error  # noqa: E402

SENTINEL = object()

log = logging.getLogger(__name__)
dir_path = os.path.dirname(os.path.realpath(__file__))


@pytest.fixture(scope="session")
def event_loop():
    return asyncio.get_event_loop()


# the http fixture
@pytest.fixture(scope="session")
def dhttp(event_loop):
    """
    The HTTP proxy
    We use this to check what the bot has sent and make sure it's right
    """
    return MockDiscordHTTP(loop=event_loop)


# the ldclient fixture
@pytest.fixture(scope="session")
def mock_ldclient():
    """
    We use this to supply feature flags
    """
    return MockAsyncLaunchDarklyClient()


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
@pytest.fixture(scope="class", params=["ara", "drakro"])
def character(request, avrae):
    """Sets up an active character in the user's context, to be used in tests. Cleans up after itself."""
    filename = os.path.join(dir_path, "static", f"char-{request.param}.json")
    with open(filename) as f:
        char = Character.from_dict(json.load(f))
    char.owner = DEFAULT_USER_ID
    char._active = True
    avrae.mdb.characters.delegate.update_one(
        {"owner": char.owner, "upstream": char.upstream}, {"$set": char.to_dict()}, upsert=True
    )
    if request.cls is not None:
        request.cls.character = char
    yield char
    avrae.mdb.characters.delegate.delete_one({"owner": char.owner, "upstream": char.upstream})
    # noinspection PyProtectedMember
    Character._cache.clear()


# ===== Init Fixture/Utils =====
@pytest.fixture(scope="class")
async def init_fixture(avrae):
    """Ensures we clean up before and after ourselves. Init tests should be grouped in a class."""
    await avrae.mdb.combats.delete_one({"channel": str(TEST_CHANNEL_ID)})
    yield
    await avrae.mdb.combats.delete_one({"channel": str(TEST_CHANNEL_ID)})
    # noinspection PyProtectedMember
    Combat._cache.clear()


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


# ==== marks ====
def pytest_collection_modifyitems(config, items):
    """
    mark every test in e2e/ with the *e2e* mark, unit/ with *unit*, and gamedata/ with *gamedata*
    """
    rootdir = pathlib.Path(config.rootdir)
    for item in items:
        rel_path = pathlib.Path(item.fspath).relative_to(rootdir)
        if "e2e" in rel_path.parts:
            item.add_marker(pytest.mark.e2e)
        elif "unit" in rel_path.parts:
            item.add_marker(pytest.mark.unit)
        elif "gamedata" in rel_path.parts:
            item.add_marker(pytest.mark.gamedata)


@pytest.fixture(scope="function")
def record_command_errors(avrae):
    """
    A fixture to temporarily remove the custom command error handler, to allow commands to raise handled errors.
    Yields a reference to a list of recorded errors.
    """
    recorded_errors = []

    async def on_command_error_rec(_, e):
        recorded_errors.append(e)

    avrae.add_listener(on_command_error_rec, "on_command_error")
    avrae.remove_listener(on_command_error)
    yield recorded_errors
    avrae.remove_listener(on_command_error_rec, "on_command_error")
    avrae.add_listener(on_command_error)
