import pytest

from aliasing.evaluators import SpellEvaluator
from cogs5e.models import automation
from cogs5e.models.sheet.statblock import StatBlock

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
    assert attack.build_str(DEFAULT_CASTER, DEFAULT_EVALUATOR)


@pytest.mark.parametrize("dc", [
    # valid inputs
    "12", "dexterityMod", "{dexterityMod}", "8 + dexterityMod + proficiencyBonus",
    "{8 + dexterityMod + proficiencyBonus}",
    # inputs that should be NaN
    "foobar", "{}", "dexterymod", "RogueLevel"
])
def test_save_strs(dc):
    save = automation.Save(stat='str', fail=[], success=[], dc=dc)
    assert save.build_str(DEFAULT_CASTER, DEFAULT_EVALUATOR)
