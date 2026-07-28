"""Unit tests for passive_effects damage_bonus filtering by type."""

from cogs5e.models.automation.utils import filter_dmg_bonuses


# damage rolls get non-heal bonuses
def test_damage_gets_non_heal_bonus():
    assert filter_dmg_bonuses("1d8 [fire]", ["2 [fire]"]) == ["2 [fire]"]
    assert filter_dmg_bonuses("1d8", ["-2"]) == ["-2"]  # damage penalty works


def test_damage_skips_heal_bonus():
    assert filter_dmg_bonuses("1d8 [fire]", ["2 [healing]"]) == []
    assert filter_dmg_bonuses("1d8", ["-2 [heal]"]) == []


# healing rolls get heal bonuses only
def test_healing_gets_heal_bonus():
    assert filter_dmg_bonuses("-1d8 [healing]", ["-2 [healing]"]) == ["-2 [healing]"]
    assert filter_dmg_bonuses("-1d8", ["-2 [heal]"]) == ["-2 [heal]"]
    assert filter_dmg_bonuses("-1d8", ["-3 [magical healing]"]) == ["-3 [magical healing]"]


def test_healing_skips_non_heal_bonus():
    assert filter_dmg_bonuses("-1d8 [healing]", ["2 [fire]"]) == []
    assert filter_dmg_bonuses("-1d8", ["-2"]) == []  # no heal type = skipped


# mixed bonuses
def test_damage_filters_mixed():
    result = filter_dmg_bonuses("1d8", ["2 [fire]", "-3 [healing]", "1d4", "-1d6 [heal]"])
    assert result == ["2 [fire]", "1d4"]


def test_healing_filters_mixed():
    result = filter_dmg_bonuses("-1d8", ["2 [fire]", "-3 [healing]", "1d4", "-1d6 [heal]"])
    assert result == ["-3 [healing]", "-1d6 [heal]"]


# edge cases
def test_empty_bonuses():
    assert filter_dmg_bonuses("1d8", []) == []
    assert filter_dmg_bonuses("-1d8", []) == []


def test_whitespace_handling():
    assert filter_dmg_bonuses("  -1d8", ["-2 [healing]"]) == ["-2 [healing]"]
    assert filter_dmg_bonuses("-1d8", ["  -2 [heal]"]) == ["  -2 [heal]"]
