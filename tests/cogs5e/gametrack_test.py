import pytest
from discord import Embed

from tests.utils import active_character

pytestmark = pytest.mark.asyncio


@pytest.mark.usefixtures("character")
class TestGame:
    async def test_g_hp(self, avrae, dhttp):
        avrae.message("!g hp")
        await dhttp.receive_delete()
        await dhttp.receive_message(r".+: (\d+)/\1")

        character = await active_character(avrae)
        if not character.max_hp > 1:
            pytest.xfail("Character does not have at least 2 max HP")

        avrae.message("!g hp set 1")
        await dhttp.receive_delete()
        await dhttp.receive_message(r".+: 1/\d+")

        avrae.message("!g hp mod 1")
        await dhttp.receive_delete()
        await dhttp.receive_message(r".+: 2/\d+")

        avrae.message("!g hp -1")
        await dhttp.receive_delete()
        await dhttp.receive_message(r".+: 1/\d+")

        avrae.message("!g hp max")
        await dhttp.receive_delete()
        await dhttp.receive_message(r".+: (\d+)/\1")

    async def test_g_lr(self, avrae, dhttp):
        avrae.message("!g lr")
        await dhttp.receive_delete()
        lr_embed = Embed(title=r".+ took a Long Rest!")
        lr_embed.add_field(name="Reset Values", value=r".*")
        await dhttp.receive_message(embed=lr_embed)
        await dhttp.receive_message(embed=Embed())

        avrae.message("!g lr -h")
        await dhttp.receive_delete()
        await dhttp.receive_message(embed=lr_embed)

    async def test_g_sr(self, avrae, dhttp):
        avrae.message("!g sr")
        await dhttp.receive_delete()
        sr_embed = Embed(title=r".+ took a Short Rest!")
        sr_embed.add_field(name="Reset Values", value=r".*")
        await dhttp.receive_message(embed=sr_embed)
        await dhttp.receive_message(embed=Embed())

        avrae.message("!g sr -h")
        await dhttp.receive_delete()
        await dhttp.receive_message(embed=sr_embed)

    async def test_g_ss(self, avrae, dhttp):
        char = await active_character(avrae)

        avrae.message("!g ss")
        await dhttp.receive_delete()
        ss_embed = Embed(title=char.name, description=r"__Remaining Spell Slots__\n")
        await dhttp.receive_message(embed=ss_embed)

        if not char.spellbook.get_max_slots(1):  # we don't need to care about this character anymore
            return

    async def test_g_status(self, avrae, dhttp):
        avrae.message("!g status")

    async def test_g_thp(self, avrae, dhttp):
        avrae.message("!g thp")
        await dhttp.receive_delete()
        await dhttp.receive_message(r".+: (\d+)/\1")

    async def test_g_ds(self, avrae, dhttp):
        avrae.message("!g ds")

    async def test_s_death(self, avrae, dhttp):
        avrae.message("!s death")
