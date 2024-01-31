"""
This file contains a bunch of dummy data and constants to emulate the responses of the Discord API
for automated testing.
"""

import datetime

from utils import config

TEST_CHANNEL_ID = 314159265358979323  # pi
TEST_DMCHANNEL_ID = 271828182845904523  # e
TEST_GUILD_ID = 112358132235579214  # fib
MESSAGE_ID = "123456789012345678"
DEFAULT_USER_ID = "111111111111111112"
DEFAULT_OWNER_ID = "222222222222222223"
OWNER_USER = {"id": DEFAULT_OWNER_ID, "username": "zhu.exe", "discriminator": "4211", "avatar": None}
DEFAULT_USER = {"id": DEFAULT_USER_ID, "username": "I'm a user", "discriminator": "0001", "avatar": None}
ME_USER = {
    "verified": True,
    "username": "Avrae Test",
    "mfa_enabled": True,
    "id": "111111111111111111",
    "flags": 0,
    "email": None,
    "discriminator": "0000",
    "bot": True,
    "avatar": None,
}
NOW = datetime.datetime.now().isoformat()


# http responses
def message_response(data):
    embeds = []
    if data.get("embed"):
        embeds = [data["embed"]]
    return {
        "nonce": None,
        "attachments": [],
        "tts": False,
        "embeds": embeds,
        "timestamp": NOW,
        "mention_everyone": False,
        "id": MESSAGE_ID,
        "pinned": False,
        "edited_timestamp": None,
        "author": DEFAULT_USER,
        "mention_roles": [],
        "content": data.get("content"),
        "channel_id": str(TEST_CHANNEL_ID),
        "mentions": [],
        "type": 0,
    }


def edit_response(data):
    embeds = []
    if data.get("embed"):
        embeds = [data["embed"]]
    return {
        "nonce": None,
        "attachments": [],
        "tts": False,
        "embeds": embeds,
        "timestamp": NOW,
        "mention_everyone": False,
        "id": MESSAGE_ID,
        "pinned": False,
        "edited_timestamp": NOW,
        "author": DEFAULT_USER,
        "mention_roles": [],
        "content": data.get("content"),
        "channel_id": str(TEST_CHANNEL_ID),
        "mentions": [],
        "type": 0,
    }


def start_dm_response(data):
    user = next(u for u in (DEFAULT_USER, OWNER_USER) if u["id"] == str(data["recipient_id"]))
    return {"last_message_id": None, "type": 1, "id": str(TEST_DMCHANNEL_ID), "recipients": [user]}


RESPONSES = {
    "GET /users/@me": lambda _: ME_USER,
    "GET /oauth2/applications/@me": lambda _: DUMMY_APPLICATION_INFO,
    "GET /applications/*/commands": lambda _: [],
    "GET /gateway": lambda _: {"url": "wss://gateway.discord.gg"},
    "POST /channels/*/messages": message_response,
    "PATCH /channels/*/messages/*": edit_response,
    "DELETE /channels/*/messages/*": lambda _: None,
    "POST /users/@me/channels": start_dm_response,
    "PUT /channels/*/pins/*": lambda _: None,
    "DELETE /channels/*/pins/*": lambda _: None,
    "PUT /channels/*/messages/*/reactions/*/@me": lambda _: None,
    "GET /channels/*/messages/*": message_response,
    "POST /channels/*/typing": lambda _: None,
}

# initialization
DUMMY_READY = {
    "v": 9,
    "user_settings": {},
    "user": ME_USER,
    "shard": [0, 1],
    "session_id": "foobar",
    "relationships": [],
    "private_channels": [],
    "presences": [],
    "guilds": [{"unavailable": True, "id": str(TEST_GUILD_ID)}],
    "guild_join_requests": [],
    "geo_ordered_rtc_regions": ["santa-clara", "us-west", "seattle", "us-south", "us-central"],
    "application": {"id": "111111111111111111", "flags": 294912},
    "_trace": ["blah"],
    "__shard_id__": 0,
}

DUMMY_GUILD_CREATE = {
    "default_message_notifications": 0,
    "afk_channel_id": None,
    "voice_states": [],
    "public_updates_channel_id": None,
    "name": "Test Guild",
    "region": "us-west",
    "stickers": [],
    "banner": None,
    "description": None,
    "splash": None,
    "discovery_splash": None,
    "preferred_locale": "en-US",
    "application_id": "207919515336441856",
    "channels": [{
        "type": 0,
        "topic": None,
        "rate_limit_per_user": 0,
        "position": 0,
        "permission_overwrites": [],
        "parent_id": None,
        "name": "test-channel",
        "last_message_id": None,
        "id": str(TEST_CHANNEL_ID),
    }],
    "mfa_level": 0,
    "unavailable": False,
    "guild_scheduled_events": [],
    "icon": None,
    "large": False,
    "explicit_content_filter": 0,
    "lazy": True,
    "joined_at": NOW,
    "system_channel_id": str(TEST_CHANNEL_ID),
    "premium_tier": 0,
    "verification_level": 0,
    "owner_id": OWNER_USER["id"],
    "max_video_channel_users": 25,
    "vanity_url_code": None,
    "threads": [],
    "member_count": 3,
    "nsfw_level": 0,
    "features": [],
    "application_command_counts": {"3": 0, "2": 0, "1": 0},
    "members": [
        {"user": ME_USER, "roles": [], "mute": False, "joined_at": NOW, "hoisted_role": None, "deaf": False},
        {"user": DEFAULT_USER, "roles": [], "mute": False, "joined_at": NOW, "hoisted_role": None, "deaf": False},
        {"user": OWNER_USER, "roles": [], "mute": False, "joined_at": NOW, "hoisted_role": None, "deaf": False},
    ],
    "afk_timeout": 300,
    "application_command_count": 0,
    "id": str(TEST_GUILD_ID),
    "nsfw": False,
    "stage_instances": [],
    "rules_channel_id": None,
    "system_channel_flags": 0,
    "max_members": 250000,
    "roles": [{
        "position": 0,
        "permissions": "6442451968",
        "name": "@everyone",
        "mentionable": False,
        "managed": False,
        "id": str(TEST_GUILD_ID),
        "hoist": False,
        "color": 0,
    }],
    "premium_subscription_count": 0,
    "presences": [],
    "guild_hashes": {
        "version": 1,
        "roles": {"omitted": True},
        "metadata": {"omitted": True},
        "channels": {"omitted": True},
    },
    "emojis": [],
}

DUMMY_DMCHANNEL_CREATE = {
    "type": 1,
    "recipients": [DEFAULT_USER],
    "last_message_id": None,
    "id": str(TEST_DMCHANNEL_ID),
}
DUMMY_APPLICATION_INFO = {
    "id": "111111111111111111",
    "name": "Avrae Test",
    "icon": None,
    "description": "",
    "summary": "",
    "bot_public": False,
    "bot_require_code_grant": False,
    "verify_key": "foobar",
    "owner": {
        "id": "592425568222445573",
        "username": "team592425568222445573",
        "avatar": None,
        "discriminator": "0000",
        "public_flags": 1024,
        "flags": 1024,
    },
    "flags": 32768,
    "team": {
        "id": "592425568222445573",
        "icon": None,
        "name": "Avrae Team",
        "owner_user_id": DEFAULT_OWNER_ID,
        "members": [{
            "user": {
                "id": DEFAULT_OWNER_ID,
                "username": "zhu.exe",
                "avatar": None,
                "discriminator": "4211",
                "public_flags": 131072,
            },
            "team_id": "592425568222445573",
            "membership_state": 2,
            "permissions": ["*"],
        }],
    },
    "rpc_origins": None,
}
