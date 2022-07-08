import discord
import pytest

from tests.utils import requires_data

pytestmark = pytest.mark.asyncio


@requires_data()
async def test_charref(avrae, dhttp):
    dhttp.clear()

    avrae.message("!charref 1")
    await dhttp.receive_message(r"<@!?\d+> What race\?")
    avrae.message("human")
    await dhttp.receive_message(r"<@!?\d+> What class\?")
    avrae.message("fighter")
    await dhttp.receive_message(r"<@!?\d+> What subclass\?")
    avrae.message("champion")
    await dhttp.receive_message(r"<@!?\d+> What background\?")
    avrae.message("acolyte")

    await dhttp.receive_message("Generating character, please wait...", regex=False)
    await dhttp.receive_message(r"\*\*Stats for \w+:\*\* `\[(\d{1,2}, ){5}\d{1,2}\]`", dm=True)
    await dhttp.drain()


@requires_data()
async def test_randchar(avrae, dhttp):
    dhttp.clear()

    avrae.message("!randchar")
    await dhttp.receive_message(r"<@!?\d+>\nGenerated random stats:\n(.*= `\d+`\n){6}Total = `\d+`")

    avrae.message("!randchar 1")
    await dhttp.receive_message("Generating character, please wait...", regex=False)
    await dhttp.receive_message(r"\*\*Stats for \w+:\*\* `\[(\d{1,2}, ){5}\d{1,2}\]`", dm=True)
    await dhttp.drain()


async def test_rollstats(avrae, dhttp):
    dhttp.clear()

    avrae.message("!rollstats")
    await dhttp.receive_message(embed=discord.Embed(title="Generating Random Stats"))


@requires_data()
async def test_randname(avrae, dhttp):
    dhttp.clear()

    avrae.message("!randname")
    await dhttp.receive_message(r"Your random name: \w+")

    avrae.message("!name elf family")
    await dhttp.receive_message(embed=discord.Embed(title="Family Elf Name", description=r"\w+"))
