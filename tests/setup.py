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
    'afk_timeout': 300,
    'description': None,
    'members': [
        {
            'user': ME_USER,
            'roles': [],
            'mute': False,
            'joined_at': NOW,
            'deaf': False
        },
        {
            'user': DEFAULT_USER,
            'roles': [],
            'mute': False,
            'joined_at': NOW,
            'deaf': False
        },
        {
            'user': OWNER_USER,
            'roles': [],
            'mute': False,
            'joined_at': NOW,
            'deaf': False
        }
    ],
    'roles': [
        {
            'position': 0,
            'permissions': 104324681,
            'name': '@everyone',
            'mentionable': False,
            'managed': False,
            'id': str(TEST_GUILD_ID),
            'hoist': False,
            'color': 0
        }
    ],
    'afk_channel_id': None,
    'system_channel_flags': 0,
    'emojis': [],
    'voice_states': [],
    'application_id': None,
    'system_channel_id': str(TEST_CHANNEL_ID),
    'name': 'Test Guild',
    'premium_tier': 0,
    'joined_at': NOW,
    'banner': None,
    'id': str(TEST_GUILD_ID),
    'features': [],
    'preferred_locale': 'en-US',
    'region': 'us-west',
    'member_count': 3,
    'premium_subscription_count': 0,
    'default_message_notifications': 0,
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
    'unavailable': False,
    'icon': None,
    'vanity_url_code': None,
    'owner_id': OWNER_USER['id'],
    'presences': [],
    'splash': None,
    'mfa_level': 0,
    'explicit_content_filter': 0,
    'lazy': True,
    'large': False,
    'verification_level': 0
}

DUMMY_DMCHANNEL_CREATE = {
    'type': 1,
    'recipients': [
        DEFAULT_USER
    ],
    'last_message_id': None,
    'id': str(TEST_DMCHANNEL_ID)
}
