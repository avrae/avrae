import discord
import pytest

pytestmark = pytest.mark.asyncio


async def test_help(avrae, dhttp):
    avrae.message("!help")
    await dhttp.drain()

    avrae.message("!help -here")
    await dhttp.receive_message(embed=discord.Embed())


async def test_help_commands(avrae, dhttp):
    for command in avrae.walk_commands():
        avrae.message(f"!help {command.qualified_name}")
        await dhttp.drain()

        avrae.message(f"!help {command.qualified_name} -here")
        await dhttp.receive_message(embed=discord.Embed())


async def test_help_modules(avrae, dhttp):
    for cog in avrae.cogs.keys():
        avrae.message(f"!help {cog}")
        await dhttp.drain()

        avrae.message(f"!help {cog} -here")
        await dhttp.receive_message(embed=discord.Embed())
