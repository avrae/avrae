import pytest

from tests.utils import active_character

pytestmark = pytest.mark.asyncio


class TestSimpleAliases:
    async def test_echo_alias(self, avrae, dhttp):
        avrae.message("!alias foobar echo foobar")
        await dhttp.receive_message("Alias `!foobar` added for command:```py\n!foobar echo foobar\n```")
        avrae.message("!foobar")
        await dhttp.receive_delete()
        await dhttp.receive_message(".+: foobar")

    async def test_variables(self, avrae, dhttp):
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
