import draconic
import pytest

from aliasing.evaluators import DisplayOnlyAutomationEvaluator
from cogs5e.models import automation
from cogs5e.models.sheet.attack import Attack, AttackList
from cogs5e.models.sheet.statblock import StatBlock
from utils import automation_display


def test_attack_display_guard_depth():
    assert automation_display.attack_display_depth() == 0
    with automation_display.attack_display_guard():
        assert automation_display.attack_display_depth() == 1
        with automation_display.attack_display_guard():
            assert automation_display.attack_display_depth() == 2
        assert automation_display.attack_display_depth() == 1
    assert automation_display.attack_display_depth() == 0


def test_attack_list_build_str_nested_returns_compact():
    inner = automation.Automation([automation.SetVariable(name="x", value="1")])
    outer = automation.Automation([automation.SetVariable(name="y", value="'a' in str(caster.attacks)")])
    attacks = AttackList([
        Attack("Zeta", inner),
        Attack("Alpha", outer),
    ])
    caster = StatBlock("Hero", attacks=attacks)
    out = attacks.build_str(caster)
    assert "**Alpha**" in out
    assert "**Zeta**" in out
    assert "variable" in out.lower()


def test_display_only_evaluator_removes_roll():
    class DummyCaster:
        name = "Bob"

        def get_scope_locals(self):
            return {}

    ev = DisplayOnlyAutomationEvaluator.with_caster(DummyCaster())
    assert "roll" not in ev.builtins
    assert "vroll" not in ev.builtins
    with pytest.raises(draconic.DraconicException):
        ev.eval("roll('1d20')")
