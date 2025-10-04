"""
Hidden Effects Tests
"""

import unittest

from cogs5e.initiative.effects.effect import InitiativeEffect


class TestHiddenEffects(unittest.TestCase):

    def test_hidden_effect_creation(self):
        """Test hidden=True creates hidden effect"""
        effect = InitiativeEffect.new(None, None, "Test Effect", hidden=True)
        self.assertTrue(effect.hidden)

    def test_visible_effect_creation_default(self):
        """Test hidden defaults to False"""
        effect = InitiativeEffect.new(None, None, "Test Effect")
        self.assertFalse(effect.hidden)

    def test_hidden_effect_serialization(self):
        """Test hidden field survives serialization roundtrip"""
        effect = InitiativeEffect.new(None, None, "Test Effect", hidden=True)
        data = effect.to_dict()
        restored = InitiativeEffect.from_dict(data, None, None)
        self.assertTrue(restored.hidden)

    def test_backwards_compatibility_serialization(self):
        """Test missing hidden field defaults to False"""
        effect = InitiativeEffect.new(None, None, "Test Effect", hidden=False)
        data = effect.to_dict()
        del data["hidden"]
        restored = InitiativeEffect.from_dict(data, None, None)
        self.assertFalse(restored.hidden)

    def test_hidden_effect_with_mechanical_effects(self):
        """Test hidden effect hides parenthetical mechanics from players"""
        from cogs5e.initiative.combatant import Combatant
        from unittest.mock import Mock

        effect = InitiativeEffect.new(None, None, "Buff", desc="Secret buff", effect_args="-ac 2", hidden=True)

        # Mock a combatant with the hidden effect
        combatant = Combatant(
            ctx=Mock(), combat=Mock(), id="test_id", name="Test", controller_id=12345, init=10, private=False, index=0
        )
        combatant._effects = [effect]
        effect.combatant = combatant

        # Player view should hide details
        player_display = combatant._get_long_effects(private=False)
        self.assertIn("Buff", player_display)
        self.assertNotIn("Secret buff", player_display)
        self.assertNotIn("AC", player_display)

    def test_hidden_effect_display_hidden(self):
        """Test hidden effect hides description and parenthetical"""
        from cogs5e.initiative.combatant import Combatant
        from unittest.mock import Mock

        effect = InitiativeEffect.new(
            None, None, "Secret Effect", desc="Secret description", duration=5, concentration=True, hidden=True
        )

        # Mock a combatant with the hidden effect
        combatant = Combatant(
            ctx=Mock(), combat=Mock(), id="test_id", name="Test", controller_id=12345, init=10, private=False, index=0
        )
        combatant._effects = [effect]
        effect.combatant = combatant

        # Player view should hide details
        player_display = combatant._get_long_effects(private=False)
        self.assertIn("Secret Effect", player_display)
        self.assertNotIn("Secret description", player_display)
        # For player view, concentration marker should still show since it's not parenthetical
        self.assertIn("<C>", player_display)

    def test_hidden_effect_with_duration_only(self):
        """Test hidden effect shows name only without combat context"""
        from cogs5e.initiative.combatant import Combatant
        from unittest.mock import Mock

        effect = InitiativeEffect.new(
            None, None, "Timed Effect", desc="Secret description", duration=3, concentration=False, hidden=True
        )

        # Mock a combatant with the hidden effect
        combatant = Combatant(
            ctx=Mock(), combat=Mock(), id="test_id", name="Test", controller_id=12345, init=10, private=False, index=0
        )
        combatant._effects = [effect]
        effect.combatant = combatant

        # Player view should show name only (no duration without combat context)
        player_display = combatant._get_long_effects(private=False)
        self.assertIn("Timed Effect", player_display)
        self.assertNotIn("Secret description", player_display)
        # Duration only shows with combat context
        self.assertNotIn("[3 rounds]", player_display)

    def test_hidden_effect_infinite_vs_timed(self):
        """Test hidden effect display difference between infinite and timed"""
        from cogs5e.initiative.combatant import Combatant
        from unittest.mock import Mock

        # Infinite effect (no duration)
        infinite_effect = InitiativeEffect.new(
            None, None, "Infinite Effect", desc="Secret description", duration=None, concentration=False, hidden=True
        )

        # Timed effect (with duration)
        timed_effect = InitiativeEffect.new(
            None, None, "Timed Effect", desc="Secret description", duration=3, concentration=False, hidden=True
        )

        # Mock a combatant with both hidden effects
        combatant = Combatant(
            ctx=Mock(), combat=Mock(), id="test_id", name="Test", controller_id=12345, init=10, private=False, index=0
        )
        combatant._effects = [infinite_effect, timed_effect]
        infinite_effect.combatant = combatant
        timed_effect.combatant = combatant

        # Player view should show names only (no duration without combat context)
        player_display = combatant._get_long_effects(private=False)
        self.assertIn("Infinite Effect", player_display)
        self.assertIn("Timed Effect", player_display)
        self.assertNotIn("Secret description", player_display)
        # Duration only shows with combat context
        self.assertNotIn("[3 rounds]", player_display)

    def test_hidden_effect_with_combat_context(self):
        """Test hidden effect shows duration but hides description"""
        from cogs5e.initiative.combatant import Combatant
        from unittest.mock import Mock

        class MockCombat:
            def __init__(self):
                self.round_num = 1
                self.index = 0

        mock_combat = MockCombat()

        timed_effect = InitiativeEffect.new(
            mock_combat, None, "Timed Effect", desc="Secret description", duration=3, concentration=True, hidden=True
        )

        # Mock a combatant with the hidden effect
        combatant = Combatant(
            ctx=Mock(),
            combat=mock_combat,
            id="test_id",
            name="Test",
            controller_id=12345,
            init=10,
            private=False,
            index=0,
        )
        combatant._effects = [timed_effect]
        timed_effect.combatant = combatant

        # Player view should show name, duration, and concentration but hide description
        player_display = combatant._get_long_effects(private=False)
        self.assertIn("Timed Effect", player_display)
        self.assertNotIn("Secret description", player_display)
        self.assertIn("[3 rounds]", player_display)
        # Concentration marker should still show
        self.assertIn("<C>", player_display)

    def test_hidden_effect_always_hidden(self):
        """Test hidden effect is always hidden from players"""
        from cogs5e.initiative.combatant import Combatant
        from unittest.mock import Mock

        effect = InitiativeEffect.new(None, None, "Secret Effect", desc="Secret description", hidden=True)

        # Mock a combatant with the hidden effect
        combatant = Combatant(
            ctx=Mock(), combat=Mock(), id="test_id", name="Test", controller_id=12345, init=10, private=False, index=0
        )
        combatant._effects = [effect]
        effect.combatant = combatant

        # Player view should hide description
        player_display = combatant._get_long_effects(private=False)
        self.assertIn("Secret Effect", player_display)
        self.assertNotIn("Secret description", player_display)

    def test_visible_effect_display_always_shown(self):
        """Test visible effect always shows everything"""
        effect = InitiativeEffect.new(
            None, None, "Public Effect", desc="Public description", duration=5, concentration=True, hidden=False
        )

        display = effect.get_str()

        # Visible effects show everything
        self.assertIn("Public description", display)
        self.assertIn("<C>", display)

    def test_hidden_effect_status_dm_privilege(self):
        """Test that DMs/controllers can see hidden effect details in status via private param"""
        from cogs5e.initiative.combatant import Combatant
        from unittest.mock import Mock

        # Create hidden effect with description
        effect = InitiativeEffect.new(
            combat=None, combatant=None, name="Secret Buff", desc="Grants +2 AC and advantage", hidden=True
        )

        # Mock a combatant with the hidden effect
        combatant = Combatant(
            ctx=Mock(), combat=Mock(), id="test_id", name="Test", controller_id=12345, init=10, private=False, index=0
        )
        combatant._effects = [effect]
        effect.combatant = combatant

        # Test normal status (should hide details)
        normal_status = combatant._get_long_effects(private=False)
        self.assertIn("Secret Buff", normal_status)
        self.assertNotIn("Grants +2 AC", normal_status)

        # Test DM status (should show details)
        dm_status = combatant._get_long_effects(private=True)

        # Debug: Test direct get_str call with explicit override
        direct_call = effect.get_str(description=True, parenthetical=True)
        print(f"Direct get_str with override: '{direct_call}'")
        print(f"DM status output: '{dm_status}'")

        self.assertIn("Secret Buff", dm_status)
        self.assertIn("Grants +2 AC", dm_status)


# Uncomment after PR #15 on automation-common is merged: https://github.com/avrae/automation-common/pull/15

# class TestHiddenEffectsAPIInterface(unittest.TestCase):
#     """Test hidden effects through automation import/export interface"""

#     def test_hidden_effect_import_export_preservation(self):
#         """Test hidden field is preserved through full import flow (mimics !a import)"""
#         from typing import List
#         import automation_common
#         from pydantic import parse_obj_as
#         from cogs5e.models.sheet.attack import AttackList

#         # Create attack JSON with hidden IEffect
#         attack_json = [{
#             "_v": 2,
#             "name": "Test Attack with Hidden Effect",
#             "automation": [{
#                 "type": "ieffect2",
#                 "name": "Hidden Test Effect",
#                 "hidden": True,
#                 "duration": 3,
#                 "desc": "This should be hidden",
#                 "effects": {"ac_bonus": -2},
#             }],
#         }]

#         # Test pydantic validation (now preserves hidden field)
#         normalized_obj = parse_obj_as(
#             List[automation_common.validation.models.AttackModel], attack_json, type_name="AttackList"
#         )

#         # Test round-trip through AttackList
#         attacks = AttackList.from_dict([atk.dict() for atk in normalized_obj])
#         attack = attacks[0]

#         # Verify the automation object has the hidden field
#         automation_effect = attack.automation.effects[0]
#         self.assertTrue(
#             automation_effect.hidden,
#             "Hidden field should be preserved through full import flow with updated pydantic models",
#         )

#         # Test serialization back to dict
#         export_dict = attack.to_dict()
#         ieffect_dict = export_dict["automation"][0]
#         self.assertTrue(ieffect_dict.get("hidden", False), "Hidden field should be present in exported dict")
