import pytest

from cogs5e.models.automation import Automation
from tests.utils import requires_data
from . import simulation_utils
from .simulation_utils import run_automation


def get_action_automation(action):
    automation_d = action["automation"]
    if action["skip"]:
        pytest.skip("Action is skipped")
    return Automation.from_data(automation_d)


# ==== tests ====
# --- ser/deser ---
def test_action_serialize(action):
    if action["skip"]:
        pytest.skip("Action is skipped")
    automation = action["automation"]
    assert Automation.from_data(automation)


def test_action_stringify(action, bob):
    automation = get_action_automation(action)
    action_str = automation.build_str(caster=bob)
    assert action_str
    assert "nan" not in action_str
    assert "unknown" not in action_str


# --- out of combat ---
# note: we use Ara as the caster for all action simulation since they can only be cast by a character
@pytest.mark.asyncio
@pytest.mark.simulation
@requires_data(fail_if_no_data=True)
async def test_action_simulate_no_target(action, ara, avrae):
    automation = get_action_automation(action)
    await run_automation(automation, avrae, caster=ara, targets=[])


@pytest.mark.asyncio
@pytest.mark.simulation
@requires_data(fail_if_no_data=True)
async def test_action_simulate_string_target(action, ara, avrae):
    automation = get_action_automation(action)
    await run_automation(automation, avrae, caster=ara, targets=["foobar"])


@pytest.mark.asyncio
@pytest.mark.simulation
@requires_data(fail_if_no_data=True)
async def test_action_simulate_statblock_targets(action, ara, bob, avrae):
    automation = get_action_automation(action)
    await run_automation(automation, avrae, caster=ara, targets=[ara, bob])


# --- in combat ---
@pytest.mark.asyncio
@pytest.mark.simulation
@requires_data(fail_if_no_data=True)
async def test_action_simulate_combat_no_target(action, ara, avrae, mock_combat):
    automation = get_action_automation(action)
    # caster not in combat
    await run_automation(automation, avrae, combat=mock_combat, caster=ara, targets=[])
    # caster in combat
    player = simulation_utils.create_player_combatant(mock_combat, avrae, ara)
    await run_automation(automation, avrae, combat=mock_combat, caster=player, targets=[])


@pytest.mark.asyncio
@pytest.mark.simulation
@requires_data(fail_if_no_data=True)
async def test_action_simulate_combat_targets(action, ara, avrae, mock_combat):
    automation = get_action_automation(action)
    # add things to combat
    basic = simulation_utils.create_basic_combatant(mock_combat, avrae)
    monster = simulation_utils.create_monster_combatant(mock_combat, avrae, monster_id=16939)
    player = simulation_utils.create_player_combatant(mock_combat, avrae, ara)

    await run_automation(
        automation,
        avrae,
        combat=mock_combat,
        caster=player,
        targets=[basic, monster, player],
    )
