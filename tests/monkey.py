import logging

import pytest
from disnake import DiscordException
from disnake.ext import commands

from cogs5e.models.errors import AvraeException
from tests.discord_mock_data import (
    DEFAULT_OWNER_ID,
    DEFAULT_USER,
    DEFAULT_USER_ID,
    MESSAGE_ID,
    OWNER_USER,
    TEST_CHANNEL_ID,
    TEST_DMCHANNEL_ID,
    TEST_GUILD_ID,
)
from utils.config import DEFAULT_PREFIX

log = logging.getLogger(__name__)


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
        "type": 0,
        "tts": False,
        "timestamp": "2021-09-08T20:33:57.337000+00:00",
        "referenced_message": None,
        "pinned": False,
        "nonce": "blah",
        "mentions": [],
        "mention_roles": [],
        "mention_everyone": False,
        "id": MESSAGE_ID,
        "flags": 0,
        "embeds": [],
        "edited_timestamp": None,
        "content": message_content,
        "components": [],
        "channel_id": str(TEST_CHANNEL_ID) if not dm else str(TEST_DMCHANNEL_ID),
        "author": DEFAULT_USER if not as_owner else OWNER_USER,
        "attachments": [],
    }
    if not dm:
        data["guild_id"] = TEST_GUILD_ID

    self._connection.parse_message_create(data)
    return MESSAGE_ID


def add_reaction(self, emoji, as_owner=False, dm=False):
    log.info(f"Adding reaction {emoji}")
    data = {
        "user_id": str(DEFAULT_USER_ID) if not as_owner else str(DEFAULT_OWNER_ID),
        "channel_id": str(TEST_CHANNEL_ID) if not dm else str(TEST_DMCHANNEL_ID),
        "message_id": str(MESSAGE_ID),
        "emoji": {"id": None, "name": emoji},  # no custom emoji for now
    }
    if not dm:
        data["guild_id"] = TEST_GUILD_ID

    self._connection.parse_message_reaction_add(data)


# another error handler so unhandled errors bubble up correctly
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandInvokeError):
        error = error.original

    if isinstance(error, (AvraeException, DiscordException)):
        return
    pytest.fail(f"Command raised an error: {error}")
    raise error
