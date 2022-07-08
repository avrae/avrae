import json
import logging

import disnake

from cogs5e.initiative.combatant import Combatant, MonsterCombatant, PlayerCombatant
from cogs5e.initiative.utils import create_combatant_id
from cogs5e.models.automation import EffectResult, IEffectResult
from gamedata import Monster, Spell, compendium
from tests.discord_mock_data import DEFAULT_USER_ID
from tests.utils import ContextBotProxy, requires_data
from utils.argparser import argparse

log = logging.getLogger(__name__)


async def run_automation(automation, avrae, combat=None, targets=None, **kwargs):
    """
    Runs the given automation and runs basic assertions on its results.

    If *combat* is given and the automation returns ieffects granting attacks or buttons, those will be tested
    recursively.
    """
    if targets is None:
        targets = []

    default_kwargs = dict(
        ctx=ContextBotProxy(avrae), embed=disnake.Embed(), args=argparse(""), combat=combat, targets=targets
    )
    result = await automation.run(**{**default_kwargs, **kwargs})
    result_dict = result.to_dict()  # AutomationResult must be dict-serializable
    assert json.dumps(result_dict)  # and JSON-serializable

    log.info("Completed root automation")

    async def _recurse_results(result: EffectResult):
        """Recurse over an automation result, and run granted buttons and attacks"""
        for node in result:
            if isinstance(node, IEffectResult) and node.effect.combatant is not None:
                log.info(f"Found IEffect with combatant: {node.effect.name} on {node.effect.combatant.name}")
                for attack_interaction in node.effect.attacks:
                    # simulate running the attack against the same targets
                    attack = attack_interaction.attack
                    log.info(f"Simulating granted action: {attack.name}")
                    await run_automation(
                        attack.automation,
                        avrae,
                        combat=combat,
                        caster=node.effect.combatant,
                        targets=targets,
                        **attack.__run_automation_kwargs__,
                    )
                    log.info(f"Finished simulating granted action: {attack.name}")
                for button in node.effect.buttons:
                    # simulate clicking the button
                    # this is pretty much just copied from cogs5e.initiative.buttons
                    log.info(f"Simulating granted button: {button.label}")
                    if button.granting_spell_id is not None:
                        spell = compendium.lookup_entity(Spell.entity_type, button.granting_spell_id)
                    else:
                        spell = None
                    await run_automation(
                        button.automation,
                        avrae,
                        combat=combat,
                        caster=node.effect.combatant,
                        targets=[],
                        ieffect=node.effect,
                        allow_caster_ieffects=False,
                        # do not allow things like damage-boosting effects to affect dot ticks
                        ab_override=button.override_default_attack_bonus,
                        dc_override=button.override_default_dc,
                        spell_override=button.override_default_casting_mod,
                        spell=spell,
                        spell_level_override=button.granting_spell_cast_level,
                        from_button=True,
                    )
                    log.info(f"Finished simulating granted button: {button.label}")
                log.info(f"Finished IEffect on combatant: {node.effect.name} on {node.effect.combatant.name}")
            await _recurse_results(node)

    if combat is not None:
        await _recurse_results(result)


def create_basic_combatant(combat, avrae):
    """Creates a new minimal basic combatant, adds it to the combat, and returns it"""
    basic_combatant = Combatant(
        id=create_combatant_id(),
        name="Test Combatant",
        controller_id=int(DEFAULT_USER_ID),
        init=0,
        private=False,
        ctx=ContextBotProxy(avrae),
        combat=combat,
    )
    combat.add_combatant(basic_combatant)
    return basic_combatant


@requires_data(fail_if_no_data=True)
def create_monster_combatant(combat, avrae, monster_id=16939):
    """Creates a new monster combatant, adds it to the combat, and returns it. Defaults to using a kobold"""
    mon = compendium.lookup_entity(Monster.entity_type, monster_id)
    return create_monster_combatant_from_monster(combat, avrae, mon)


def create_monster_combatant_from_monster(combat, avrae, monster):
    monster_combatant = MonsterCombatant.from_monster(
        monster,
        ctx=ContextBotProxy(avrae),
        combat=combat,
        name="Test Monster",
        controller_id=int(DEFAULT_USER_ID),
        init=0,
        private=False,
    )
    combat.add_combatant(monster_combatant)
    return monster_combatant


def create_player_combatant(combat, avrae, character):
    """Creates a new player combatant from the given character and adds and returns it"""
    player_combatant = PlayerCombatant.from_character(
        character,
        ctx=ContextBotProxy(avrae),
        combat=combat,
        controller_id=int(DEFAULT_USER_ID),
        init=0,
        private=False,
    )
    combat.add_combatant(player_combatant)
    return player_combatant
