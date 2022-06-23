import pytest

from cogs5e.models.automation import Automation
from gamedata import Monster
from tests.utils import requires_data
from . import simulation_utils
from .simulation_utils import run_automation


def unfurl_action_pair(action):
    automation_d = action[0]["automation"]
    if automation_d is None:
        pytest.skip("Action has no automation")
    return Automation.from_data(automation_d), Monster.from_data(action[1])


# ==== tests ====
# --- ser/deser ---
def test_attack_serialize(monster):
    assert Monster.from_data(monster)


def test_monster_stringify(monster_attack, bob):
    automation, caster = unfurl_action_pair(monster_attack)
    attack_str = automation.build_str(caster=bob)
    assert attack_str
    assert "nan" not in attack_str


# --- out of combat ---
# all out-of-combat simulation tests use the monster as the caster, as if it was cast from !ma
@pytest.mark.asyncio
@pytest.mark.simulation
@requires_data(fail_if_no_data=True)
async def test_monster_simulate_no_target(monster_attack, avrae):
    automation, caster = unfurl_action_pair(monster_attack)
    await run_automation(automation, avrae, caster=caster, targets=[])


@pytest.mark.asyncio
@pytest.mark.simulation
@requires_data(fail_if_no_data=True)
async def test_monster_simulate_string_target(monster_attack, avrae):
    automation, caster = unfurl_action_pair(monster_attack)
    await run_automation(automation, avrae, caster=caster, targets=["foobar"])


@pytest.mark.asyncio
@pytest.mark.simulation
@requires_data(fail_if_no_data=True)
async def test_monster_simulate_statblock_targets(monster_attack, ara, bob, avrae):
    automation, caster = unfurl_action_pair(monster_attack)
    await run_automation(automation, avrae, caster=caster, targets=[ara, bob])


# --- in combat ---
@pytest.mark.asyncio
@pytest.mark.simulation
@requires_data(fail_if_no_data=True)
async def test_monster_simulate_combat_no_target(monster_attack, ara, avrae, mock_combat):
    automation, caster = unfurl_action_pair(monster_attack)
    await run_automation(automation, avrae, combat=mock_combat, caster=caster, targets=[])


@pytest.mark.asyncio
@pytest.mark.simulation
@requires_data(fail_if_no_data=True)
async def test_monster_simulate_combat_targets(monster_attack, ara, avrae, mock_combat):
    automation, caster = unfurl_action_pair(monster_attack)
    # add things to combat
    basic = simulation_utils.create_basic_combatant(mock_combat, avrae)
    monster = simulation_utils.create_monster_combatant_from_monster(mock_combat, avrae, caster)
    player = simulation_utils.create_player_combatant(mock_combat, avrae, ara)

    await run_automation(
        automation,
        avrae,
        combat=mock_combat,
        caster=monster,
        targets=[basic, monster, player],
    )
