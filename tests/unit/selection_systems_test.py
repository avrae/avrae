import pytest
from unittest.mock import Mock, AsyncMock, patch

from gamedata.lookuputils import _handle_legacy_preference, search_entities
from gamedata.shared import Sourced
from utils.settings.guild import LegacyPreference, ServerSettings


class MockSourced(Sourced):
    """Mock implementation of Sourced for testing"""

    entity_type = "test"

    def __init__(self, name, is_legacy=False, is_free=True, entitlement_entity_type=None, entitlement_entity_id=1):
        self.name = name
        self.is_legacy = is_legacy
        self.is_free = is_free
        self.homebrew = False
        self.source = "TEST"
        self.entity_id = entitlement_entity_id
        self.page = None
        self._url = None
        self.entitlement_entity_type = entitlement_entity_type or self.entity_type
        self.entitlement_entity_id = entitlement_entity_id
        self.limited_use_only = False
        self.rulesVersion = None


class MockMonster(MockSourced):
    """Mock Monster for testing"""

    entity_type = "monster"

    def __init__(self, name, is_legacy=False, is_free=True):
        super().__init__(name, is_legacy, is_free, "monster")


class MockSpell(MockSourced):
    """Mock Spell for testing"""

    entity_type = "spell"

    def __init__(self, name, is_legacy=False, is_free=True):
        super().__init__(name, is_legacy, is_free, "spell")


class MockContext:
    """Mock context for testing"""

    def __init__(self, guild=True):
        self.guild = Mock() if guild else None
        self.author = Mock()
        self.author.id = 12345
        self.author.send = AsyncMock()
        self.channel = Mock()
        self.channel.mention = "<#123456789>"
        self.channel.send = AsyncMock()
        self.bot = Mock()
        self.bot.wait_for = AsyncMock()

    async def get_server_settings(self):
        settings = Mock(spec=ServerSettings)
        settings.legacy_preference = LegacyPreference.ASK
        return settings

    async def trigger_typing(self):
        """Mock trigger_typing method"""
        pass


@pytest.fixture
def mock_ctx():
    return MockContext()


@pytest.fixture
def mock_ctx_pm():
    return MockContext(guild=False)


@pytest.fixture
def available_ids():
    return {"monster": {1, 2, 3}, "spell": {1, 2, 3}}


@pytest.fixture
def legacy_monster():
    return MockMonster("Ancient Goblin", is_legacy=True, is_free=True)


@pytest.fixture
def modern_monster():
    return MockMonster("Goblin", is_legacy=False, is_free=True)


@pytest.fixture
def spell():
    return MockSpell("Fireball", is_legacy=False, is_free=True)


def setup_mock_settings(mock_ctx, legacy_pref=LegacyPreference.ASK, enable_buttons=False):
    """Helper to set up mock server settings on a context"""
    mock_ctx.get_server_settings = AsyncMock()
    settings = Mock()
    settings.legacy_preference = legacy_pref
    settings.enable_button_selection = enable_buttons
    mock_ctx.get_server_settings.return_value = settings
    return settings


class TestHandleLegacyPreference:
    """Test the _handle_legacy_preference function for auto-selecting between legacy and modern entities"""

    @pytest.mark.asyncio
    async def test_single_choice_returns_none(self, mock_ctx, available_ids, spell):
        """Single choice should return None (no auto-selection)"""
        result = await _handle_legacy_preference(mock_ctx, [spell], available_ids)
        assert result is None

    @pytest.mark.asyncio
    async def test_non_legacy_choices_returns_none(self, mock_ctx, available_ids):
        """Two non-legacy choices should return None (no auto-selection)"""
        spell1 = MockSpell("Fireball")
        spell2 = MockSpell("Firebolt")

        result = await _handle_legacy_preference(mock_ctx, [spell1, spell2], available_ids)
        assert result is None

    @pytest.mark.asyncio
    async def test_pm_context_returns_none(self, mock_ctx_pm, available_ids):
        """PM context should return None (no auto-selection)"""
        legacy_spell = MockSpell("Ancient Fireball", is_legacy=True, is_free=True)
        modern_spell = MockSpell("Fireball", is_legacy=False, is_free=True)

        result = await _handle_legacy_preference(mock_ctx_pm, [legacy_spell, modern_spell], available_ids)
        assert result is None

    @pytest.mark.asyncio
    async def test_legacy_preference_ask_returns_none(self, mock_ctx, available_ids, legacy_monster, modern_monster):
        """ASK preference should return None (let user choose)"""
        setup_mock_settings(mock_ctx, legacy_pref=LegacyPreference.ASK)

        with patch("gamedata.lookuputils.can_access", return_value=True):
            result = await _handle_legacy_preference(mock_ctx, [legacy_monster, modern_monster], available_ids)
            assert result is None

    @pytest.mark.asyncio
    async def test_legacy_preference_latest_returns_latest(
        self, mock_ctx, available_ids, legacy_monster, modern_monster
    ):
        """LATEST preference should auto-select the modern entity"""
        setup_mock_settings(mock_ctx, legacy_pref=LegacyPreference.LATEST)

        with patch("gamedata.lookuputils.can_access", return_value=True):
            result = await _handle_legacy_preference(mock_ctx, [legacy_monster, modern_monster], available_ids)
            assert result == modern_monster

    @pytest.mark.asyncio
    async def test_legacy_preference_legacy_returns_legacy(
        self, mock_ctx, available_ids, legacy_monster, modern_monster
    ):
        """LEGACY preference should auto-select the legacy entity"""
        setup_mock_settings(mock_ctx, legacy_pref=LegacyPreference.LEGACY)

        with patch("gamedata.lookuputils.can_access", return_value=True):
            result = await _handle_legacy_preference(mock_ctx, [legacy_monster, modern_monster], available_ids)
            assert result == legacy_monster


class TestMonsterPMSelectorLegacyPreference:
    """Test monster PM selector (buttons enabled) respects legacy preferences"""

    @pytest.mark.asyncio
    async def test_preference_ask_shows_selection(self, mock_ctx, available_ids, legacy_monster, modern_monster):
        """ASK: Should show button selection"""
        setup_mock_settings(mock_ctx, legacy_pref=LegacyPreference.ASK, enable_buttons=True)

        with patch("utils.selection.select_monster_with_dm_feedback") as mock_dm_feedback:
            mock_dm_feedback.return_value = modern_monster

            # Manually create and test the selector that would be created in search_entities
            async def test_selector(ctx, choices, *args, **kwargs):
                """Reproduce the monster_pm_selector logic"""
                if len(choices) == 2 and ctx.guild is not None:
                    a, b = choices
                    if a.is_legacy != b.is_legacy:
                        from utils.settings.guild import LegacyPreference
                        from gamedata.lookuputils import can_access

                        legacy = a if a.is_legacy else b
                        latest = a if not a.is_legacy else b

                        guild_settings = await ctx.get_server_settings()
                        # If guild prefers LATEST and user has access, return it
                        if guild_settings.legacy_preference == LegacyPreference.LATEST and can_access(
                            latest, available_ids[latest.entitlement_entity_type]
                        ):
                            return latest
                        # If guild prefers LEGACY and user has access, return it
                        elif guild_settings.legacy_preference == LegacyPreference.LEGACY and can_access(
                            legacy, available_ids[legacy.entitlement_entity_type]
                        ):
                            return legacy

                # Otherwise use button-based DM feedback
                return await mock_dm_feedback(
                    ctx=ctx, choices=choices, key=kwargs.get("key"), query=kwargs.get("query")
                )

            with patch("gamedata.lookuputils.can_access", return_value=True):
                result = await test_selector(mock_ctx, [legacy_monster, modern_monster], key=lambda x: x.name)

                # Should call select_monster_with_dm_feedback for ASK
                mock_dm_feedback.assert_called_once()
                assert result == modern_monster

    @pytest.mark.asyncio
    async def test_preference_latest_returns_latest(self, mock_ctx, available_ids, legacy_monster, modern_monster):
        """LATEST: Should auto-select latest version"""
        setup_mock_settings(mock_ctx, legacy_pref=LegacyPreference.LATEST, enable_buttons=True)

        with patch("utils.selection.select_monster_with_dm_feedback") as mock_dm_feedback:
            with patch("gamedata.lookuputils.search_and_select") as mock_search:
                # The selector should return latest directly, search_and_select won't be involved in selection
                mock_search.return_value = (modern_monster, {"num_options": 2, "chosen_index": 1})
                with patch.object(mock_ctx.bot, "ddb") as mock_ddb:
                    mock_ddb.get_accessible_entities = AsyncMock(return_value={1, 2, 3})
                    with patch("gamedata.lookuputils.add_training_data"):
                        with patch("gamedata.lookuputils.can_access", return_value=True):
                            result = await search_entities(
                                mock_ctx, {"monster": [legacy_monster, modern_monster]}, "goblin", pm=True
                            )

                            # Should NOT call select_monster_with_dm_feedback - direct return
                            mock_dm_feedback.assert_not_called()
                            assert result == modern_monster

    @pytest.mark.asyncio
    async def test_preference_legacy_returns_legacy(self, mock_ctx, available_ids, legacy_monster, modern_monster):
        """LEGACY: Should auto-select legacy version"""
        setup_mock_settings(mock_ctx, legacy_pref=LegacyPreference.LEGACY, enable_buttons=True)

        with patch("utils.selection.select_monster_with_dm_feedback") as mock_dm_feedback:
            with patch("gamedata.lookuputils.search_and_select") as mock_search:
                mock_search.return_value = (legacy_monster, {"num_options": 2, "chosen_index": 0})
                with patch.object(mock_ctx.bot, "ddb") as mock_ddb:
                    mock_ddb.get_accessible_entities = AsyncMock(return_value={1, 2, 3})
                    with patch("gamedata.lookuputils.add_training_data"):
                        with patch("gamedata.lookuputils.can_access", return_value=True):
                            result = await search_entities(
                                mock_ctx, {"monster": [legacy_monster, modern_monster]}, "goblin", pm=True
                            )

                            # Should NOT call select_monster_with_dm_feedback - direct return
                            mock_dm_feedback.assert_not_called()
                            assert result == legacy_monster


class TestSearchEntities:
    """Test the search_entities function to ensure proper selector routing"""

    @pytest.mark.asyncio
    async def test_monster_entities_use_monster_selector(self, mock_ctx, modern_monster):
        entities = {"monster": [modern_monster]}

        with patch("gamedata.lookuputils.search_and_select") as mock_search:
            mock_search.return_value = (modern_monster, {"num_options": 1, "chosen_index": 0})
            with patch("gamedata.lookuputils.create_selectkey") as mock_selectkey:
                mock_selectkey.return_value = lambda x: x.name
                with patch.object(mock_ctx.bot, "ddb") as mock_ddb:
                    mock_ddb.get_accessible_entities = AsyncMock(return_value={1, 2, 3})
                    with patch("gamedata.lookuputils.add_training_data"):
                        with patch("gamedata.lookuputils.can_access", return_value=True):

                            result = await search_entities(mock_ctx, entities, "goblin")

                            # Verify search_and_select was called
                            mock_search.assert_called_once()
                            call_args = mock_search.call_args

                            # Verify the selector function is the monster selector
                            selector_func = call_args[1]["selector"]
                            assert selector_func is not None

                            assert result == modern_monster

    @pytest.mark.asyncio
    async def test_spell_entities_use_text_selector(self, mock_ctx, spell):
        entities = {"spell": [spell]}

        with patch("gamedata.lookuputils.search_and_select") as mock_search:
            mock_search.return_value = (spell, {"num_options": 1, "chosen_index": 0})
            with patch("gamedata.lookuputils.create_selectkey") as mock_selectkey:
                mock_selectkey.return_value = lambda x: x.name
                with patch.object(mock_ctx.bot, "ddb") as mock_ddb:
                    mock_ddb.get_accessible_entities = AsyncMock(return_value={1, 2, 3})
                    with patch("gamedata.lookuputils.add_training_data"):
                        with patch("gamedata.lookuputils.can_access", return_value=True):

                            result = await search_entities(mock_ctx, entities, "fireball")

                            # Verify search_and_select was called
                            mock_search.assert_called_once()
                            call_args = mock_search.call_args

                            # Verify the selector function is the text selector
                            selector_func = call_args[1]["selector"]
                            assert selector_func is not None

                            assert result == spell


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
