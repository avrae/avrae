"""
Unit tests to test initiative name builders (in combatant_builders).
"""

import d20
import pytest

from cogs5e.initiative.combatant_builders import CombatantNameBuilder, resolve_n_arg
from cogs5e.models.errors import InvalidArgument


def test_n_arg():
    assert resolve_n_arg("1") == (1, None)
    assert resolve_n_arg("0") == (1, None)
    assert resolve_n_arg("26") == (25, None)
    assert resolve_n_arg(None) == (1, None)

    for _ in range(20):
        n, msg = resolve_n_arg("1d6")
        assert 1 <= n <= 6
        assert msg

    with pytest.raises(d20.RollError):
        resolve_n_arg("foobar")


# ==== namebuilder ====
class _MockCombat:
    @staticmethod
    def get_combatant(name, *_, **__):
        if name in ("one", "one1"):
            return True
        if name.startswith("always"):
            return True
        return False


def test_namebuilder_basic():
    builder = CombatantNameBuilder("foo", _MockCombat(), always_number_first_name=False)
    assert builder.next() == "foo"
    assert builder.next() == "foo2"
    assert builder.next() == "foo3"

    builder = CombatantNameBuilder("foo#", _MockCombat(), always_number_first_name=False)
    assert builder.next() == "foo1"
    assert builder.next() == "foo2"
    assert builder.next() == "foo3"

    builder = CombatantNameBuilder("one", _MockCombat(), always_number_first_name=False)
    with pytest.raises(InvalidArgument):
        builder.next()

    builder = CombatantNameBuilder("one#", _MockCombat(), always_number_first_name=False)
    assert builder.next() == "one2"
    assert builder.next() == "one3"

    builder = CombatantNameBuilder("always", _MockCombat(), always_number_first_name=False)
    with pytest.raises(InvalidArgument):
        builder.next()

    builder = CombatantNameBuilder("always#", _MockCombat(), always_number_first_name=False)
    with pytest.raises(InvalidArgument):
        builder.next()


def test_namebuilder_always_number_first():
    builder = CombatantNameBuilder("foo", _MockCombat(), always_number_first_name=True)
    builder2 = CombatantNameBuilder("foo#", _MockCombat(), always_number_first_name=True)
    assert builder.next() == builder2.next() == "foo1"
    assert builder.next() == builder2.next() == "foo2"
    assert builder.next() == builder2.next() == "foo3"

    builder = CombatantNameBuilder("one", _MockCombat(), always_number_first_name=True)
    builder2 = CombatantNameBuilder("one#", _MockCombat(), always_number_first_name=True)
    assert builder.next() == builder2.next() == "one2"
    assert builder.next() == builder2.next() == "one3"

    builder = CombatantNameBuilder("always", _MockCombat(), always_number_first_name=True)
    with pytest.raises(InvalidArgument):
        builder.next()

    builder = CombatantNameBuilder("always#", _MockCombat(), always_number_first_name=True)
    with pytest.raises(InvalidArgument):
        builder.next()
