import discord
import pytest


pytestmark = pytest.mark.asyncio


async def test_snippet_before_edit(avrae, dhttp):
    dhttp.clear()
    
    avrae.message('!snippet test adv')
    await dhttp.receive_delete()
    await dhttp.receive_message(rf"Snippet `test` added.\n```py\n!snippet test adv\n```")

    avrae.message('!snippet 2d6 adv')
    await dhttp.receive_delete
    await dhttp.receive_message('You can not use any valid dice strings as the name of a snippet.')

    avrae.message('!snippet adv adv')
    await dhttp.receive_delete()
    await dhttp.receive_message("Warning: making a snippet named `adv` will prevent you from using the built-in `adv` argument in Avrae commands.\nAre you sure you want to make this snippet?(Y/N)")
    avrae.message('yes')
    await dhttp.receive_message(rf"Snippet `adv` added.\n```py\n!snippet adv adv\n```")

    avrae.message('!snippet adv adv')
    await dhttp.receive_delete()
    await dhttp.receive_message("Warning: making a snippet named `adv` will prevent you from using the built-in `adv` argument in Avrae commands.\nAre you sure you want to make this snippet?(Y/N)")
    avrae.message('no')
    await dhttp.receive_message('Ok, cancelling.')

    avrae.message('!snippet str adv')
    await dhttp.receive_delete()
    await dhttp.receive_message("Warning: making a snippet named `adv` will prevent you from using the built-in `adv` argument in Avrae commands.\nAre you sure you want to make this snippet?(Y/N)")
    avrae.message('no')
    await dhttp.receive_message('Ok, cancelling.')

    avrae.message('!snippet 10 adv')
    await dhttp.receive_delete
    await dhttp.receive_message('You can not use any valid dice strings as the name of a snippet.')


