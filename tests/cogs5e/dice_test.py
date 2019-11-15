import discord
import pytest

from tests.utils import ATTACK_PATTERN, D20_PATTERN, DAMAGE_PATTERN, TO_HIT_PATTERN, requires_data

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
    await dhttp.receive_message(r"A Kobold's attacks:\n.*")

    avrae.message("!ma kobold dagger")
    await dhttp.receive_delete()
    atk_embed = discord.Embed(title=r"(\w+ ?){2,3} attacks with a Dagger!")
    atk_embed.add_field(name="Meta", inline=False, value=ATTACK_PATTERN)
    atk_embed.add_field(name="Effect", inline=False, value=r"Melee Weapon Attack:.+")
    await dhttp.receive_message(embed=atk_embed)

    avrae.message("!ma kobold dagger -h")
    await dhttp.receive_delete()
    await dhttp.receive_message(f"An unknown creature attacks with a Dagger!\n"
                                f"{TO_HIT_PATTERN}\n({DAMAGE_PATTERN}\n)?Melee Weapon Attack:.+", dm=True)
    atk_embed = discord.Embed(title="An unknown creature attacks with a Dagger!")
    atk_embed.add_field(name="Meta", inline=False, value=ATTACK_PATTERN)
    await dhttp.receive_message(embed=atk_embed)


@requires_data()
async def test_mc(avrae, dhttp):
    dhttp.clear()

    avrae.message("!mc kobold acro")
    await dhttp.receive_message(embed=discord.Embed(title="A Kobold makes an Acrobatics check!",
                                                    description=D20_PATTERN))
    await dhttp.receive_delete()

    avrae.message("!mc kobold acro -h")
    await dhttp.receive_message(embed=discord.Embed(title="An unknown creature makes an Acrobatics check!",
                                                    description=D20_PATTERN))
    await dhttp.receive_delete()


@requires_data()
async def test_ms(avrae, dhttp):
    dhttp.clear()

    avrae.message("!ms kobold dex")
    await dhttp.receive_message(embed=discord.Embed(title="A Kobold makes a Dexterity Save!",
                                                    description=D20_PATTERN))
    await dhttp.receive_delete()

    avrae.message("!ms kobold dex -h")
    await dhttp.receive_message(embed=discord.Embed(title="An unknown creature makes a Dexterity Save!",
                                                    description=D20_PATTERN))
    await dhttp.receive_delete()


async def test_multiroll(avrae, dhttp):
    dhttp.clear()

    avrae.message("!rr 10 1d20")
    await dhttp.receive_delete()
    await dhttp.receive_message(rf"<@!?\d+>\nRolling 10 iterations...\n({D20_PATTERN}\n){{10}}\d+ total.")


async def test_roll(avrae, dhttp):
    dhttp.clear()
