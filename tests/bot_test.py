import pytest


@pytest.mark.asyncio
async def test_basic_commands(avrae, dhttp):
    dhttp.clear()
    avrae.message("ping")
    await dhttp.receive_message("Pong.")
    await dhttp.receive_edit(regex=r"Pong.\nPing = \d+ ms.")

    avrae.message("echo foobar")
    await dhttp.receive_delete()
    await dhttp.receive_message(regex=r".*: foobar")
