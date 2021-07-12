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
OWNER_USER = {
    "id": str(config.OWNER_ID),
    "username": "zhu.exe",
    "discriminator": "4211",
    "avatar": None
}
DEFAULT_USER = {
    "id": DEFAULT_USER_ID,
    "username": "I'm a user",
    "discriminator": "0001",
    "avatar": None
}
ME_USER = {
    'username': 'Avrae Test', 'verified': True, 'locale': 'en-US', 'mfa_enabled': True, 'bot': True,
    'id': '111111111111111111', 'flags': 0, 'avatar': None, 'discriminator': '0000', 'email': None
}
NOW = datetime.datetime.now().isoformat()


# http responses
def message_response(data):
    embeds = []
    if data.get('embed'):
        embeds = [data['embed']]
    return {
        'nonce': None, 'attachments': [], 'tts': False, 'embeds': embeds,
        'timestamp': NOW, 'mention_everyone': False, 'id': MESSAGE_ID,
        'pinned': False, 'edited_timestamp': None,
        'author': DEFAULT_USER, 'mention_roles': [], 'content': data.get('content'),
        'channel_id': str(TEST_CHANNEL_ID), 'mentions': [], 'type': 0
    }


def edit_response(data):
    embeds = []
    if data.get('embed'):
        embeds = [data['embed']]
    return {
        'nonce': None, 'attachments': [], 'tts': False, 'embeds': embeds,
        'timestamp': NOW, 'mention_everyone': False, 'id': MESSAGE_ID,
        'pinned': False, 'edited_timestamp': NOW,
        'author': DEFAULT_USER, 'mention_roles': [],
        'content': data.get('content'), 'channel_id': str(TEST_CHANNEL_ID), 'mentions': [], 'type': 0
    }


def start_dm_response(data):
    user = next(u for u in (DEFAULT_USER, OWNER_USER) if u['id'] == str(data['recipient_id']))
    return {
        "last_message_id": None,
        "type": 1,
        "id": str(TEST_DMCHANNEL_ID),
        "recipients": [
            user
        ]
    }


RESPONSES = {
    "GET /users/@me": lambda _: ME_USER,
    "GET /gateway": lambda _: {'url': 'wss://gateway.discord.gg'},
    f"POST /channels/*/messages": message_response,
    f"PATCH /channels/*/messages/{MESSAGE_ID}": edit_response,
    f"DELETE /channels/*/messages/{MESSAGE_ID}": lambda _: None,
    "POST /users/@me/channels": start_dm_response,
    f"PUT /channels/*/pins/{MESSAGE_ID}": lambda _: None,
    f"DELETE /channels/*/pins/{MESSAGE_ID}": lambda _: None,
    f"PUT /channels/*/messages/{MESSAGE_ID}/reactions/*/@me": lambda _: None,
    f"GET /channels/*/messages/{MESSAGE_ID}": message_response,
    f"POST /channels/*/typing": lambda _: None,
}

# initialization
DUMMY_READY = {
    'v': 6,
    'user_settings': {},
    'user': ME_USER,
    'shard': [
        0,
        1
    ],
    'session_id': 'foobar',
    'relationships': [],
    'private_channels': [],
    'presences': [],
    'guilds': [
        {
            'unavailable': True,
            'id': str(TEST_GUILD_ID)
        }
    ],
    '__shard_id__': 0
}

DUMMY_GUILD_CREATE = {
    'members': [
        {
            'user': ME_USER,
            'roles': [],
            'mute': False,
            'joined_at': NOW,
            'hoisted_role': None,
            'deaf': False
        },
        {
            'user': DEFAULT_USER,
            'roles': [],
            'mute': False,
            'joined_at': NOW,
            'hoisted_role': None,
            'deaf': False
        },
        {
            'user': OWNER_USER,
            'roles': [],
            'mute': False,
            'joined_at': NOW,
            'hoisted_role': None,
            'deaf': False
        }
    ],
    'icon': None,
    'owner_id': OWNER_USER['id'],
    'emojis': [],
    'member_count': 3,
    'presences': [],
    'splash': None,
    'system_channel_flags': 0,
    'nsfw': False,
    'lazy': True,
    'system_channel_id': str(TEST_CHANNEL_ID),
    'application_id': None,
    'unavailable': False,
    'stickers': [],
    'channels': [
        {
            'type': 0,
            'topic': None,
            'rate_limit_per_user': 0,
            'position': 0,
            'permission_overwrites': [],
            'parent_id': None,
            'name': 'test-channel',
            'last_message_id': None,
            'id': str(TEST_CHANNEL_ID)
        }
    ],
    'name': 'Test Guild',
    'nsfw_level': 0,
    'rules_channel_id': None,
    'voice_states': [],
    'afk_timeout': 300,
    'preferred_locale': 'en-US',
    'max_members': 100000,
    'guild_hashes': {
        'version': 1,
        'roles': {'omitted': True}, 'metadata': {'omitted': True}, 'channels': {'omitted': True}
    },
    'public_updates_channel_id': None,
    'explicit_content_filter': 0,
    'banner': None,
    'vanity_url_code': None,
    'afk_channel_id': None,
    'description': None,
    'mfa_level': 0,
    'verification_level': 0,
    'premium_subscription_count': 0,
    'default_message_notifications': 0,
    'stage_instances': [],
    'large': False,
    'region': 'us-west',
    'max_video_channel_users': 25,
    'joined_at': NOW,
    'roles': [
        {
            'position': 0,
            'permissions_new': '6442451968',
            'permissions': 1024,
            'name': '@everyone',
            'mentionable': False,
            'managed': False,
            'id': str(TEST_GUILD_ID),
            'hoist': False,
            'color': 0
        }
    ],
    'premium_tier': 0,
    'discovery_splash': None,
    'threads': [],
    'features': [],
    'application_command_count': 0,
    'id': str(TEST_GUILD_ID)
}

DUMMY_DMCHANNEL_CREATE = {
    'type': 1,
    'recipients': [
        DEFAULT_USER
    ],
    'last_message_id': None,
    'id': str(TEST_DMCHANNEL_ID)
}
