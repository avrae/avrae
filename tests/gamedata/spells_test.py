import pytest

from cogs5e.models.automation import Automation
from gamedata import Monster, Spell, compendium
from tests.utils import requires_data
from . import simulation_utils
from .simulation_utils import run_automation


def get_spell_automation(spell):
    automation_d = spell["automation"]
    if automation_d is None:
        pytest.skip("Spell has no automation")
    return Automation.from_data(automation_d)


# ==== tests ====
# --- ser/deser ---
def test_spell_serialize(spell):
    assert Spell.from_data(spell)


def test_spell_stringify(spell, bob):
    automation = get_spell_automation(spell)
    spell_str = automation.build_str(caster=bob)
    assert spell_str
    assert "nan" not in spell_str


# --- out of combat ---
@pytest.mark.asyncio
@pytest.mark.simulation
@requires_data(fail_if_no_data=True)
async def test_spell_simulate_no_target(spell, bob, avrae):
    automation = get_spell_automation(spell)
    await run_automation(automation, avrae, caster=bob, targets=[])


@pytest.mark.asyncio
@pytest.mark.simulation
@requires_data(fail_if_no_data=True)
async def test_spell_simulate_string_target(spell, bob, avrae):
    automation = get_spell_automation(spell)
    await run_automation(automation, avrae, caster=bob, targets=["foobar"])


@pytest.mark.asyncio
@pytest.mark.simulation
@requires_data(fail_if_no_data=True)
async def test_spell_simulate_statblock_targets(spell, ara, bob, avrae):
    automation = get_spell_automation(spell)
    await run_automation(automation, avrae, caster=bob, targets=[ara, bob])


@pytest.mark.asyncio
@pytest.mark.simulation
@requires_data(fail_if_no_data=True)
async def test_spell_simulate_player_caster(spell, ara, bob, avrae):
    automation = get_spell_automation(spell)
    await run_automation(automation, avrae, caster=ara, targets=[ara, bob])


@pytest.mark.asyncio
@pytest.mark.simulation
@requires_data(fail_if_no_data=True)
async def test_spell_simulate_monster_caster(spell, bob, avrae):
    automation = get_spell_automation(spell)
    mage = compendium.lookup_entity(Monster.entity_type, 16947)
    await run_automation(automation, avrae, caster=mage, targets=[mage, bob])


# --- in combat ---
@pytest.mark.asyncio
@pytest.mark.simulation
@requires_data(fail_if_no_data=True)
async def test_spell_simulate_combat_no_target(spell, ara, avrae, mock_combat):
    automation = get_spell_automation(spell)
    # --- player caster ---
    # caster not in combat
    await run_automation(automation, avrae, combat=mock_combat, caster=ara, targets=[])
    # caster in combat
    player = simulation_utils.create_player_combatant(mock_combat, avrae, ara)
    await run_automation(automation, avrae, combat=mock_combat, caster=player, targets=[])

    # --- monster caster ---
    # caster not in combat
    mage = compendium.lookup_entity(Monster.entity_type, 16947)
    await run_automation(automation, avrae, combat=mock_combat, caster=mage, targets=[])


@pytest.mark.asyncio
@pytest.mark.simulation
@requires_data(fail_if_no_data=True)
async def test_spell_simulate_combat_targets(spell, ara, avrae, mock_combat):
    automation = get_spell_automation(spell)
    mage = compendium.lookup_entity(Monster.entity_type, 16947)
    # add things to combat
    basic = simulation_utils.create_basic_combatant(mock_combat, avrae)
    monster = simulation_utils.create_monster_combatant_from_monster(mock_combat, avrae, mage)
    player = simulation_utils.create_player_combatant(mock_combat, avrae, ara)

    # player caster
    await run_automation(
        automation,
        avrae,
        combat=mock_combat,
        caster=player,
        targets=[basic, monster, player],
    )

    # monster caster
    await run_automation(
        automation,
        avrae,
        combat=mock_combat,
        caster=monster,
        targets=[basic, monster, player],
    )
