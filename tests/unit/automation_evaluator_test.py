from types import SimpleNamespace

import disnake
import pytest
from aliasing.api import automation as automation_api
from aliasing.evaluators import AutomationEvaluator
from cogs5e import initiative as init
from cogs5e.initiative.combatant import Combatant, MonsterCombatant, PlayerCombatant
from cogs5e.initiative.utils import create_combatant_id
from cogs5e.models.automation.effects.castspell import CastSpell
from cogs5e.models.automation.runtime import AutomationContext
from cogs5e.models.sheet.spellcasting import Spellbook
from cogs5e.models.sheet.statblock import StatBlock
from tests.discord_mock_data import DEFAULT_USER_ID
from tests.utils import ContextBotProxy
from utils.argparser import argparse


pytestmark = pytest.mark.asyncio


def _create_basic_combatant(combat, avrae, name="Basic Combatant"):
    combatant = Combatant(
        id=create_combatant_id(),
        name=name,
        controller_id=int(DEFAULT_USER_ID),
        init=1,
        private=False,
        ctx=ContextBotProxy(avrae),
        combat=combat,
    )
    combat.add_combatant(combatant)
    return combatant


def _create_monster_combatant(combat, avrae, name="Monster Combatant"):
    combatant = MonsterCombatant(
        id=create_combatant_id(),
        name=name,
        controller_id=int(DEFAULT_USER_ID),
        init=0,
        private=False,
        ctx=ContextBotProxy(avrae),
        combat=combat,
        monster_name="Training Dummy",
        monster_id=42,
    )
    combat.add_combatant(combatant)
    return combatant


def _create_player_combatant(combat, avrae, character):
    combatant = PlayerCombatant.from_character(
        character,
        ctx=ContextBotProxy(avrae),
        combat=combat,
        controller_id=int(DEFAULT_USER_ID),
        init=2,
        private=False,
    )
    combat.add_combatant(combatant)
    return combatant


async def test_wrap_statblock_returns_expected_wrapper_types(mock_combat, avrae, ara):
    basic = _create_basic_combatant(mock_combat, avrae)
    monster = _create_monster_combatant(mock_combat, avrae)
    player = _create_player_combatant(mock_combat, avrae, ara)
    plain = StatBlock("Plain", spellbook=Spellbook())

    assert isinstance(automation_api.wrap_statblock(plain), automation_api.AutomationStatBlock)
    assert isinstance(automation_api.wrap_statblock(ara), automation_api.AutomationCharacter)
    assert isinstance(automation_api.wrap_statblock(player), automation_api.AutomationCharacter)
    assert isinstance(automation_api.wrap_statblock(basic), automation_api.AutomationCombatant)
    assert isinstance(automation_api.wrap_statblock(monster), automation_api.AutomationCombatant)


async def test_standalone_character_has_inert_combat_fields(ara):
    wrapped = automation_api.wrap_statblock(ara)

    assert isinstance(wrapped, automation_api.AutomationCharacter)
    assert wrapped.id is None
    assert wrapped.note is None
    assert wrapped.controller is None
    assert wrapped.group is None
    assert wrapped.is_hidden is False
    assert wrapped.effects == []
    assert wrapped.get_effect("missing") is None
    assert wrapped.monster_name is None
    assert wrapped.monster_id is None


async def test_automation_context_wraps_runtime_vars_and_preserves_simple_targets(mock_combat, avrae, ara):
    basic = _create_basic_combatant(mock_combat, avrae)
    effect = init.InitiativeEffect.new(combat=mock_combat, combatant=basic, name="Wrapped", effect_args="")
    autoctx = AutomationContext(
        ctx=ContextBotProxy(avrae),
        embed=disnake.Embed(),
        caster=ara,
        targets=[basic, "Named Target", None],
        args=argparse(""),
        combat=mock_combat,
        ieffect=effect,
    )

    assert isinstance(autoctx.metavars["caster"], automation_api.AutomationCharacter)
    assert isinstance(autoctx.metavars["targets"][0], automation_api.AutomationCombatant)
    assert isinstance(autoctx.metavars["targets"][1], automation_api.AutomationStatBlock)
    assert autoctx.metavars["targets"][1].name == "Named Target"
    assert isinstance(autoctx.metavars["targets"][2], automation_api.AutomationStatBlock)
    assert autoctx.metavars["targets"][2].name == "Target"
    assert isinstance(autoctx.metavars["ieffect"], automation_api.AutomationEffect)


async def test_wrap_target_creates_placeholder_statblocks():
    named = automation_api.wrap_target("Named Target")
    missing = automation_api.wrap_target(None)

    assert isinstance(named, automation_api.AutomationStatBlock)
    assert named.name == "Named Target"
    assert isinstance(missing, automation_api.AutomationStatBlock)
    assert missing.name == "Target"


async def test_combat_helper_returns_wrapped_objects(mock_combat, avrae, ara):
    basic = _create_basic_combatant(mock_combat, avrae)
    player = _create_player_combatant(mock_combat, avrae, ara)
    mock_combat._current_index = 0
    autoctx = AutomationContext(
        ctx=ContextBotProxy(avrae),
        embed=disnake.Embed(),
        caster=player,
        targets=[basic],
        args=argparse(""),
        combat=mock_combat,
    )

    combat = autoctx.evaluator.eval("combat()")

    assert isinstance(combat, automation_api.AutomationCombat)
    looked_up = autoctx.evaluator.eval(f"combat().get_combatant({basic.name!r})")
    assert isinstance(looked_up, automation_api.AutomationCombatant)
    assert looked_up.name == basic.name


async def test_wrappers_do_not_expose_mutators(mock_combat, avrae, ara):
    basic = _create_basic_combatant(mock_combat, avrae)
    player = _create_player_combatant(mock_combat, avrae, ara)
    autoctx = AutomationContext(
        ctx=ContextBotProxy(avrae),
        embed=disnake.Embed(),
        caster=player,
        targets=[basic],
        args=argparse(""),
        combat=mock_combat,
    )
    wrapped_caster = autoctx.metavars["caster"]
    wrapped_combat = autoctx.evaluator.eval("combat()")

    assert not hasattr(wrapped_caster, "set_hp")
    assert not hasattr(wrapped_caster, "modify_hp")
    assert not hasattr(wrapped_caster.spellbook, "set_slots")
    assert not hasattr(wrapped_combat, "set_metadata")
    assert not hasattr(wrapped_combat, "set_round")


async def test_runtime_vars_override_scope_locals(avrae, monkeypatch):
    caster = StatBlock("Caster", spellbook=Spellbook(dc=13, sab=5, spell_mod=3))
    original_get_scope_locals = caster.get_scope_locals
    monkeypatch.setattr(
        caster,
        "get_scope_locals",
        lambda: {
            **original_get_scope_locals(),
            "caster": "cvar caster",
            "choice": "cvar choice",
            "target": "cvar target",
        },
    )
    autoctx = AutomationContext(
        ctx=ContextBotProxy(avrae),
        embed=disnake.Embed(),
        caster=caster,
        targets=[],
        args=argparse("-choice Runtime"),
        combat=None,
        spell_override=7,
    )
    autoctx.metavars["target"] = "runtime target"

    assert autoctx.parse_annostr("{{caster}}", is_full_expression=True) is autoctx.metavars["caster"]
    assert autoctx.parse_annostr("{{choice}}", is_full_expression=True) == "runtime"
    assert autoctx.parse_annostr("{{target}}", is_full_expression=True) == "runtime target"
    assert autoctx.parse_annostr("{{spell}}", is_full_expression=True) == 7


async def test_cast_spell_accepts_automation_effect_as_parent(mock_combat, avrae, ara, monkeypatch):
    observed = {}

    class EmptyEffect:
        type = "empty"

        def run(self, autoctx):
            observed["spell"] = autoctx.parse_annostr("{{spell}}", is_full_expression=True)
            return None

    combatant = _create_basic_combatant(mock_combat, avrae)
    parent_effect = init.InitiativeEffect.new(combat=mock_combat, combatant=combatant, name="Parent", effect_args="")
    autoctx = AutomationContext(
        ctx=ContextBotProxy(avrae),
        embed=disnake.Embed(),
        caster=ara,
        targets=[],
        args=argparse(""),
        combat=mock_combat,
        ieffect=parent_effect,
    )
    spell = SimpleNamespace(
        level=1,
        range="Self",
        higherlevels=None,
        automation=SimpleNamespace(effects=[EmptyEffect()]),
    )
    monkeypatch.setattr(
        "cogs5e.models.automation.effects.castspell.gamedata.compendium.lookup_entity",
        lambda *_: spell,
    )

    CastSpell(id=1, parent="ieffect", castingMod=8).run(autoctx)

    assert autoctx.conc_effect is parent_effect
    assert observed["spell"] == 8
