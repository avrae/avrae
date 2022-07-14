import disnake
import pytest

from gamedata.compendium import compendium
from tests.utils import ATTACK_PATTERN, D20_PATTERN, DAMAGE_PATTERN, TO_HIT_PATTERN, requires_data, server_settings
from utils.settings.guild import InlineRollingType

pytestmark = pytest.mark.asyncio


async def test_iterroll(avrae, dhttp):
    dhttp.clear()

    avrae.message("!rrr 10 1d20 21")
    await dhttp.receive_delete()
    await dhttp.receive_message(rf"<@!?\d+>\nRolling 10 iterations, DC 21...\n({D20_PATTERN}\n){{10}}0 successes.")

    avrae.message("!rrr 10 1d20 1")
    await dhttp.receive_delete()
    await dhttp.receive_message(rf"<@!?\d+>\nRolling 10 iterations, DC 1...\n({D20_PATTERN}\n){{10}}10 successes.")

    avrae.message("!rrr 10 1d20 10")
    await dhttp.receive_delete()
    await dhttp.receive_message(rf"<@!?\d+>\nRolling 10 iterations, DC 10...\n({D20_PATTERN}\n){{10}}\d+ successes.")


@requires_data()
async def test_ma(avrae, dhttp):
    dhttp.clear()

    avrae.message("!ma kobold")
    await dhttp.receive_delete()
    await dhttp.receive_message(embed=disnake.Embed(title="A Kobold's Actions"))

    avrae.message("!ma kobold dagger")
    await dhttp.receive_delete()
    atk_embed = disnake.Embed(title=r"(\w+ ?){2,3} attacks with a Dagger!")
    atk_embed.add_field(name="Meta", inline=False, value=ATTACK_PATTERN)
    atk_embed.add_field(name="Effect", inline=False, value=r"\*Melee Weapon Attack:.+")
    await dhttp.receive_message(embed=atk_embed)

    avrae.message("!ma kobold dagger -h")
    await dhttp.receive_delete()
    await dhttp.receive_message(
        rf"An unknown creature attacks with a Dagger!\n{TO_HIT_PATTERN}\n({DAMAGE_PATTERN}\n)?\*Melee Weapon Attack:.+",
        dm=True,
    )
    atk_embed = disnake.Embed(title="An unknown creature attacks with a Dagger!")
    atk_embed.add_field(name="Meta", inline=False, value=ATTACK_PATTERN)
    await dhttp.receive_message(embed=atk_embed)


@requires_data()
async def test_mc(avrae, dhttp):
    dhttp.clear()

    avrae.message("!mc kobold acro")
    await dhttp.receive_delete()
    await dhttp.receive_message(
        embed=disnake.Embed(title="A Kobold makes an Acrobatics check!", description=D20_PATTERN)
    )

    avrae.message("!mc kobold acro -h")
    await dhttp.receive_delete()
    await dhttp.receive_message(
        embed=disnake.Embed(title="An unknown creature makes an Acrobatics check!", description=D20_PATTERN)
    )


@requires_data()
async def test_ms(avrae, dhttp):
    dhttp.clear()

    avrae.message("!ms kobold dex")
    await dhttp.receive_delete()
    await dhttp.receive_message(embed=disnake.Embed(title="A Kobold makes a Dexterity Save!", description=D20_PATTERN))

    avrae.message("!ms kobold dex -h")
    await dhttp.receive_delete()
    await dhttp.receive_message(
        embed=disnake.Embed(title="An unknown creature makes a Dexterity Save!", description=D20_PATTERN)
    )


@requires_data()
async def test_mcast(avrae, dhttp):
    dhttp.clear()

    mage = next(m for m in compendium.monsters if m.name == "Mage")

    avrae.message("!mcast mage fireball")
    await dhttp.receive_delete()
    embed = disnake.Embed(title="A Mage casts Fireball!")
    embed.add_field(name="Meta", value=rf"{DAMAGE_PATTERN}\n\*\*DC\*\*: {mage.spellbook.dc}\nDEX Save")
    embed.add_field(name="Effect", value=".*")
    embed.add_field(name="Spell Slots", value="`3` ◉◉◉")
    await dhttp.receive_message(embed=embed)
    assert mage.spellbook.get_slots(3) == mage.spellbook.get_max_slots(3)  # do not modify singleton slots


async def test_multiroll(avrae, dhttp):
    dhttp.clear()

    avrae.message("!rr 10 1d20")
    await dhttp.receive_delete()
    await dhttp.receive_message(rf"<@!?\d+>\nRolling 10 iterations...\n({D20_PATTERN}\n){{10}}\d+ total.")


async def test_inline_rolling_disabled(avrae, dhttp, mock_ldclient):
    # set correct server settings and feature flags
    async with server_settings(avrae, inline_enabled=InlineRollingType.DISABLED):
        with mock_ldclient.flags({"cog.dice.inline_rolling.enabled": True}):
            avrae.message("[[1d20]]")
            assert dhttp.queue_empty()


async def test_inline_rolling_reaction(avrae, dhttp, mock_ldclient):
    async with server_settings(avrae, inline_enabled=InlineRollingType.REACTION):
        with mock_ldclient.flags({"cog.dice.inline_rolling.enabled": True}):
            avrae.message("[[1d20]]")
            await dhttp.receive_reaction("\N{game die}")
            # first time interaction
            await dhttp.receive_message(dm=True)

            avrae.add_reaction("\N{game die}")
            await dhttp.receive_message(rf"\({D20_PATTERN}\)")


async def test_inline_rolling_enabled(avrae, dhttp, mock_ldclient):
    async with server_settings(avrae, inline_enabled=InlineRollingType.ENABLED):
        with mock_ldclient.flags({"cog.dice.inline_rolling.enabled": True}):
            avrae.message("[[1d20]]")
            # first time interaction
            await dhttp.receive_message(dm=True)
            await dhttp.receive_message(rf"\({D20_PATTERN}\)")

            avrae.message("one two [[1d20]] three four five")
            await dhttp.receive_message(rf"one two \({D20_PATTERN}\) three four\.\.\.")


async def test_inline_rolling_character(avrae, dhttp, mock_ldclient, character):
    async with server_settings(avrae, inline_enabled=InlineRollingType.ENABLED):
        with mock_ldclient.flags({"cog.dice.inline_rolling.enabled": True}):
            avrae.message("[[1d20]]")
            await dhttp.drain()  # clear any 1st time interactions

            # checks/saves
            avrae.message("[[c:arcana]]")
            await dhttp.receive_message(rf"\(Arcana Check: {D20_PATTERN}\)")

            avrae.message("[[s:dex]]")
            await dhttp.receive_message(rf"\(Dexterity Save: {D20_PATTERN}\)")

            # invalid
            avrae.message("[[c:foobar]]")
            await dhttp.receive_message("(`foobar` is not a valid skill.)", regex=False)
            avrae.message("[[s:foobar]]")
            await dhttp.receive_message("(`foobar` is not a valid save.)", regex=False)


async def test_roll(avrae, dhttp):
    dhttp.clear()
