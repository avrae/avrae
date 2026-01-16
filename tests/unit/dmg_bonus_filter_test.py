"""Unit tests for passive_effects damage_bonus filtering by sign."""

from cogs5e.models.automation.utils import filter_dmg_bonuses


def test_damage_gets_positive_bonus():
    result = filter_dmg_bonuses("1d8 [fire]", ["2 [fire]"])
    assert result == ["2 [fire]"]


def test_damage_skips_negative_bonus():
    result = filter_dmg_bonuses("1d8 [fire]", ["-2"])
    assert result == []


def test_healing_gets_negative_bonus():
    result = filter_dmg_bonuses("-1d8 [healing]", ["-2"])
    assert result == ["-2"]


def test_healing_skips_positive_bonus():
    result = filter_dmg_bonuses("-1d8 [healing]", ["2 [fire]"])
    assert result == []


def test_damage_filters_mixed():
    result = filter_dmg_bonuses("1d8", ["2", "-3", "1d4", "-1d6"])
    assert result == ["2", "1d4"]


def test_healing_filters_mixed():
    result = filter_dmg_bonuses("-1d8", ["2", "-3", "1d4", "-1d6"])
    assert result == ["-3", "-1d6"]


def test_empty_bonuses():
    assert filter_dmg_bonuses("1d8", []) == []
    assert filter_dmg_bonuses("-1d8", []) == []


def test_whitespace_handling():
    assert filter_dmg_bonuses("  -1d8", ["-2"]) == ["-2"]
    assert filter_dmg_bonuses("-1d8", ["  -2"]) == ["  -2"]
