import os
import re
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import disnake
import pytest
from disnake import Embed

from cogs5e.initiative import Combat
from cogs5e.models.character import Character
from gamedata.compendium import compendium
from tests.discord_mock_data import DEFAULT_USER_ID, MESSAGE_ID, TEST_CHANNEL_ID, TEST_GUILD_ID
from utils.settings import ServerSettings

if TYPE_CHECKING:
    from tests.mocks import Request

GAMEDATA_BASE_PATH = os.getenv("TEST_GAMEDATA_BASE_PATH")
if GAMEDATA_BASE_PATH is None:
    GAMEDATA_BASE_PATH = os.path.join(os.path.dirname(__file__), "static/compendium")

# rolled dice: the individual results of dice
# matches:
# (5)
# (~~13~~, 16, ~~**1**~~)
# (1 -> 4, 5, 4)
# (4, ~~2 -> 4~~, ~~1 -> 4~~)
# (5 -> **6**, 5 -> **6**, ~~1 -> **6**~~)
ROLLED_DICE_PATTERN = r"\((~*(\**\d+\**( -> )?)+~*(, )?)+\)"

# d20: 1d20 or advantage variants plus potential modifier and result after
# matches:
# 1d20 (5)
# 1d20 (12) + 3
# 1d20 (**1**) - 1 = `0`
# 1d20 (**20**)
# 2d20kh1 (15, ~~2~~) = `15`
# 3d20kh1 (~~13~~, 16, ~~**1**~~)
D20_PATTERN = rf"\d?d20(\w+[lh<>]?\d+)? *{ROLLED_DICE_PATTERN}( *[+-] *\d+)?( *= *`\d+`)?"

# dice: any combination of valid dice, rolled or unrolled
DICE_PATTERN = (
    rf"((\()? *((\d*d\d+(\w+[lh<>]?\d+)?( *{ROLLED_DICE_PATTERN})?)|\d+|( *[-+*/]))( *\[.*\])?)+"
    rf"(\))?( *[\/\*] *\d)?( *= *`\d+`)?"
)

# to hit: a to-hit section of an attack
TO_HIT_PATTERN = (
    rf"\*\*To Hit:?\*\*:? ((\d?d20\.\.\. = `(\d+|HIT|MISS)`)|({D20_PATTERN}{DICE_PATTERN} = `\d+`)|"
    rf"(Automatic (hit|miss)!))"
)

# damage: a damage section of an attack
DAMAGE_PATTERN = rf"((\*\*Damage( \(CRIT!\))?:?\*\*:? {DICE_PATTERN})|(\*\*Miss!\*\*))"

# attack: to hit and damage on two lines
ATTACK_PATTERN = rf"{TO_HIT_PATTERN}\n{DAMAGE_PATTERN}"

# catches Dagger and Faithful Daggo' (Dagger)
DAGGER_PATTER = r".*\(?Dagger\)?"

# save: d20, success or failure
SAVE_PATTERN = rf"\*\*\w+ Save:?\*\*:? {D20_PATTERN}; (Failure|Success)!"

# save spell: saving throw and damage on two lines
SAVE_SPELL_PATTERN = rf"{SAVE_PATTERN}\n{DAMAGE_PATTERN}"


def requires_data(fail_if_no_data=False):
    """
    A decorator that skips a test if data is not loaded.
    By default, only a severely limited subset of data is available in tests.
    Test environments can inject real gamedata by writing to tests/static/compendium.

    Default exposed gamedata:
    Conditions: FakeCondition
    Names: Elf, Family
    Rules: Fake Rule
    Backgrounds: Acolyte
    Monsters: Mage, Kobold
    Classes: Fighter (Champion)
    Classfeats: None
    Feats: Grappler
    Items: Longsword
    Itemprops: Versatile
    Races: Human
    Spells: Fire Bolt, Fireball
    """
    if not compendium.spells:  # if spells have not loaded, no data has
        compendium.load_all_json(base_path=GAMEDATA_BASE_PATH)
        compendium.load_common()

    if not compendium.spells:  # we have no data, then
        if not fail_if_no_data:
            return pytest.mark.skip(reason="Test requires gamedata")
        else:
            # this returns a decorator, so make our actual method just fail
            return lambda func: lambda *_, **__: pytest.fail("Test requires gamedata")

    return lambda func: func


async def active_character(avrae):
    """Gets the character active in this test."""
    fakectx = ContextBotProxy(avrae)
    return await Character.from_ctx(fakectx, use_global=True, use_channel=True, use_guild=True)


async def active_combat(avrae):
    """Gets the combat active in this test."""
    return await Combat.from_id(str(TEST_CHANNEL_ID), ContextBotProxy(avrae))


@asynccontextmanager
async def server_settings(avrae, **settings):
    """Async context manager that sets certain server settings in the context."""
    old_servsettings = await ServerSettings.for_guild(avrae.mdb, TEST_GUILD_ID)
    try:
        new_servsettings = ServerSettings(guild_id=int(TEST_GUILD_ID), **settings)
        await new_servsettings.commit(avrae.mdb)
        yield
    finally:
        await old_servsettings.commit(avrae.mdb)


class ContextBotProxy:
    def __init__(self, bot):
        self.bot = bot
        # to make draconic tests work
        self.prefix = "!"
        self.invoked_with = "foo"
        self.message = MessageProxy()

    @property
    def channel(self):
        return self.bot.get_channel(int(TEST_CHANNEL_ID))

    @property
    def guild(self):
        return self.bot.get_guild(int(TEST_GUILD_ID))

    @property
    def author(self):
        return self.guild.get_member(int(DEFAULT_USER_ID))


class MessageProxy:
    def __init__(self):
        self.id = int(MESSAGE_ID)


# ==== assertion helpers ====
def compare_embeds(request_embed, embed, *, regex: bool = True):
    """Recursively checks to ensure that two embeds have the same structure."""
    assert type(request_embed) == type(embed)

    if isinstance(embed, dict):
        for k, v in embed.items():
            if k == "inline":
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


def embed_assertions(embed):
    """Checks to ensure that the embed is valid."""
    assert len(embed) <= 6000
    assert embed.title is None or len(embed.title) <= 256
    assert embed.description is None or len(embed.description) <= 4096
    assert embed.fields is None or len(embed.fields) <= 25
    for field in embed.fields:
        assert 0 < len(field.name) <= 256
        assert 0 < len(field.value) <= 1024
    if embed.footer:
        assert len(embed.footer.text) <= 2048
    if embed.author:
        assert len(embed.author.name) <= 256


def message_content_check(request: "Request", content: str = None, *, regex: bool = True, embed: Embed = None):
    match = None
    if content:
        if regex:
            match = re.match(content, request.data.get("content"))
            assert match
        else:
            assert request.data.get("content") == content
    if embed:
        embed_data = request.data.get("embeds")
        if embed_data is not None:
            assert embed_data
            embed_assertions(disnake.Embed.from_dict(embed_data[0]))
            compare_embeds(embed_data[0], embed.to_dict(), regex=regex)
    return match


# ==== combat helpers ====
async def start_init(avrae, dhttp):
    dhttp.clear()
    avrae.message("!init begin")
    await dhttp.receive_delete()
    await dhttp.receive_message()
    await dhttp.receive_pin()
    await dhttp.receive_edit()
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
