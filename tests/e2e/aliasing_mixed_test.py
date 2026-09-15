import pytest

from tests.discord_mock_data import DEFAULT_USER_ID
from tests.utils import active_character, end_init, start_init

pytestmark = pytest.mark.asyncio


async def _expect_script_error(dhttp, channel_pattern):
    # an error raised inside a scripting builtin is wrapped by the interpreter: the author is PM'd a
    # traceback, then the error is sent to the channel.
    await dhttp.receive_message(r"(?s).*user-created command.*", dm=True)
    await dhttp.receive_message(channel_pattern)


async def test_echo_alias(avrae, dhttp):
    avrae.message("!alias foobar echo foobar")
    await dhttp.receive_message("Alias `foobar` added.```py\n!alias foobar echo foobar\n```")
    avrae.message("!foobar")
    await dhttp.receive_delete()
    await dhttp.receive_message(".+: foobar")


async def test_alias_newlines(avrae, dhttp):
    # ensure newlines directly after the alias name won't break anything.
    avrae.message("!alias foobar\necho hello!")
    await dhttp.receive_message("Alias `foobar` added.```py\n!alias foobar \necho hello!\n```")
    avrae.message("!foobar")
    await dhttp.drain()  # no expected output due to the newline before the alias command.


async def test_variables(avrae, dhttp):
    avrae.message("!uvar foobar Hello world")
    await dhttp.receive_message()
    avrae.message("!gvar create I am a gvar")
    match = await dhttp.receive_message("Created global variable `([0-9a-f-]+)`.")
    address = match.group(1)

    avrae.message(
        "!alias foobar echo <foobar> {foobar} {{foobar}}\n" + f"{{{{get_gvar('{address}')}}}}"
    )  # {{get_gvar('1234...')}}
    await dhttp.receive_message()
    avrae.message("!foobar")
    await dhttp.receive_delete()
    await dhttp.receive_message(".+: Hello world 0 Hello world\nI am a gvar")


async def test_create_gvar_scripting(avrae, dhttp):
    # create_gvar returns a UUID and the new gvar persists (not script-writable by default)
    avrae.message("!test <drac2>return create_gvar('made in script')</drac2>")
    match = await dhttp.receive_message(r".+: ([0-9a-f-]{36})")
    address = match.group(1)
    gvar = await avrae.mdb.gvars.find_one({"key": address})
    assert gvar is not None
    assert gvar["value"] == "made in script"
    assert gvar["owner"] == DEFAULT_USER_ID
    assert gvar["script_writable"] is False


async def test_create_gvar_script_writable_and_read_after_write(avrae, dhttp):
    # create_gvar(script_writable=True), set_gvar on it, and read-after-write within the same run
    avrae.message(
        "!test <drac2>\n"
        "a = create_gvar('initial', True)\n"
        "set_gvar(a, 'updated')\n"
        "return a + '|' + get_gvar(a)\n"
        "</drac2>"
    )
    match = await dhttp.receive_message(r".+: ([0-9a-f-]{36})\|updated")
    address = match.group(1)
    gvar = await avrae.mdb.gvars.find_one({"key": address})
    assert gvar["value"] == "updated"
    assert gvar["script_writable"] is True


async def test_set_gvar_on_existing_and_batching(avrae, dhttp):
    # create via command (script_writable False by default), enable scripting, then loop-write it
    avrae.message("!gvar create starting value")
    match = await dhttp.receive_message(r"Created global variable `([0-9a-f-]+)`.")
    address = match.group(1)
    avrae.message(f"!gvar scripting {address}")
    await dhttp.receive_message(rf"Scripting writes for global variable `{address}` turned on.")

    # 100 writes to one address dedupe to a single committed write and count 1 toward the cap
    avrae.message(
        "!test <drac2>\n"
        f"for i in range(100):\n"
        f"    set_gvar('{address}', str(i))\n"
        f"return get_gvar('{address}')\n"
        "</drac2>"
    )
    await dhttp.receive_message(r".+: 99")
    gvar = await avrae.mdb.gvars.find_one({"key": address})
    assert gvar["value"] == "99"


async def test_set_gvar_not_script_writable(avrae, dhttp):
    avrae.message("!gvar create static data")
    match = await dhttp.receive_message(r"Created global variable `([0-9a-f-]+)`.")
    address = match.group(1)
    avrae.message(f"!test {{{{set_gvar('{address}', 'nope')}}}}")
    await _expect_script_error(dhttp, r"Error evaluating expression: This gvar is not writable by scripting\.")
    # unchanged
    gvar = await avrae.mdb.gvars.find_one({"key": address})
    assert gvar["value"] == "static data"


async def test_set_gvar_field_absent_treated_as_static(avrae, dhttp):
    # a pre-existing document without the script_writable field must be treated as not writable
    address = "00000000-0000-4000-8000-000000000abc"
    await avrae.mdb.gvars.insert_one(
        {"key": address, "owner": DEFAULT_USER_ID, "owner_name": "tester", "value": "legacy", "editors": []}
    )
    avrae.message(f"!test {{{{set_gvar('{address}', 'nope')}}}}")
    await _expect_script_error(dhttp, r"Error evaluating expression: This gvar is not writable by scripting\.")


async def test_set_gvar_not_found(avrae, dhttp):
    avrae.message("!test {{set_gvar('11111111-2222-4333-8444-555555555555', 'x')}}")
    await _expect_script_error(dhttp, r"Error evaluating expression: Global variable not found\.")


async def test_set_gvar_not_permitted(avrae, dhttp):
    # owned by the default user, script-writable, but written by a different (owner) user
    avrae.message("!gvar create shared")
    match = await dhttp.receive_message(r"Created global variable `([0-9a-f-]+)`.")
    address = match.group(1)
    avrae.message(f"!gvar scripting {address}")
    await dhttp.receive_message(rf"Scripting writes for global variable `{address}` turned on.")

    avrae.message(f"!test {{{{set_gvar('{address}', 'hijack')}}}}", as_owner=True)
    await dhttp.drain()
    # the non-owner's write was rejected, so the value is unchanged
    gvar = await avrae.mdb.gvars.find_one({"key": address})
    assert gvar["value"] == "shared"


async def test_create_gvar_exceeds_per_execution_cap(avrae, dhttp):
    avrae.message("!test <drac2>\nfor i in range(60):\n    create_gvar(str(i))\n</drac2>")
    await _expect_script_error(dhttp, r"Error evaluating expression: Too many gvar writes in a single execution")


async def test_gvar_scripting_toggle_requires_owner(avrae, dhttp):
    avrae.message("!gvar create toggle me")
    match = await dhttp.receive_message(r"Created global variable `([0-9a-f-]+)`.")
    address = match.group(1)

    avrae.message(f"!gvar scripting {address}")
    await dhttp.receive_message(rf"Scripting writes for global variable `{address}` turned on.")
    avrae.message(f"!gvar scripting {address}")
    await dhttp.receive_message(rf"Scripting writes for global variable `{address}` turned off.")

    # a non-owner cannot change it
    avrae.message(f"!gvar scripting {address}", as_owner=True)
    await dhttp.receive_message(r"You are not the owner of this variable\.")


async def test_set_gvar_allowed_for_editor(avrae, dhttp):
    # a gvar owned by someone else, script-writable, with the invoking user listed as an editor
    address = "00000000-0000-4000-8000-0000000ed170"
    await avrae.mdb.gvars.insert_one({
        "key": address,
        "owner": "999999999999999999",
        "owner_name": "someone-else",
        "value": "original",
        "editors": [DEFAULT_USER_ID],
        "script_writable": True,
    })
    avrae.message(f"!test {{{{set_gvar('{address}', 'edited by editor')}}}}")
    await dhttp.receive_message(r".+:")  # set_gvar returns None, so the alias echoes nothing after the colon
    gvar = await avrae.mdb.gvars.find_one({"key": address})
    assert gvar["value"] == "edited by editor"


async def test_create_gvar_size_limit(avrae, dhttp):
    avrae.message("!test <drac2>return create_gvar('x' * 100001)</drac2>")
    await _expect_script_error(dhttp, r"Error evaluating expression: Gvars must be shorter than 100,000 characters\.")


async def test_set_gvar_size_limit(avrae, dhttp):
    avrae.message("!test <drac2>\n" "a = create_gvar('small', True)\n" "set_gvar(a, 'y' * 100001)\n" "</drac2>")
    await _expect_script_error(dhttp, r"Error evaluating expression: Gvars must be shorter than 100,000 characters\.")


async def test_alias_percent_arguments(avrae, dhttp):
    avrae.message("!alias foobar echo the first argument is %1% yay")
    await dhttp.drain()

    # 1 arg, none given
    avrae.message("!foobar")
    await dhttp.receive_delete()
    await dhttp.receive_message(".+: the first argument is %1% yay")

    # 1 arg, 1 given
    avrae.message("!foobar foo")
    await dhttp.receive_delete()
    await dhttp.receive_message(".+: the first argument is foo yay")

    # 1 arg, 2 given
    avrae.message("!foobar foo bar")
    await dhttp.receive_delete()
    await dhttp.receive_message(".+: the first argument is foo yay bar")

    # 1 arg, 1 given with quotes
    avrae.message('!foobar "foo bar"')
    await dhttp.receive_delete()
    await dhttp.receive_message('.+: the first argument is "foo bar" yay')


async def test_alias_ampersand_arguments(avrae, dhttp):
    avrae.message("!alias foobar echo the first argument is &1& yay")
    await dhttp.drain()

    # 1 arg, none given
    avrae.message("!foobar")
    await dhttp.receive_delete()
    await dhttp.receive_message(".+: the first argument is &1& yay")

    # 1 arg, 1 given
    avrae.message("!foobar foo")
    await dhttp.receive_delete()
    await dhttp.receive_message(".+: the first argument is foo yay")

    # 1 arg, 2 given
    avrae.message("!foobar foo bar")
    await dhttp.receive_delete()
    await dhttp.receive_message(".+: the first argument is foo yay bar")

    # 1 arg, 1 given with quotes
    avrae.message('!foobar "foo bar"')
    await dhttp.receive_delete()
    await dhttp.receive_message(".+: the first argument is foo bar yay")


async def test_alias_ampersand_all_arguments(avrae, dhttp):
    avrae.message("!alias foobar echo the arguments are &ARGS&")
    await dhttp.drain()

    # no args
    avrae.message("!foobar")
    await dhttp.receive_delete()
    await dhttp.receive_message(r".+: the arguments are \[\]")

    # 1 arg
    avrae.message("!foobar foo")
    await dhttp.receive_delete()
    await dhttp.receive_message(r".+: the arguments are \['foo'\]")

    # 2 args
    avrae.message("!foobar foo bar")
    await dhttp.receive_delete()
    await dhttp.receive_message(r".+: the arguments are \['foo', 'bar'\]")

    # 1 quoted arg
    avrae.message('!foobar "foo bar"')
    await dhttp.receive_delete()
    await dhttp.receive_message(r".+: the arguments are \['foo bar'\]")


async def test_servalias(avrae, dhttp):
    avrae.message("!servalias serverfoobar echo this is serverfoobar", as_owner=True)
    await dhttp.drain()

    avrae.message("!serverfoobar")
    await dhttp.receive_delete()
    await dhttp.receive_message(r".+: this is serverfoobar")

    avrae.message("!serverfoobar", dm=True)
    assert dhttp.queue_empty()


async def test_alias_vs_servalias(avrae, dhttp):
    avrae.message("!alias foobar echo this is foobar")
    avrae.message("!servalias foobar echo this is server foobar", as_owner=True)
    await dhttp.drain()

    avrae.message("!foobar")
    await dhttp.receive_delete()
    await dhttp.receive_message(r".+: this is foobar")


async def test_alias_verify_signature(avrae, dhttp):
    avrae.message("!test {{x = signature()}}{{verify_signature(x)}}")
    # ensure it is json
    await dhttp.receive_message(r".+: {.+}")


@pytest.mark.usefixtures("character")
class TestCharacterAliases:
    async def test_echo_attributes(self, avrae, dhttp):
        character = await active_character(avrae)
        avrae.message(
            "!alias foobar echo {charismaMod} {proficiencyBonus} {charismaMod+proficiencyBonus}\n<name> <color>"
        )
        await dhttp.receive_message()

        avrae.message("!foobar")
        await dhttp.receive_delete()
        await dhttp.receive_message(
            f".+: {character.stats.get_mod('cha')} {character.stats.prof_bonus} "
            f"{character.stats.get_mod('cha') + character.stats.prof_bonus}\n"
            f"{character.get_title_name()} [0-9a-f]+"
        )

    async def test_echo_attributes_new(self, avrae, dhttp):
        character = await active_character(avrae)
        avrae.message(
            "!alias foobar echo {{c=character()}} {{c.stats.charisma}} {{c.stats.prof_bonus}} "
            "{{c.stats.charisma+c.stats.prof_bonus}}"
        )
        await dhttp.receive_message()

        avrae.message("!foobar")
        await dhttp.receive_delete()
        await dhttp.receive_message(
            f".+: {character.stats.charisma} {character.stats.prof_bonus} "
            f"{character.stats.charisma + character.stats.prof_bonus}"
        )


@pytest.mark.usefixtures("init_fixture", "character")
class TestCombatAliases:
    async def test_combat_aliases_setup(cls, avrae, dhttp):
        await start_init(avrae, dhttp)

    async def test_combat_function(self, avrae, dhttp):
        avrae.message("!test {{combat()}}")
        await dhttp.receive_message()

    async def test_combat_aliases_teardown(cls, avrae, dhttp):
        await end_init(avrae, dhttp)
