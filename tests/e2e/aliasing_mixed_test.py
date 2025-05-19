import pytest

from tests.utils import active_character, end_init, start_init

pytestmark = pytest.mark.asyncio


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

    async def test_combat_me(self, avrae, dhttp):
        avrae.message("!test {{combat().me}}")
        await dhttp.receive_message(r".+:\s*$")  # nothing after the colon, should return None
        # character joins
        character = await active_character(avrae)
        avrae.message("!init join")
        await dhttp.drain()

        avrae.message("!test {{combat().me.name}}")
        await dhttp.receive_message(f".+: {character.name}")  # should return the character's name

    async def test_combat_aliases_teardown(cls, avrae, dhttp):
        await end_init(avrae, dhttp)
