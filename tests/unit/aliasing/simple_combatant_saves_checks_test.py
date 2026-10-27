"""
Tests for SimpleCombatant.save(), SimpleCombatant.check(), and Skills.get() progressive matching.
"""

from unittest.mock import MagicMock

import d20
import pytest

from aliasing.api.combat import SimpleCombatant, InvalidSaveType
from cogs5e.models.sheet.base import Skills, Saves, BaseStats
from cogs5e.initiative.effects.passive import InitPassiveEffect


# =============================================================================
# Skills.get() Progressive Unique Matching Tests
# =============================================================================
class TestSkillsProgressiveMatching:
    """Test the progressive unique matching in Skills.get()"""

    @pytest.fixture
    def skills(self):
        return Skills.default()

    def test_exact_and_progressive_partial_match(self, skills):
        assert skills.get("perception", return_name=True)[1] == "perception"
        assert skills.get("perc", return_name=True)[1] == "perception"
        assert skills.get("ste", return_name=True)[1] == "stealth"
        assert skills.get("pers", return_name=True)[1] == "persuasion"
        assert skills.get("ani", return_name=True)[1] == "animalHandling"

    def test_invalid_or_ambiguous_raises_error(self, skills):
        with pytest.raises(ValueError):
            skills.get("xyz")
        with pytest.raises(ValueError):
            skills.get("in")


# =============================================================================
# SimpleCombatant.save() Tests
# =============================================================================
class TestSimpleCombatantSave:
    """Test SimpleCombatant.save() with effects and csettings."""

    @pytest.fixture
    def mock_combatant(self):
        combatant = MagicMock()
        base_stats = BaseStats(
            prof_bonus=2, strength=14, dexterity=16, constitution=12, intelligence=10, wisdom=8, charisma=14
        )
        combatant.saves = Saves.default(base_stats)
        combatant.active_effects.side_effect = lambda mapper, reducer=None, default=None: default
        combatant.character = None
        return combatant

    @pytest.fixture
    def simple_combatant(self, mock_combatant):
        sc = object.__new__(SimpleCombatant)
        sc._combatant = mock_combatant
        sc._hidden = False
        sc._interpreter = MagicMock()
        return sc

    @pytest.fixture
    def effect_factory(self, mock_combatant):
        """Factory for creating effect mocks with various passive effects."""

        def _create(*effect_defs):
            def side_effect(mapper, reducer=None, default=None):
                results = []
                for attr_name, attr_value, expected in effect_defs:
                    effect = MagicMock()
                    effect.effects = InitPassiveEffect(**{attr_name: attr_value})
                    result = mapper(effect)
                    if result == expected:
                        results.append(result)
                if results:
                    return reducer(results) if reducer else results
                return default

            mock_combatant.active_effects.side_effect = side_effect

        return _create

    def test_basic_save(self, simple_combatant):
        result = simple_combatant.save("dex")
        assert "1d20" in result.full
        assert "+ 3" in result.full

    @pytest.mark.parametrize(
        "bonus, expected",
        [(None, 0), ("", 0), ("2", 2), ("1d1", 1), ("-1d1", -1), ("1d1[bless]+2", 3), ("2*(1+1)", 4)],
    )
    def test_bonus_adds_to_generated_roll(self, simple_combatant, bonus, expected):
        result = simple_combatant.save("dex", args=f'-b "{bonus}"' if bonus else bonus)
        d20_value = d20.utils.leftmost(result.raw).total
        assert result.total == d20_value + 3 + expected
        assert result.full == f"{result.dice} = `{result.total}`"

    @pytest.mark.parametrize(
        "bonus, annotations",
        [
            ("1d4 [bless]", ["[bless]"]),
            ("1d4 [bless bonus] + 2 [inspiration]", ["[bless bonus]", "[inspiration]"]),
            ("1d4 [^bless]", ["[^bless]"]),
        ],
    )
    def test_bonus_preserves_annotations(self, simple_combatant, bonus, annotations):
        result = simple_combatant.save("dex", args=f'-b "{bonus}"')
        for annotation in annotations:
            assert annotation in result.full
            assert annotation in result.dice

    @pytest.mark.parametrize(
        "bonus, expected, comment",
        [
            ("1d1 ^[bless]", 1, "^[bless]"),
            ("1d1 [bless] ^[extra comment]", 1, "^[extra comment]"),
            ("2*(1+1) custom bonus", 4, "custom bonus"),
            ("1d1 bonus + 20", 1, "bonus + 20"),
        ],
    )
    def test_bonus_preserves_comments(self, simple_combatant, bonus, expected, comment):
        result = simple_combatant.save("dex", args=f'-b "{bonus}"')
        assert result.result.comment == comment
        assert result.full == f"{result.dice} = `{result.total}`"
        assert str(result.result) == result.full
        d20_value = d20.utils.leftmost(result.raw).total
        assert result.total == d20_value + 3 + expected

    def test_bonus_with_effects_and_character_settings(self, simple_combatant, mock_combatant, effect_factory):
        effect_factory(("save_adv", {"dex"}, {"dex"}), ("save_bonus", "2", "2"))
        mock_combatant.character = MagicMock()
        mock_combatant.character.options.reroll = 1

        result = simple_combatant.save("dex", False, True, True, "-b 1d1")

        assert "ro1" in result.full and "kl1" in result.full
        d20_value = d20.utils.leftmost(result.raw).total
        assert result.total == d20_value + 3 + 2 + 1

    @pytest.mark.parametrize("bonus", ["not dice", "(1d4"])
    def test_invalid_bonus_raises_dice_error(self, simple_combatant, bonus):
        with pytest.raises(d20.RollSyntaxError):
            simple_combatant.save("dex", args=f'-b "{bonus}"')

    def test_effect_advantage_applied(self, simple_combatant, effect_factory):
        effect_factory(("save_adv", {"dex"}, {"dex"}))
        result = simple_combatant.save("dex", include_ieffects=True)
        assert "2d20" in result.full and "kh1" in result.full

    def test_user_override_beats_effect(self, simple_combatant, effect_factory):
        effect_factory(("save_adv", {"str"}, {"str"}))
        result = simple_combatant.save("str", adv=False, include_ieffects=True)
        assert "kl1" in result.full

    def test_dc_bonus_does_not_modify_save(self, simple_combatant, effect_factory):
        effect_factory(("dc_bonus", 5, 5))
        result = simple_combatant.save("str", include_ieffects=True)
        assert "+ -5" not in result.full

    def test_character_reroll_applied(self, simple_combatant, mock_combatant):
        """Halfling luck reroll from character settings."""
        mock_character = MagicMock()
        mock_character.options.reroll = 1
        mock_combatant.character = mock_character

        result = simple_combatant.save("dex", include_csettings=True)
        assert "ro1" in result.full

    def test_invalid_save_type(self, simple_combatant, mock_combatant):
        mock_combatant.saves.get = MagicMock(side_effect=ValueError())
        with pytest.raises(InvalidSaveType):
            simple_combatant.save("notasave")


# =============================================================================
# SimpleCombatant.check() Tests
# =============================================================================
class TestSimpleCombatantCheck:
    """Test SimpleCombatant.check() with effects and csettings."""

    @pytest.fixture
    def mock_combatant(self):
        combatant = MagicMock()
        base_stats = BaseStats(
            prof_bonus=2, strength=14, dexterity=16, constitution=12, intelligence=10, wisdom=14, charisma=8
        )
        combatant.skills = Skills.default(base_stats)
        combatant.active_effects.side_effect = lambda mapper, reducer=None, default=None: default
        combatant.character = None
        return combatant

    @pytest.fixture
    def simple_combatant(self, mock_combatant):
        sc = object.__new__(SimpleCombatant)
        sc._combatant = mock_combatant
        sc._hidden = False
        sc._interpreter = MagicMock()
        return sc

    @pytest.fixture
    def effect_factory(self, mock_combatant):
        """Factory for creating effect mocks with various passive effects."""

        def _create(*effect_defs):
            def side_effect(mapper, reducer=None, default=None):
                results = []
                for attr_name, attr_value, expected in effect_defs:
                    effect = MagicMock()
                    effect.effects = InitPassiveEffect(**{attr_name: attr_value})
                    result = mapper(effect)
                    if result == expected:
                        results.append(result)
                if results:
                    return reducer(results) if reducer else results
                return default

            mock_combatant.active_effects.side_effect = side_effect

        return _create

    def test_basic_check(self, simple_combatant):
        result = simple_combatant.check("perception")
        assert "1d20" in result.full
        assert "+ 2" in result.full

    @pytest.mark.parametrize(
        "bonus, expected",
        [(None, 0), ("", 0), ("2", 2), ("1d1", 1), ("-1d1", -1), ("1d1[guidance]+2", 3), ("2*(1+1)", 4)],
    )
    def test_bonus_adds_to_generated_roll(self, simple_combatant, bonus, expected):
        result = simple_combatant.check("perception", args=f'-b "{bonus}"' if bonus else bonus)
        d20_value = d20.utils.leftmost(result.raw).total
        assert result.total == d20_value + 2 + expected
        assert result.full == f"{result.dice} = `{result.total}`"

    @pytest.mark.parametrize(
        "bonus, annotations",
        [
            ("1d4 [bless]", ["[bless]"]),
            ("1d4 [bless bonus] + 2 [inspiration]", ["[bless bonus]", "[inspiration]"]),
            ("1d4 [^bless]", ["[^bless]"]),
        ],
    )
    def test_bonus_preserves_annotations(self, simple_combatant, bonus, annotations):
        result = simple_combatant.check("perception", args=f'-b "{bonus}"')
        for annotation in annotations:
            assert annotation in result.full
            assert annotation in result.dice

    @pytest.mark.parametrize(
        "bonus, expected, comment",
        [
            ("1d1 ^[bless]", 1, "^[bless]"),
            ("1d1 [bless] ^[extra comment]", 1, "^[extra comment]"),
            ("2*(1+1) custom bonus", 4, "custom bonus"),
            ("1d1 bonus + 20", 1, "bonus + 20"),
        ],
    )
    def test_bonus_preserves_comments(self, simple_combatant, bonus, expected, comment):
        result = simple_combatant.check("perception", args=f'-b "{bonus}"')
        assert result.result.comment == comment
        assert result.full == f"{result.dice} = `{result.total}`"
        assert str(result.result) == result.full
        d20_value = d20.utils.leftmost(result.raw).total
        assert result.total == d20_value + 2 + expected

    def test_bonus_with_effects_and_character_settings(self, simple_combatant, mock_combatant, effect_factory):
        effect_factory(("check_dis", {"perception"}, {"perception"}), ("check_bonus", "2", "2"))
        mock_combatant.character = MagicMock()
        mock_combatant.character.options.reroll = 1
        mock_combatant.character.options.talent = True
        mock_combatant.skills.skills["perception"].prof = 1

        result = simple_combatant.check("perception", True, True, True, "-b 1d1")

        assert "ro1" in result.full and "kh1" in result.full and "mi10" in result.full
        d20_value = d20.utils.leftmost(result.raw).total
        assert result.total == d20_value + 2 + 2 + 1

    @pytest.mark.parametrize("bonus", ["not dice", "(1d4"])
    def test_invalid_bonus_raises_dice_error(self, simple_combatant, bonus):
        with pytest.raises(d20.RollSyntaxError):
            simple_combatant.check("perception", args=f'-b "{bonus}"')

    def test_effect_advantage_skill_specific(self, simple_combatant, effect_factory):
        effect_factory(("check_adv", {"stealth"}, {"stealth"}))
        result = simple_combatant.check("stealth", include_ieffects=True)
        assert "2d20" in result.full and "kh1" in result.full

    def test_effect_advantage_base_ability(self, simple_combatant, effect_factory):
        """Check uses advantage from base ability effect (wisdom -> perception)."""
        effect_factory(("check_adv", {"wisdom"}, {"wisdom"}))

        perc = simple_combatant.check("perception", include_ieffects=True)
        assert "kh1" in perc.full

        stealth = simple_combatant.check("stealth", include_ieffects=True)
        assert "kh1" not in stealth.full

    def test_user_override_beats_effect(self, simple_combatant, effect_factory):
        effect_factory(("check_dis", {"stealth"}, {"stealth"}))
        result = simple_combatant.check("stealth", adv=True, include_ieffects=True)
        assert "kh1" in result.full

    def test_check_bonus_applied(self, simple_combatant, effect_factory):
        effect_factory(("check_bonus", "1d4", "1d4"))
        result = simple_combatant.check("arcana", include_ieffects=True)
        assert "1d4" in result.full

    def test_reliable_talent_requires_proficiency(self, simple_combatant, mock_combatant):
        """Reliable talent applies min 10 only for proficient skills."""
        mock_character = MagicMock()
        mock_character.options.reroll = None
        mock_character.options.talent = True
        mock_combatant.character = mock_character

        result = simple_combatant.check("perception", include_csettings=True)
        assert "mi10" not in result.full

        mock_combatant.skills.skills["perception"].prof = 1
        result = simple_combatant.check("perception", include_csettings=True)
        assert "mi10" in result.full

    def test_invalid_skill_raises_error(self, simple_combatant, mock_combatant):
        mock_combatant.skills.get = MagicMock(side_effect=ValueError())
        with pytest.raises(ValueError):
            simple_combatant.check("notaskill")
