import pytest

from tests.utils import active_character

pytestmark = pytest.mark.asyncio


async def test_echo_alias(avrae, dhttp):
    avrae.message("!alias foobar echo foobar")
    await dhttp.receive_message("Alias `foobar` added.```py\n!alias foobar echo foobar\n```")
    avrae.message("!foobar")
    await dhttp.receive_delete()
    await dhttp.receive_message(".+: foobar")


async def test_variables(avrae, dhttp):
    avrae.message("!uvar foobar Hello world")
    await dhttp.receive_message()
    avrae.message("!gvar create I am a gvar")
    match = await dhttp.receive_message("Created global variable `([0-9a-f-]+)`.")
    address = match.group(1)

    avrae.message("!alias foobar echo <foobar> {foobar} {{foobar}}\n" +
                  f"{{{{get_gvar('{address}')}}}}")  # {{get_gvar('1234...')}}
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
    avrae.message("!foobar \"foo bar\"")
    await dhttp.receive_delete()
    await dhttp.receive_message(".+: the first argument is \"foo bar\" yay")


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
    avrae.message("!foobar \"foo bar\"")
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
    avrae.message("!foobar \"foo bar\"")
    await dhttp.receive_delete()
    await dhttp.receive_message(r".+: the arguments are \['foo bar'\]")


async def test_servalias(avrae, dhttp):
    avrae.message("!servalias serverfoobar echo this is serverfoobar")
    await dhttp.drain()

    avrae.message("!serverfoobar")
    await dhttp.receive_delete()
    await dhttp.receive_message(r".+: this is serverfoobar")

    avrae.message("!serverfoobar", dm=True)
    assert dhttp.queue_empty()


async def test_alias_vs_servalias(avrae, dhttp):
    avrae.message("!alias foobar echo this is foobar")
    avrae.message("!servalias foobar echo this is server foobar")
    await dhttp.drain()

    avrae.message("!foobar")
    await dhttp.receive_delete()
    await dhttp.receive_message(r".+: this is foobar")


@pytest.mark.usefixtures("character")
class TestCharacterAliases:
    async def test_echo_attributes(self, avrae, dhttp):
        character = await active_character(avrae)
        avrae.message("!alias foobar echo {charismaMod} {proficiencyBonus} {charismaMod+proficiencyBonus}\n"
                      "<name> <color>")
        await dhttp.receive_message()

        avrae.message("!foobar")
        await dhttp.receive_delete()
        await dhttp.receive_message(f".+: {character.stats.get_mod('cha')} {character.stats.prof_bonus} "
                                    f"{character.stats.get_mod('cha') + character.stats.prof_bonus}\n"
                                    f"{character.get_title_name()} [0-9a-f]+")

    async def test_echo_attributes_new(self, avrae, dhttp):
        character = await active_character(avrae)
        avrae.message("!alias foobar echo {{c=character()}} {{c.stats.charisma}} {{c.stats.prof_bonus}} "
                      "{{c.stats.charisma+c.stats.prof_bonus}}")
        await dhttp.receive_message()

        avrae.message("!foobar")
        await dhttp.receive_delete()
        await dhttp.receive_message(f".+: {character.stats.charisma} {character.stats.prof_bonus} "
                                    f"{character.stats.charisma + character.stats.prof_bonus}")
