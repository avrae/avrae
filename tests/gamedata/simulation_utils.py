import json

import disnake

from cogs5e.initiative.combatant import Combatant, MonsterCombatant, PlayerCombatant
from cogs5e.models.sheet.base import Skill
from cogs5e.models.sheet.resistance import Resistances
from gamedata import Monster, compendium
from tests.discord_mock_data import DEFAULT_USER_ID
from tests.utils import ContextBotProxy, requires_data
from utils.argparser import argparse


async def run_automation(automation, avrae, combat=None, **kwargs):
    """Wrapper function to help supply some defaults"""

    default_kwargs = dict(ctx=ContextBotProxy(avrae), embed=disnake.Embed(), args=argparse(""), combat=combat)
    result = await automation.run(**{**default_kwargs, **kwargs})
    result_dict = result.to_dict()  # AutomationResult must be dict-serializable
    assert json.dumps(result_dict)  # and JSON-serializable
    return result


def create_basic_combatant(combat, avrae):
    """Creates a new basic combatant, adds it to the combat, and returns it"""
    basic_combatant = Combatant.new(
        name="Test Combatant",
        controller_id=int(DEFAULT_USER_ID),
        init=0,
        init_skill=Skill(0),
        max_hp=10,
        ac=10,
        private=False,
        resists=Resistances(),
        ctx=ContextBotProxy(avrae),
        combat=combat,
    )
    combat.add_combatant(basic_combatant)
    return basic_combatant


@requires_data(fail_if_no_data=True)
def create_monster_combatant(combat, avrae, monster_id=16939):
    """Creates a new monster combatant, adds it to the combat, and returns it. Defaults to using a kobold"""
    mon = compendium.lookup_entity(Monster.entity_type, monster_id)
    monster_combatant = MonsterCombatant.from_monster(
        mon,
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
