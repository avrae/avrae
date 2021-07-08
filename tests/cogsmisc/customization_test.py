import discord  # noqa: F401 Is used in file
import pytest


pytestmark = pytest.mark.asyncio


async def test_snippet_before_edit(avrae, dhttp):
    dhttp.clear()

    # Snippet tests
    avrae.message("!snippet test adv")
    await dhttp.receive_message("Snippet `test` added.```py\n!snippet test adv\n```", regex=False)

    avrae.message("!snippet 2d6 adv")
    await dhttp.receive_message("**Warning:** Creating a snippet named `2d6` might cause hidden problems "
                                "if you try to use the same roll in other commands.\nAre you sure you want to "
                                "create this snippet? (Reply with yes/no)", regex=False)
    avrae.message("no")
    await dhttp.receive_message("Ok, cancelling.", regex=False)

    avrae.message("!snippet adv adv")
    await dhttp.receive_message("**Warning:** Creating a snippet named `adv` will prevent you from using "
                                "the built-in `adv` argument in Avrae commands.\nAre you sure you want to "
                                "create this snippet? (Reply with yes/no)", regex=False)
    avrae.message("yes")
    await dhttp.receive_message("Snippet `adv` added.```py\n!snippet adv adv\n```", regex=False)

    avrae.message("!snippet adv adv")
    await dhttp.receive_message("**Warning:** Creating a snippet named `adv` will prevent you from using "
                                "the built-in `adv` argument in Avrae commands.\nAre you sure you want to "
                                "create this snippet? (Reply with yes/no)", regex=False)
    avrae.message("no")
    await dhttp.receive_message("Ok, cancelling.", regex=False)

    avrae.message("!snippet str adv")
    await dhttp.receive_message("**Warning:** Creating a snippet named `str` will prevent you from using "
                                "the built-in `str` argument in Avrae commands.\nAre you sure you want to "
                                "create this snippet? (Reply with yes/no)", regex=False)
    avrae.message("no")
    await dhttp.receive_message("Ok, cancelling.", regex=False)

    avrae.message("!snippet 10 adv")
    await dhttp.receive_message("**Warning:** Creating a snippet named `10` might cause hidden problems if "
                                "you try to use the same roll in other commands.\nAre you sure you want to "
                                "create this snippet? (Reply with yes/no)", regex=False)
    avrae.message("no")
    await dhttp.receive_message("Ok, cancelling.", regex=False)

    avrae.message("!snippet remove test")
    await dhttp.receive_message("Snippet test removed.", regex=False)

    avrae.message("!snippet remove adv")
    await dhttp.receive_message("Snippet adv removed.", regex=False)

    avrae.message("!serversnippet adv adv")
    await dhttp.receive_message("**Warning:** Creating a snippet named `adv` will prevent you from using "
                                "the built-in `adv` argument in Avrae commands.\nAre you sure you want to "
                                "create this snippet? (Reply with yes/no)", regex=False)
    avrae.message("yes")
    await dhttp.receive_message("Server snippet `adv` added.```py\n!snippet adv adv\n```", regex=False)

    # alias tests
    avrae.message("!alias tester echo test")
    await dhttp.receive_message("Alias `tester` added.```py\n!alias tester echo test\n```", regex=False)

    avrae.message("!alias test echo test")
    await dhttp.receive_message("`test` is already a builtin command. Try another name.", regex=False)

    avrae.message("!servalias tester echo test")
    await dhttp.receive_message("Server alias `tester` added.```py\n!alias tester echo test\n```", regex=False)

    avrae.message("!servalias test echo test")
    await dhttp.receive_message("`test` is already a builtin command. Try another name.", regex=False)

    # testing the bugfix for renaming
    avrae.message("!snippet do adv")
    await dhttp.receive_message("Snippet `do` added.```py\n!snippet do adv\n```", regex=False)
    avrae.message("!snippet rename do adv")
    await dhttp.receive_message("**Warning:** Creating a snippet named `adv` will prevent you from using "
                                "the built-in `adv` argument in Avrae commands.\nAre you sure you want to "
                                "create this snippet? (Reply with yes/no)", regex=False)
    avrae.message("yes")
    await dhttp.receive_message("Okay, renamed the snippet do to adv.", regex=False)

    avrae.message("!alias tester echo not a test")
    await dhttp.receive_message("Alias `tester` added.```py\n!alias tester echo not a test\n```", regex=False)
    avrae.message("!alias rename tester test")
    await dhttp.receive_message("`test` is already a builtin command. Try another name.", regex=False)
