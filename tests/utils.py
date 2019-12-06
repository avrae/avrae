import os

import discord
import pytest

from cogs5e.funcs.lookupFuncs import compendium
from cogs5e.models.character import Character
from cogs5e.models.initiative import Combat
from tests.setup import DEFAULT_USER_ID, TEST_CHANNEL_ID

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
DICE_PATTERN = rf"( *((\d*d\d+(\w+[lh<>]?\d+)?( *{ROLLED_DICE_PATTERN})?)|\d+|( *[-+*/]))( *\[.*\])?)+( *= *`\d+`)?"

# to hit: a to-hit section of an attack
TO_HIT_PATTERN = rf"\*\*To Hit:?\*\*:? ((\d?d20\.\.\. = `(\d+|HIT|MISS)`)|({D20_PATTERN}{DICE_PATTERN} = `\d+`)|" \
                 rf"(Automatic (hit|miss)!))"

# damage: a damage section of an attack
DAMAGE_PATTERN = rf"((\*\*Damage( \(CRIT!\))?:?\*\*:? {DICE_PATTERN})|(\*\*Miss!\*\*))"

# attack: to hit and damage on two lines
ATTACK_PATTERN = rf"{TO_HIT_PATTERN}\n{DAMAGE_PATTERN}"

# save: d20, success or failure
SAVE_PATTERN = rf"\*\*\w+ Save:\*\* {D20_PATTERN}; (Failure|Success)!"

# save spell: saving throw and damage on two lines
SAVE_SPELL_PATTERN = rf"{SAVE_PATTERN}\n{DAMAGE_PATTERN}"


def requires_data():
    """
    A wrapper that skips a test if data is not loaded.
    Only a severely limited subset of data is available in tests.
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
        compendium.load_all_json(base_path=os.path.relpath("tests/static/compendium"))
        compendium.load_common()

    if not compendium.spells:  # we have no data, then
        return pytest.mark.skip(reason=f"Test requires data")

    return lambda func: func


async def active_character(avrae):
    """Gets the character active in this test."""
    fakectx = ContextBotProxy(avrae)
    fakectx.author = discord.Object(id=DEFAULT_USER_ID)
    return await Character.from_ctx(fakectx)


async def active_combat(avrae):
    """Gets the combat active in this test."""
    return await Combat.from_id(str(TEST_CHANNEL_ID), ContextBotProxy(avrae))


class ContextBotProxy:
    def __init__(self, bot):
        self.bot = bot
