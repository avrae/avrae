import pytest

from tests.setup import TEST_CHANNEL_ID

pytestmark = pytest.mark.asyncio


async def test_init_begin(avrae, dhttp):
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


async def test_init_end(avrae, dhttp):
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


@pytest.fixture(autouse=True, scope="module")
async def init_fixture(avrae):
    """Ensures we clean up before and after ourselves."""
    await avrae.mdb.combats.delete_one({"channel": str(TEST_CHANNEL_ID)})
    yield
    await avrae.mdb.combats.delete_one({"channel": str(TEST_CHANNEL_ID)})
