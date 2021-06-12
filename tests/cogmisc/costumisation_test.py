import discord
import pytest


pytestmark = pytest.mark.asyncio


async def test_snippet_before_edit(avrae, dhttp):
    dhttp.clear()
    
    avrae.message('!snippet test adv')
    await dhttp.receive_message("Snippet `test` added.```py\n!snippet test adv\n```", regex = False)

    avrae.message('!snippet 2d6 adv')
    await dhttp.receive_message('You can not use any valid dice strings as the name of a snippet.', regex = False)

    avrae.message('!snippet adv adv')
    await dhttp.receive_message("Warning: making a snippet named `adv` will prevent you from using the built-in `adv` argument in Avrae commands.\nAre you sure you want to make this snippet?(Y/N)", regex = False)
    avrae.message('yes')
    await dhttp.receive_message("Snippet `adv` added.```py\n!snippet adv adv\n```", regex = False)

    avrae.message('!snippet adv adv')
    await dhttp.receive_message("Warning: making a snippet named `adv` will prevent you from using the built-in `adv` argument in Avrae commands.\nAre you sure you want to make this snippet?(Y/N)", regex = False)
    avrae.message('no')
    await dhttp.receive_message('Ok, cancelling.', regex = False)
    await dhttp.recieve_message('The snippet was not created.', regex = False)

    avrae.message('!snippet str adv')
    await dhttp.receive_message("Warning: making a snippet named `str` will prevent you from using the built-in `str` argument in Avrae commands.\nAre you sure you want to make this snippet?(Y/N)", regex = False)
    avrae.message('no')
    await dhttp.receive_message('Ok, cancelling.', regex = False)
    await dhttp.recieve_message('The snippet was not created.', regex = False)

    avrae.message('!snippet 10 adv')
    await dhttp.receive_message('You can not use any valid dice strings as the name of a snippet.', regex = False)


