import discord
import pytest

from tests.setup import TEST_CHANNEL_ID
from tests.utils import D20_PATTERN

pytestmark = pytest.mark.asyncio


@pytest.mark.usefixtures("init_fixture")
class TestInitiativeSimple:
    async def test_init_begin(self, avrae, dhttp):
        dhttp.clear()
        avrae.message("!init begin")
        await dhttp.receive_delete()
        await dhttp.receive_message("```Awaiting combatants...```")
        await dhttp.receive_edit("```markdown\nCurrent initiative: 0 (round 0)\n===============================\n```",
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
                                    r"```markdown\nCurrent initiative: \d+ \(round \d+\)\n"
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


# ===== Utilities =====
@pytest.fixture(scope="class")
async def init_fixture(avrae):
    """Ensures we clean up before and after ourselves. Init tests should be grouped in a class."""
    await avrae.mdb.combats.delete_one({"channel": str(TEST_CHANNEL_ID)})
    yield
    await avrae.mdb.combats.delete_one({"channel": str(TEST_CHANNEL_ID)})


async def start_init(avrae, dhttp):
    dhttp.clear()
    avrae.message("!init begin")
    await dhttp.receive_delete()
    await dhttp.receive_message()
    await dhttp.receive_edit()
    await dhttp.receive_pin()
    await dhttp.receive_message()


async def end_init(avrae, dhttp):
    dhttp.clear()
    avrae.message("!init end")
    await dhttp.receive_delete()
    await dhttp.receive_message()
    avrae.message("y")
    await dhttp.receive_delete()
    await dhttp.receive_delete()
    await dhttp.receive_message()
    await dhttp.receive_message(dm=True)
    await dhttp.receive_edit()
    await dhttp.receive_unpin()
    await dhttp.receive_edit()
