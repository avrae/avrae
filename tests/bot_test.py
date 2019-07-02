import discord
import pytest

pytestmark = pytest.mark.asyncio


async def test_basic_commands(avrae, dhttp):
    dhttp.clear()
    avrae.message("!ping")
    await dhttp.receive_message("Pong.")
    await dhttp.receive_edit(r"Pong.\nPing = \d+ ms.", regex=True)

    avrae.message("!echo foobar")
    await dhttp.receive_delete()
    await dhttp.receive_message(r".*: foobar", regex=True)

    avrae.message("!embed -f foo|bar -title \"Hello world\"")
    await dhttp.receive_delete()
    await dhttp.receive_message(embed=discord.Embed(title=r"Hello \w+"), regex=True)
