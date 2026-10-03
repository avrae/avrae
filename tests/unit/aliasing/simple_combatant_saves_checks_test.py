"""Tests for the SimpleCombatant save/check helpers."""

from unittest.mock import MagicMock

import pytest

from aliasing.api.combat import InvalidSaveType, SimpleCombatant
from cogs5e.initiative.effects.passive import InitPassiveEffect
from cogs5e.models.sheet.base import BaseStats, Saves, Skills


@pytest.fixture
def simple_combatant():
    combatant = MagicMock()
    stats = BaseStats(
        prof_bonus=2,
        strength=14,
        dexterity=16,
        constitution=12,
        intelligence=10,
        wisdom=14,
        charisma=8,
    )
    combatant.saves = Saves.default(stats)
    combatant.skills = Skills.default(stats)
    combatant.character = None
    effects = []

    def active_effects(mapper, reducer=lambda values: values, default=None):
        values = [value for effect in effects if (value := mapper(effect))]
        return reducer(values) if values else default

    def set_effects(*effect_defs):
        effects[:] = [MagicMock(effects=InitPassiveEffect(**effect)) for effect in effect_defs]

    combatant.active_effects.side_effect = active_effects

    simple = object.__new__(SimpleCombatant)
    simple._combatant = combatant
    simple._hidden = False
    simple._interpreter = MagicMock()
    return simple, combatant, set_effects


def test_skills_get_exact_progressive_and_invalid(simple_combatant):
    skills = simple_combatant[0]._combatant.skills

    assert skills.get("perception", return_name=True)[1] == "perception"
    assert skills.get("perc", return_name=True)[1] == "perception"
    assert skills.get("ste", return_name=True)[1] == "stealth"
    with pytest.raises(ValueError):
        skills.get("in")


def test_save_flags_are_independent_and_preserve_save_bonus(simple_combatant):
    simple, combatant, set_effects = simple_combatant
    set_effects({"save_bonus": "1|dex"}, {"save_adv": {"dex"}}, {"dc_bonus": 2})
    character = MagicMock()
    character.options.reroll = 1
    combatant.character = character

    default = simple.save("dex")
    ieffects = simple.save("dex", include_ieffects=True)
    csettings = simple.save("dex", include_csettings=True)
    both = simple.save("dex", include_ieffects=True, include_csettings=True)

    assert "1d20" in default.full and " + 1" in default.full
    assert "kh1" not in default.full and "-2" not in default.full and "ro1" not in default.full
    assert "kh1" in ieffects.full and "-2" in ieffects.full and "ro1" not in ieffects.full
    assert "ro1" in csettings.full and "kh1" not in csettings.full and "-2" not in csettings.full
    assert "kh1" in both.full and "-2" in both.full and "ro1" in both.full


def test_save_explicit_advantage_overrides_ieffect(simple_combatant):
    simple, _, set_effects = simple_combatant
    set_effects({"save_adv": {"dex"}})

    result = simple.save("dex", adv=False, include_ieffects=True)

    assert "2d20" in result.full and "kl1" in result.full
    assert "kh1" not in result.full


def test_check_flags_are_independent(simple_combatant):
    simple, combatant, set_effects = simple_combatant
    set_effects({"check_adv": {"perception"}}, {"check_bonus": "1d4"})
    combatant.skills.skills["perception"].prof = 1
    character = MagicMock()
    character.options.reroll = 1
    character.options.talent = True
    combatant.character = character

    default = simple.check("perception")
    ieffects = simple.check("perception", include_ieffects=True)
    csettings = simple.check("perception", include_csettings=True)
    both = simple.check("perception", include_ieffects=True, include_csettings=True)

    assert "1d20" in default.full and "kh1" not in default.full
    assert "1d4" not in default.full and "ro1" not in default.full and "mi10" not in default.full
    assert "kh1" in ieffects.full and "1d4" in ieffects.full
    assert "ro1" not in ieffects.full and "mi10" not in ieffects.full
    assert "ro1" in csettings.full and "mi10" in csettings.full
    assert "kh1" not in csettings.full and "1d4" not in csettings.full
    assert "kh1" in both.full and "1d4" in both.full and "ro1" in both.full and "mi10" in both.full


def test_check_ieffect_matches_base_ability(simple_combatant):
    simple, _, set_effects = simple_combatant
    set_effects({"check_adv": {"wisdom"}})

    perception = simple.check("perception", include_ieffects=True)
    stealth = simple.check("stealth", include_ieffects=True)

    assert "kh1" in perception.full
    assert "kh1" not in stealth.full


def test_invalid_save_and_check_raise(simple_combatant):
    simple, combatant, _ = simple_combatant
    combatant.saves.get = MagicMock(side_effect=ValueError)
    with pytest.raises(InvalidSaveType):
        simple.save("not-a-save")

    combatant.skills.get = MagicMock(side_effect=ValueError)
    with pytest.raises(ValueError):
        simple.check("not-a-skill")
