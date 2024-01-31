# TODO complete tests/add assertions
import disnake
import pytest

from tests.utils import active_character

pytestmark = pytest.mark.asyncio


@pytest.mark.usefixtures("character")
class TestBasicSheetCommands:
    async def test_attack(self, avrae, dhttp):
        avrae.message("!a dag")

    async def test_action(self, avrae, dhttp):
        character = await active_character(avrae)
        if not any(1 for action in character.actions if "Bardic" in action.name):
            pytest.skip("Character does not have bardic inspiration")
        avrae.message("!a bardic")

    async def test_attack_add(self, avrae, dhttp):
        avrae.message("!a add TESTATTACKFOOBAR -b 5 -d 1d6")

    async def test_attack_delete(self, avrae, dhttp):
        avrae.message("!a delete TESTATTACKFOOBAR")
        await dhttp.receive_message()
        avrae.message("y")

    async def test_action_list(self, avrae, dhttp):
        avrae.message("!a list")
        avrae.message("!a")

    async def test_save(self, avrae, dhttp):
        avrae.message("!s con")

    async def test_check(self, avrae, dhttp):
        avrae.message("!c performance")

    async def test_desc(self, avrae, dhttp):
        avrae.message("!desc")

    async def test_edit_desc(self, avrae, dhttp):
        avrae.message("!desc edit This is a new description.")

    async def test_remove_desc(self, avrae, dhttp):
        avrae.message("!desc remove")

    async def test_portrait(self, avrae, dhttp):
        avrae.message("!portrait")

    async def test_edit_portrait(self, avrae, dhttp):
        pass

    async def test_remove_portrait(self, avrae, dhttp):
        pass

    async def test_playertoken(self, avrae, dhttp):
        # avrae.message("!token")  # will error until formdata handler added
        pass

    async def test_sheet(self, avrae, dhttp):
        avrae.message("!sheet")

    async def test_character(self, avrae, dhttp):
        avrae.message("!char")

    async def test_character_list(self, avrae, dhttp):
        avrae.message("!char list")

    async def test_character_delete(self, avrae, dhttp):
        pass

    async def test_csettings(self, avrae, dhttp):
        pass

    async def test_cvar(self, avrae, dhttp):
        avrae.message("!cvar TESTCVAR foo")
        await dhttp.drain()

    async def test_remove_cvar(self, avrae, dhttp):
        avrae.message("!cvar delete TESTCVAR")
        await dhttp.drain()

    async def test_cvar_deleteall(self, avrae, dhttp):
        avrae.message("!cvar deleteall")
        await dhttp.receive_message()
        avrae.message("Yes, I am sure")
        await dhttp.drain()

    async def test_list_cvar(self, avrae, dhttp):
        avrae.message("!cvar list")


@pytest.mark.usefixtures("character")
class TestComplexAttacks:
    async def test_creation_and_attack(self, avrae, dhttp):
        avrae.message("!a add TESTATTACKFOOBAR -b 5 -d 1d6")
        await dhttp.receive_message("Created attack TESTATTACKFOOBAR!")

        async def _receive_attack(embed=None):
            await dhttp.receive_message(embed=embed)
            await dhttp.receive_delete()

        avrae.message("!a TESTATTACKFOOBAR")
        await _receive_attack()

        avrae.message("!a TESTATTACKFOOBAR -phrase foobar -title barfoo")
        await _receive_attack(disnake.Embed(description=r">>> \*foobar\*", title="barfoo"))

        avrae.message("!a TESTATTACKFOOBAR adv")
        await _receive_attack()

        avrae.message("!a TESTATTACKFOOBAR -ac 15")
        await _receive_attack()

        avrae.message("!a TESTATTACKFOOBAR -b 5")
        await _receive_attack()

        avrae.message("!a TESTATTACKFOOBAR -d 5 hit")
        await _receive_attack()

        avrae.message("!a TESTATTACKFOOBAR -criton 20 -c 15 hit crit")
        await _receive_attack()

        avrae.message("!a TESTATTACKFOOBAR -rr 2")
        await _receive_attack()

        avrae.message("!a TESTATTACKFOOBAR -t foo")
        await _receive_attack()

        avrae.message("!a TESTATTACKFOOBAR -rr 2 -t foo")
        await _receive_attack()
