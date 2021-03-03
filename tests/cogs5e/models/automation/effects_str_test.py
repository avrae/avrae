import logging

import pytest

from aliasing.evaluators import SpellEvaluator
from cogs5e.models import automation
from cogs5e.models.sheet.statblock import StatBlock

log = logging.getLogger(__name__)

DEFAULT_CASTER = StatBlock("Bob")
DEFAULT_EVALUATOR = SpellEvaluator.with_caster(DEFAULT_CASTER)


@pytest.mark.parametrize("attack_bonus", [
    # valid inputs
    "3", "dexterityMod", "{dexterityMod}", "dexterityMod + proficiencyBonus", "{dexterityMod + proficiencyBonus}",
    # inputs that should be NaN
    "foobar", "{}", "dexterymod", "RogueLevel"
])
def test_attack_strs(attack_bonus):
    attack = automation.Attack(hit=[], miss=[], attackBonus=attack_bonus)
    result = attack.build_str(DEFAULT_CASTER, DEFAULT_EVALUATOR)
    log.info(f"Attack str: ({attack_bonus=!r}) -> {result}")
    assert result


@pytest.mark.parametrize("dc", [
    # valid inputs
    "12", "dexterityMod", "{dexterityMod}", "8 + dexterityMod + proficiencyBonus",
    "{8 + dexterityMod + proficiencyBonus}",
    # inputs that should be NaN
    "foobar", "{}", "dexterymod", "RogueLevel"
])
def test_save_strs(dc):
    save = automation.Save(stat='str', fail=[], success=[], dc=dc)
    result = save.build_str(DEFAULT_CASTER, DEFAULT_EVALUATOR)
    log.info(f"Save str: ({dc=!r}) -> {result}")
    assert result


@pytest.mark.parametrize("counter", [
    # counters by name
    "counter", "other counter name",
    # spell slot
    automation.utils.SpellSlotReference(1), automation.utils.SpellSlotReference(9)
    # feature (todo)
])
@pytest.mark.parametrize("amount", [
    # valid inputs
    "1", "proficiencyBonus", "{proficiencyBonus}", "dexterityMod + proficiencyBonus",
    "{dexterityMod + proficiencyBonus}",
    # inputs that should be NaN
    "foobar", "{}", "dexterymod", "RogueLevel", "1d4"
])
def test_usecounter_strs(counter, amount):
    usecounter = automation.UseCounter(counter, amount)
    result = usecounter.build_str(DEFAULT_CASTER, DEFAULT_EVALUATOR)
    log.info(f"UseCounter str: ({counter=!r}, {amount=!r}) -> {result}")
    assert result
