import pytest
from disnake import Embed

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
        await dhttp.receive_message(r".+: 1/\d+ \([+-]\d+\)")
        char = await active_character(avrae)
        assert char.hp == 1

        avrae.message("!g hp mod 1")
        await dhttp.receive_delete()
        await dhttp.receive_message(r".+: 2/\d+ \([+-]\d+\)")
        char = await active_character(avrae)
        assert char.hp == 2

        avrae.message("!g hp -1")
        await dhttp.receive_delete()
        await dhttp.receive_message(r".+: 1/\d+ \([+-]\d+\)")
        char = await active_character(avrae)
        assert char.hp == 1

        avrae.message("!g hp max")
        await dhttp.receive_delete()
        await dhttp.receive_message(r".+: (\d+)/\1 \([+-]\d+\)")
        char = await active_character(avrae)
        assert char.hp == char.max_hp

    async def test_g_lr(self, avrae, dhttp):
        avrae.message("!g lr")
        await dhttp.receive_delete()
        lr_embed = Embed(title=r".+ took a Long Rest!")
        lr_embed.add_field(name="Hit Points", value=r".*")
        await dhttp.receive_message(embed=lr_embed)

        avrae.message("!g lr -h")
        await dhttp.receive_delete()
        lr_embed = Embed(title=r".+ took a Long Rest!")
        lr_embed.add_field(name="Reset Values", value=r".*")
        await dhttp.receive_message(embed=lr_embed)

    async def test_g_sr(self, avrae, dhttp):
        avrae.message("!g sr")
        await dhttp.receive_delete()
        sr_embed = Embed(title=r".+ took a Short Rest!")
        sr_embed.add_field(name="Hit Points", value=r".*")
        await dhttp.receive_message(embed=sr_embed)

        avrae.message("!g sr -h")
        await dhttp.receive_delete()
        sr_embed = Embed(title=r".+ took a Short Rest!")
        sr_embed.add_field(name="Reset Values", value=r".*")
        await dhttp.receive_message(embed=sr_embed)

    async def test_g_ss(self, avrae, dhttp):
        char = await active_character(avrae)

        avrae.message("!g ss")
        await dhttp.receive_delete()
        ss_embed = Embed(description=r"__\*\*Remaining Spell Slots\*\*__\n")
        ss_embed.set_author(name=char.name)
        await dhttp.receive_message(embed=ss_embed)

        if not char.spellbook.get_max_slots(1):  # we don't need to care about this character anymore
            return

        avrae.message("!g ss 1")
        await dhttp.receive_delete()
        ss_embed = Embed(description=r"__\*\*Remaining Level 1 Spell Slots\*\*__\n")
        ss_embed.set_author(name=char.name)
        await dhttp.receive_message(embed=ss_embed)

        avrae.message("!g ss 1 -1")
        await dhttp.receive_delete()
        await dhttp.receive_message(embed=ss_embed)
        char = await active_character(avrae)
        assert char.spellbook.get_slots(1) == char.spellbook.get_max_slots(1) - 1

        avrae.message("!g ss 1 1")
        await dhttp.receive_delete()
        await dhttp.receive_message(embed=ss_embed)
        char = await active_character(avrae)
        assert char.spellbook.get_slots(1) == 1

        avrae.message("!g ss 1 +1")
        await dhttp.receive_delete()
        await dhttp.receive_message(embed=ss_embed)
        char = await active_character(avrae)
        assert char.spellbook.get_slots(1) == min(2, char.spellbook.get_max_slots(1))

    async def test_g_status(self, avrae, dhttp):
        avrae.message("!g status")
        await dhttp.receive_delete()
        char = await active_character(avrae)
        status_embed = Embed()
        status_embed.set_author(name=char.name)
        status_embed.add_field(name="Hit Points", value=r".*")
        status_embed.add_field(name="Spell Slots", value=r".*")
        if char.death_saves.successes != 0 or char.death_saves.fails != 0:
            status_embed.add_field(name="Death Saves", value=r".*")
        for _ in char.consumables:
            status_embed.add_field(name=r".*", value=r".*")
        await dhttp.receive_message(embed=status_embed)

    async def test_g_thp(self, avrae, dhttp):
        avrae.message("!g thp")
        await dhttp.receive_delete()
        await dhttp.receive_message(r".+: (\d+)/\1")

        avrae.message("!g thp 5")
        await dhttp.receive_delete()
        await dhttp.receive_message(r".+: (\d+)/\1 \(5 temp\)")
        char = await active_character(avrae)
        assert char.temp_hp == 5
        assert char.hp == char.max_hp

        avrae.message("!g thp 10")
        await dhttp.receive_delete()
        await dhttp.receive_message(r".+: (\d+)/\1 \(10 temp\)")
        char = await active_character(avrae)
        assert char.temp_hp == 10
        assert char.hp == char.max_hp

        avrae.message("!g thp -8")
        await dhttp.receive_delete()
        await dhttp.receive_message(r".+: (\d+)/\1 \(2 temp\)")
        char = await active_character(avrae)
        assert char.temp_hp == 2
        assert char.hp == char.max_hp

        avrae.message("!g hp -2")
        await dhttp.receive_delete()
        await dhttp.receive_message(r".+: (\d+)/\1")
        char = await active_character(avrae)
        assert char.temp_hp == 0
        assert char.hp == char.max_hp

    async def test_g_ds(self, avrae, dhttp):
        avrae.message("!g ds")

    async def test_s_death(self, avrae, dhttp):
        avrae.message("!s death")

    async def test_game_coinpurse(self, avrae, dhttp):
        avrae.message("!game coinpurse")
        await dhttp.receive_delete()
        await dhttp.receive_message()
        char = await active_character(avrae)
        assert char.coinpurse.pp == 0
        assert char.coinpurse.gp == 0
        assert char.coinpurse.ep == 0
        assert char.coinpurse.sp == 0
        assert char.coinpurse.cp == 0

        avrae.message("!game coinpurse +10gp")
        await dhttp.receive_delete()
        await dhttp.receive_message()
        char = await active_character(avrae)
        assert char.coinpurse.pp == 0
        assert char.coinpurse.gp == 10
        assert char.coinpurse.ep == 0
        assert char.coinpurse.sp == 0
        assert char.coinpurse.cp == 0

        avrae.message("!game coinpurse -1")
        await dhttp.receive_delete()
        await dhttp.receive_message()
        char = await active_character(avrae)
        assert char.coinpurse.pp == 0
        assert char.coinpurse.gp == 9
        assert char.coinpurse.ep == 0
        assert char.coinpurse.sp == 0
        assert char.coinpurse.cp == 0

        avrae.message("!game coinpurse -10cp")
        await dhttp.receive_delete()
        await dhttp.receive_message("You don't have enough of the chosen")
        avrae.message("Yes")
        await dhttp.drain()
        char = await active_character(avrae)
        assert char.coinpurse.pp == 0
        assert char.coinpurse.gp == 8
        assert char.coinpurse.ep == 1
        assert char.coinpurse.sp == 4
        assert char.coinpurse.cp == 0

        avrae.message("!game coinpurse 10pp -1gp +3sp -2ep -1cp")
        await dhttp.receive_delete()
        await dhttp.receive_message("You don't have enough of the chosen")
        avrae.message("Yes")
        await dhttp.drain()
        char = await active_character(avrae)
        assert char.coinpurse.pp == 10
        assert char.coinpurse.gp == 6
        assert char.coinpurse.ep == 1
        assert char.coinpurse.sp == 6
        assert char.coinpurse.cp == 9

        avrae.message("!game coinpurse 12345cp")
        await dhttp.receive_delete()
        await dhttp.receive_message()
        char = await active_character(avrae)
        assert char.coinpurse.pp == 10
        assert char.coinpurse.gp == 6
        assert char.coinpurse.ep == 1
        assert char.coinpurse.sp == 6
        assert char.coinpurse.cp == 12354

        avrae.message("!game coinpurse convert")
        await dhttp.receive_delete()
        await dhttp.receive_message()
        char = await active_character(avrae)
        assert char.coinpurse.pp == 23
        assert char.coinpurse.gp == 0
        assert char.coinpurse.ep == 1
        assert char.coinpurse.sp == 1
        assert char.coinpurse.cp == 4


@pytest.mark.usefixtures("character")
class TestSpellbook:
    async def test_sb(self, avrae, dhttp):
        avrae.message("!sb")

    async def test_sb_add(self, avrae, dhttp):
        avrae.message("!sb add fireball")

    async def test_sb_remove(self, avrae, dhttp):
        avrae.message("!sb remove fireball")


@pytest.mark.usefixtures("character")
class TestCustomCounters:
    async def test_cc_create(self, avrae, dhttp):
        avrae.message("!cc create TESTCC")
        await dhttp.receive_message("Custom counter created.")

        avrae.message("!cc create TESTLIMITS -min 0 -max 100")
        await dhttp.receive_message("Custom counter created.")

        avrae.message("!cc create TESTRESETTO1 -min 0 -max 100 -resetto 10")
        await dhttp.receive_message("Custom counter created.")

        avrae.message("!cc create TESTRESETTO2 -min 0 -max 100 -resetto level")
        await dhttp.receive_message("Custom counter created.")

        avrae.message("!cc create TESTRESETBY1 -min 0 -max 100 -resetby 5")
        await dhttp.receive_message("Custom counter created.")

        avrae.message("!cc create TESTRESETBY2 -min 0 -max 100 -resetby {level}")
        await dhttp.receive_message("Custom counter created.")

    async def test_cc_summary(self, avrae, dhttp):
        avrae.message("!cc")
        char = await active_character(avrae)
        cc_embed = Embed()
        # Needed to allow for embed comparison

        for _ in char.consumables:
            cc_embed.add_field(
                name=".+",
                value=r"((◉+〇*)|(\*\*Current Value\*\*:.+))(\n)*(\*\*Range\*\*: .+)*(\n)*(\*\*Resets On\*\*: .+)*",
            )
        await dhttp.receive_message(embed=cc_embed)

    async def test_cc_misc(self, avrae, dhttp):
        char = await active_character(avrae)
        cc_embed = Embed()
        test_cc = next(cc for cc in char.consumables if cc.name == "TESTCC")
        test_cc_limits = next(cc for cc in char.consumables if cc.name == "TESTLIMITS")

        cc_embed.add_field(name=r".+", value=r"((\d+)|(\d+\/\d+)) (\((\+|-)\d+\))(\n)*(\(\d+ .+\))*")
        avrae.message("!cc TESTCC +5")
        await dhttp.receive_delete()
        await dhttp.receive_message(embed=cc_embed)
        assert test_cc.value == 5

        avrae.message("!cc TESTLIMITS -99")
        await dhttp.receive_delete()
        await dhttp.receive_message(embed=cc_embed)
        assert test_cc_limits.value == 1

        avrae.message("!cc TESTLIMITS -2")
        await dhttp.receive_delete()
        await dhttp.receive_message(embed=cc_embed)
        assert test_cc_limits.value == 0

    async def test_cc_reset(self, avrae, dhttp):
        char = await active_character(avrae)

        test_cc_limits = next(cc for cc in char.consumables if cc.name == "TESTLIMITS")
        avrae.message("!cc reset TESTLIMITS")
        await dhttp.receive_message(r"(\w+: )(\d+\/\d+ )(\((\+|-)\d+\))")
        assert test_cc_limits.value == 100

    async def test_cc_reset_to(self, avrae, dhttp):
        char = await active_character(avrae)
        cc_embed = Embed()
        cc_embed.add_field(name=r".+", value=r"((\d+)|(\d+\/\d+)) (\((\+|-)\d+\))(\n)*(\(\d+ .+\))*")

        test_cc_resetto_1 = next(cc for cc in char.consumables if cc.name == "TESTRESETTO1")
        test_cc_resetto_2 = next(cc for cc in char.consumables if cc.name == "TESTRESETTO2")

        avrae.message("!cc TESTRESETTO1 set 0")
        await dhttp.receive_delete()
        await dhttp.receive_message(embed=cc_embed)
        assert test_cc_resetto_1.value == 0

        avrae.message("!cc TESTRESETTO2 set 0")
        await dhttp.receive_delete()
        await dhttp.receive_message(embed=cc_embed)
        assert test_cc_resetto_2.value == 0

        avrae.message("!cc reset TESTRESETTO1")
        await dhttp.receive_message(r"(\w+: )(\d+\/\d+ )(\((\+|-)\d+\))")
        assert test_cc_resetto_1.value == 10

        avrae.message("!cc reset TESTRESETTO2")
        await dhttp.receive_message(r"(\w+: )(\d+\/\d+ )(\((\+|-)\d+\))")
        assert test_cc_resetto_2.value == char.levels.total_level

    async def test_cc_reset_by(self, avrae, dhttp):
        char = await active_character(avrae)
        cc_embed = Embed()
        cc_embed.add_field(name=r".+", value=r"((\d+)|(\d+\/\d+)) (\((\+|-)\d+\))(\n)*(\(\d+ .+\))*")

        test_cc_resetby_1 = next(cc for cc in char.consumables if cc.name == "TESTRESETBY1")
        test_cc_resetby_2 = next(cc for cc in char.consumables if cc.name == "TESTRESETBY2")

        avrae.message("!cc TESTRESETBY1 set 0")
        await dhttp.receive_delete()
        await dhttp.receive_message(embed=cc_embed)
        assert test_cc_resetby_1.value == 0

        avrae.message("!cc TESTRESETBY2 set 0")
        await dhttp.receive_delete()
        await dhttp.receive_message(embed=cc_embed)
        assert test_cc_resetby_2.value == 0

        avrae.message("!cc reset TESTRESETBY1")
        await dhttp.receive_message(r"(\w+: )(\d+\/\d+ )(\((\+|-)\d+ = `\d+`\))")
        assert test_cc_resetby_1.value == 5

        avrae.message("!cc reset TESTRESETBY1")
        await dhttp.receive_message(r"(\w+: )(\d+\/\d+ )(\((\+|-)\d+ = `\d+`\))")
        assert test_cc_resetby_1.value == 10

        level = char.levels.total_level
        avrae.message("!cc reset TESTRESETBY2")
        await dhttp.receive_message(r"(\w+: )(\d+\/\d+ )(\((\+|-)\d+ = `\d+`\))")
        assert test_cc_resetby_2.value == level

        avrae.message("!cc reset TESTRESETBY2")
        await dhttp.receive_message(r"(\w+: )(\d+\/\d+ )(\((\+|-)\d+ = `\d+`\))")
        assert test_cc_resetby_2.value == level * 2

    async def test_cc_delete(self, avrae, dhttp):
        avrae.message("!cc delete TESTCC")
        await dhttp.receive_message("Deleted counter TESTCC.")

        avrae.message("!cc delete TESTLIMITS")
        await dhttp.receive_message("Deleted counter TESTLIMITS.")

        avrae.message("!cc delete TESTRESETTO1")
        await dhttp.receive_message("Deleted counter TESTRESETTO1.")

        avrae.message("!cc delete TESTRESETTO2")
        await dhttp.receive_message("Deleted counter TESTRESETTO2.")

        avrae.message("!cc delete TESTRESETBY1")
        await dhttp.receive_message("Deleted counter TESTRESETBY1.")

        avrae.message("!cc delete TESTRESETBY2")
        await dhttp.receive_message("Deleted counter TESTRESETBY2.")
