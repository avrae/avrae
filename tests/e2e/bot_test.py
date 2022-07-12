import disnake
import disnake.ext.commands
import pytest

pytestmark = pytest.mark.asyncio


async def test_basic_commands(avrae, dhttp):
    dhttp.clear()
    avrae.message("!ping")
    await dhttp.receive_message("Pong.")
    await dhttp.receive_edit(r"Pong.\nHTTP Ping = \d+ ms.", regex=True)

    avrae.message("!echo foobar")
    await dhttp.receive_delete()
    await dhttp.receive_message(r".*: foobar", regex=True)

    avrae.message('!embed -f foo|bar -title "Hello world"', dm=True)
    await dhttp.receive_delete(dm=True)
    await dhttp.receive_message(embed=disnake.Embed(title=r"Hello \w+"), regex=True, dm=True)


async def test_nonexistant_commands(avrae, dhttp):
    dhttp.clear()
    avrae.message("!this_command_does_not_exist_and_is_not_an_alias")
    avrae.message("this_message_is_not_even_a_command")
    avrae.message("hello world")
    avrae.message("spam spam spam!roll 1d20")
    assert dhttp.queue_empty()  # avrae has not responded to anything


async def test_owner_permissions(avrae, dhttp, record_command_errors):
    avrae.message("!admin", as_owner=False)
    await dhttp.drain()
    assert isinstance(record_command_errors[0], disnake.ext.commands.NotOwner)

    record_command_errors.clear()
    avrae.message("!admin", as_owner=True)
    await dhttp.drain()
    assert len(record_command_errors) == 0
