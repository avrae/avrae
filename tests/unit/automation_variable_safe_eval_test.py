from types import SimpleNamespace
from unittest.mock import Mock

from cogs5e.models.automation.effects.variable import SetVariable


def _mock_caster():
    return SimpleNamespace(
        name="Caster",
        attacks=[SimpleNamespace(name="Magic Stone"), SimpleNamespace(name="Unarmed Strike")],
    )


def test_build_str_uses_safe_eval_for_caster_attacks(monkeypatch):
    effect = SetVariable(name="test", value="'Magic Stone' in str(caster.attacks)")
    evaluator = Mock()
    evaluator.builtins = {}
    caster = _mock_caster()

    safe_eval_called = {"called": False}

    def _safe_eval(expr, names, timeout):
        safe_eval_called["called"] = True
        assert expr == "'Magic Stone' in str(caster.attacks)"
        assert names["caster"].name == "Caster"
        assert names["caster"].attacks == ["Magic Stone", "Unarmed Strike"]
        assert timeout > 0
        return 1

    monkeypatch.setattr("cogs5e.models.automation.effects.variable.safe_eval.eval_expr", _safe_eval)

    effect.build_str(caster, evaluator)

    assert safe_eval_called["called"]
    evaluator.eval.assert_not_called()
    assert evaluator.builtins["test"] == 1


def test_build_str_uses_on_error_when_safe_eval_fails(monkeypatch):
    effect = SetVariable(name="test", value="'Magic Stone' in str(caster.attacks)", onError="0")
    evaluator = Mock()
    evaluator.builtins = {}
    caster = _mock_caster()

    calls = {"count": 0}

    def _safe_eval(expr, names, timeout):
        calls["count"] += 1
        if expr == "'Magic Stone' in str(caster.attacks)":
            raise RuntimeError("timeout-like failure")
        if expr == "0":
            return 0
        raise AssertionError(f"Unexpected expression: {expr}")

    monkeypatch.setattr("cogs5e.models.automation.effects.variable.safe_eval.eval_expr", _safe_eval)

    effect.build_str(caster, evaluator)

    assert calls["count"] == 2
    evaluator.eval.assert_not_called()
    assert evaluator.builtins["test"] == 0


def test_build_str_non_caster_attacks_keeps_legacy_eval():
    effect = SetVariable(name="test", value="1+1")
    evaluator = Mock()
    evaluator.builtins = {}
    evaluator.eval.return_value = 2
    caster = _mock_caster()

    effect.build_str(caster, evaluator)

    evaluator.eval.assert_called_once_with("1+1")
    assert evaluator.builtins["test"] == 2
