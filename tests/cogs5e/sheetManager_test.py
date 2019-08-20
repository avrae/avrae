# TODO complete tests/add assertations
import pytest

pytestmark = pytest.mark.asyncio


@pytest.mark.usefixtures("character")
class TestSheetStuff:
    async def test_attack(self, avrae, dhttp):
        avrae.message("!a dag")

    async def test_attack_list(self, avrae, dhttp):
        avrae.message("!a list")
        avrae.message("!a")

    async def test_attack_add(self, avrae, dhttp):
        avrae.message("!a add TESTATTACKFOOBAR -b 5 -d 1d6")

    async def test_attack_delete(self, avrae, dhttp):
        avrae.message("!a delete TESTATTACKFOOBAR")

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

    async def test_playertoken(self, avrae, dhttp):  # todo figure out how to handle files/formdata
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

    async def test_remove_cvar(self, avrae, dhttp):
        avrae.message("!cvar delete TESTCVAR")

    async def test_cvar_deleteall(self, avrae, dhttp):
        avrae.message("!cvar deleteall")
        avrae.message("Yes, I am sure")

    async def test_list_cvar(self, avrae, dhttp):
        avrae.message("!cvar list")
