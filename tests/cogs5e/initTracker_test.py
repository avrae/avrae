import discord
import pytest

from cogs5e.models.sheet.resistance import Resistance
from gamedata.compendium import compendium
from tests.conftest import end_init, start_init
from tests.utils import D20_PATTERN, active_character, active_combat

pytestmark = pytest.mark.asyncio


@pytest.mark.usefixtures("init_fixture")
class TestInitiativeSimple:
    async def test_init_begin(self, avrae, dhttp):
        dhttp.clear()
        avrae.message("!init begin")
        await dhttp.receive_delete()
        await dhttp.receive_message("```Awaiting combatants...```")
        await dhttp.receive_edit("```md\nCurrent initiative: 0 (round 0)\n===============================\n```",
                                 regex=False)
        await dhttp.receive_pin()
        await dhttp.receive_message("Everyone roll for initiative!\nIf you have a character set up with SheetManager: "
                                    "`!init join`\nIf it's a 5e monster: `!init madd <monster name>`\nOtherwise: "
                                    "`!init add <modifier> <name>`", regex=False)

    async def test_init_end(self, avrae, dhttp):
        dhttp.clear()
        avrae.message("!init end")
        await dhttp.receive_delete()
        await dhttp.receive_message("Are you sure you want to end combat? (Reply with yes/no)", regex=False)
        avrae.message("y")
        await dhttp.receive_delete()
        await dhttp.receive_delete()
        await dhttp.receive_message("OK, ending...")
        await dhttp.receive_message(r"End of combat report: \d+ rounds "
                                    r"```md\nCurrent initiative: \d+ \(round \d+\)\n"
                                    r"===============================\n```.*", dm=True)
        await dhttp.receive_edit(r"[\s\S]*```-----COMBAT ENDED-----```")
        await dhttp.receive_unpin()
        await dhttp.receive_edit("Combat ended.")


@pytest.mark.usefixtures("init_fixture", "character")
class TestInitiativeWithCharacters:
    async def test_init_begin(self, avrae, dhttp):
        await start_init(avrae, dhttp)

    async def test_init_join(self, avrae, dhttp):
        dhttp.clear()
        avrae.message("!init join")
        await dhttp.receive_delete()
        await dhttp.receive_edit()
        join_embed = discord.Embed(
            title=rf".+ makes an Initiative check!",
            description=D20_PATTERN
        )
        join_embed.set_footer(text="Added to combat!")
        await dhttp.receive_message(embed=join_embed)

    async def test_init_end(self, avrae, dhttp):
        await end_init(avrae, dhttp)


@pytest.mark.usefixtures("init_fixture", "character")
class TestYourStandardInitiative:
    async def test_standard_init_setup(self, avrae, dhttp):
        await start_init(avrae, dhttp)
        avrae.message("!init join -p 50")
        await dhttp.drain()
        avrae.message("!init madd kobold")
        await dhttp.drain()
        avrae.message("!init add 0 TEST1")
        await dhttp.drain()
        avrae.message("!init add 0 TEST2")
        await dhttp.drain()
        avrae.message("!init next")
        await dhttp.drain()

    async def test_attacking(self, avrae, dhttp):
        character = await active_character(avrae)
        for combatant in (character.name, "KO1", "TEST1", "TEST2"):
            avrae.message(f"!i a \"{character.attacks[0].name}\" -t \"{combatant}\" hit")
            await dhttp.drain()
            c = (await active_combat(avrae)).get_combatant(combatant)
            if c.hp is not None:
                assert c.hp < c.max_hp

    async def test_hp_modifications(self, avrae, dhttp):
        character = await active_character(avrae)
        for combatant in (character.name, "KO1", "TEST1", "TEST2"):
            avrae.message(f"!i hp \"{combatant}\" max 100")
            await dhttp.drain()
            assert (await active_combat(avrae)).get_combatant(combatant).max_hp == 100

            avrae.message(f"!i hp \"{combatant}\" set 100")
            await dhttp.drain()
            assert (await active_combat(avrae)).get_combatant(combatant).hp == 100

            avrae.message(f"!i a \"{character.attacks[0].name}\" -t \"{combatant}\" hit")
            await dhttp.drain()
            assert (await active_combat(avrae)).get_combatant(combatant).hp < 100

    async def test_resistances(self, avrae, dhttp):
        character = await active_character(avrae)
        for combatant in (character.name, "KO1", "TEST1"):
            avrae.message(f"!i opt \"{combatant}\" -resist foobar")
            await dhttp.drain()
            resistances = (await active_combat(avrae)).get_combatant(combatant).resistances
            assert 'foobar' in [r.dtype for r in resistances.resist]
            assert 'foobar' not in [r.dtype for r in resistances.immune]
            assert 'foobar' not in [r.dtype for r in resistances.vuln]

            avrae.message(f"!i opt \"{combatant}\" -vuln foobar")
            await dhttp.drain()
            resistances = (await active_combat(avrae)).get_combatant(combatant).resistances
            assert 'foobar' in [r.dtype for r in resistances.vuln]
            assert 'foobar' not in [r.dtype for r in resistances.resist]

            avrae.message(f"!i opt \"{combatant}\" -neutral foobar")
            await dhttp.drain()
            resistances = (await active_combat(avrae)).get_combatant(combatant).resistances
            assert 'foobar' not in [r.dtype for r in resistances.vuln]

    async def test_complex_resistances(self, avrae, dhttp):
        character = await active_character(avrae)
        for combatant in (character.name, "KO1", "TEST1"):
            avrae.message(f"!i opt \"{combatant}\" -resist \"magical foobar\"")
            await dhttp.drain()
            resistances = (await active_combat(avrae)).get_combatant(combatant).resistances
            assert Resistance('foobar', only=['magical']) in resistances.resist

            avrae.message(f"!i opt \"{combatant}\" -vuln \"magical foobar\"")
            await dhttp.drain()
            resistances = (await active_combat(avrae)).get_combatant(combatant).resistances
            assert Resistance('foobar', only=['magical']) not in resistances.resist
            assert Resistance('foobar', only=['magical']) in resistances.vuln

            avrae.message(f"!i opt \"{combatant}\" -neutral \"magical foobar\"")
            await dhttp.drain()
            resistances = (await active_combat(avrae)).get_combatant(combatant).resistances
            assert Resistance('foobar', only=['magical']) not in resistances.vuln

    async def test_resistance_effects(self, avrae, dhttp):
        character = await active_character(avrae)
        for combatant in (character.name, "KO1", "TEST1"):
            avrae.message(f"!i opt \"{combatant}\" -resist foobar")  # start with a known resistance
            await dhttp.drain()

            avrae.message(f"!i effect \"{combatant}\" test -resist foobar")
            await dhttp.drain()
            resistances = (await active_combat(avrae)).get_combatant(combatant).resistances
            assert 'foobar' in [r.dtype for r in resistances.resist]
            assert 'foobar' not in [r.dtype for r in resistances.immune]
            assert 'foobar' not in [r.dtype for r in resistances.vuln]

            avrae.message(f"!i effect \"{combatant}\" test2 -vuln foobar -dur 1")  # effects can stack
            await dhttp.drain()
            resistances = (await active_combat(avrae)).get_combatant(combatant).resistances
            assert 'foobar' in [r.dtype for r in resistances.vuln]
            assert 'foobar' in [r.dtype for r in resistances.resist]

    async def test_silver_resists(self, avrae, dhttp):
        character = await active_character(avrae)
        for combatant in (character.name, "KO1", "TEST1", "TEST2"):
            avrae.message(f'!i opt "{combatant}" -resist "nonsilvered foo"')  # make sure silvered will work
            await dhttp.drain()

            avrae.message(f'!i hp "{combatant}" set 100')
            avrae.message(f'!i a test -t "{combatant}" hit -custom -d 10[foo] silvered')
            await dhttp.drain()
            assert (await active_combat(avrae)).get_combatant(combatant).hp == 90
            avrae.message(f'!i a test -t "{combatant}" hit -custom -d 10[foo]')
            await dhttp.drain()
            assert (await active_combat(avrae)).get_combatant(combatant).hp == 85

    async def test_magical_resists(self, avrae, dhttp):
        character = await active_character(avrae)
        for combatant in (character.name, "KO1", "TEST1"):
            avrae.message(f'!i opt "{combatant}" -resist "nonmagical bar"')  # since a change was made to magical
            await dhttp.drain()

            avrae.message(f'!i hp "{combatant}" set 100')
            avrae.message(f'!i a test -t "{combatant}" hit -custom -d 10[bar] magical')
            await dhttp.drain()
            assert (await active_combat(avrae)).get_combatant(combatant).hp == 90
            avrae.message(f'!i a test -t "{combatant}" hit -custom -d 10[bar]')
            await dhttp.drain()
            assert (await active_combat(avrae)).get_combatant(combatant).hp == 85

    async def test_effect_durations(self, avrae, dhttp):
        avrae.message(f"!i next")
        await dhttp.drain()
        avrae.message(f"!i next")
        await dhttp.drain()
        avrae.message(f"!i next")
        await dhttp.drain()
        avrae.message(f"!i next")
        await dhttp.drain()

        character = await active_character(avrae)
        for combatant in (character.name, "KO1", "TEST1"):
            effects = (await active_combat(avrae)).get_combatant(combatant).get_effects()
            assert len(effects) == 1

            avrae.message(f"!i re \"{combatant}\"")
            await dhttp.drain()

    async def test_standard_init_teardown(self, avrae, dhttp):
        await end_init(avrae, dhttp)


@pytest.mark.usefixtures("init_fixture", "character")
class TestInitiativeStatBlockCopying:
    async def test_init_begin(self, avrae, dhttp):
        await start_init(avrae, dhttp)

    async def test_character_copies(self, avrae, dhttp):
        dhttp.clear()
        avrae.message("!init join")
        await dhttp.drain()

        character = await active_character(avrae)
        combatant = (await active_combat(avrae)).get_combatant(character.name)

        assert combatant.resistances is not character.resistances
        assert combatant.spellbook is character.spellbook
        assert combatant.stats is character.stats
        assert combatant.skills is character.skills
        assert combatant.saves is character.saves

    async def test_monster_copies(self, avrae, dhttp):
        dhttp.clear()
        avrae.message("!init madd kobold")
        await dhttp.drain()

        kobold = next(m for m in compendium.monsters if m.name == "Kobold")
        combatant = (await active_combat(avrae)).get_combatant("KO1")

        assert combatant.resistances is not kobold.resistances
        assert combatant.spellbook is not kobold.spellbook
        assert combatant.stats is kobold.stats
        assert combatant.skills is kobold.skills
        assert combatant.saves is kobold.saves

    async def test_init_end(self, avrae, dhttp):
        await end_init(avrae, dhttp)


@pytest.mark.usefixtures("init_fixture")
async def test_commands_no_error(avrae, dhttp):
    """
    Runs through a gauntlet of init commands and just checks that there are no errors, without any assertations on the
    state
    """
    commands = [
        "!init begin",
        "!init madd kobold -n 3",
        "!init madd mage"
        # test round tracking
        "!init next",  # KO1
        "!init next",  # KO2
        "!init next",  # KO3
        "!init next",  # MA1
        "!init next",  # KO1
        # test cast
        "!i goto MA1",
        '!i cast "fire bolt" -t ko1 -t ko2',
        '!i hp ko1 set 0',
        # test autoremove
        "!init next",
        "!init next",
        "!init next",
        "!init next",
        "!init next",
        # test attacking
        "!i goto ko3",
        '!i a "dagger" -t ma1',
        # test effect parenting
        "!i effect ko3 teffect",
        "!i effect ma1 teffect2 -dur 2 -parent ko3|teffect",
        "!i skipround 3",
        # test effect parenting with renames
        "!i effect ko3 teffect2",
        "!i effect ma1 teffect22 -dur 2 -parent ko3|teffect2",
        "!i opt ma1 -name mage1",
        "!i opt ko3 -name kobold3",
        "!i skipround 3",
        # test removing combatant with child effects
        "!i effect kobold3 teffect22",
        "!i effect mage1 teffect222 -dur 2 -parent kobold3|teffect22",
        "!i remove kobold3",
        "!i skipround 3",
    ]

    for command in commands:
        avrae.message(command)
        await dhttp.drain()


@pytest.mark.usefixtures("init_fixture")
async def test_assign_groups(avrae, dhttp):
    """AVRAE-BOT-11R: assigning groups before the combat starts"""
    commands = [
        "!init begin",
        "!init madd kobold -n 3",
        "!init opt ko1 -group kobolds",
        "!init opt ko1 -group none",
        "!init next",
        "!init opt ko1 -group kobolds",
        "!init opt ko1 -group none",
    ]

    for command in commands:
        avrae.message(command)
        await dhttp.drain()
