import re

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

    # Attack bonus errors: Attack.build_str generates "+{attack_bonus}" patterns where
    # attack_bonus can be float("nan") from stringify_intexpr when IntExpression evaluation fails
    assert not re.search(r"[+-]nan\b", action_str), f"Found malformed attack bonus in: {action_str}"

    # Save DC errors: Save.build_str generates "DC {dc}" patterns where
    # dc can be float("nan") from stringify_intexpr when DC IntExpression evaluation fails
    assert not re.search(r"\bDC nan\b", action_str), f"Found malformed DC in: {action_str}"

    # Value context errors: Various build_str methods generate "Property: {value}" patterns where
    # value can be float("nan") from stringify_intexpr when numeric expressions fail
    assert not re.search(r":\s*nan\b", action_str), f"Found 'nan' in value context in: {action_str}"

    # UseCounter usage errors: UseCounter.build_str generates "uses {used}/{max}" patterns where
    # used/max can be float("nan") from stringify_intexpr when counter expressions fail
    assert not re.search(r"\buses\s+nan\b", action_str, re.IGNORECASE), f"Found 'uses nan' in: {action_str}"

    # UseCounter restore errors: UseCounter.build_str generates "restores {amount}" patterns where
    # amount can be float("nan") from stringify_intexpr when restore expressions fail
    assert not re.search(r"\brestores\s+nan\b", action_str, re.IGNORECASE), f"Found 'restores nan' in: {action_str}"

    # Unknown value errors: Various build_str methods use "Unknown" as fallback when
    # data lookup fails, appearing in value contexts that suggest missing/invalid data
    assert not re.search(r":\s*Unknown\b", action_str), f"Found 'Unknown' as value in: {action_str}"

    # Effect description errors: Effect descriptions should not show "Unknown" as it indicates
    # missing or malformed effect data rather than a legitimate effect name
    assert not re.search(r"\bEffect:\s*Unknown\b", action_str), f"Found 'Effect: Unknown' in: {action_str}"


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
