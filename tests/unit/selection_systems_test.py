import pytest
from unittest.mock import Mock, AsyncMock, patch

from gamedata.lookuputils import _create_selector, search_entities
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


class TestCreateSelector:
    """Test the text-based selector for non-monster entities"""

    @pytest.mark.asyncio
    async def test_single_choice_returns_directly(self, mock_ctx, available_ids, spell):
        with patch("gamedata.lookuputils.get_selection") as mock_get_selection:
            mock_get_selection.return_value = spell
            selector = _create_selector(available_ids)

            result = await selector(mock_ctx, [spell], key=lambda x: x.name)

            assert result == spell

    @pytest.mark.asyncio
    async def test_non_legacy_choices_defer_to_get_selection(self, mock_ctx, available_ids):
        spell1 = MockSpell("Fireball")
        spell2 = MockSpell("Firebolt")

        with patch("gamedata.lookuputils.get_selection") as mock_get_selection:
            mock_get_selection.return_value = spell1
            selector = _create_selector(available_ids)

            result = await selector(mock_ctx, [spell1, spell2], key=lambda x: x.name)

            mock_get_selection.assert_called_once()
            assert result == spell1

    @pytest.mark.asyncio
    async def test_pm_context_defers_to_get_selection(self, mock_ctx_pm, available_ids):
        # Use spells instead of monsters for non-monster test
        legacy_spell = MockSpell("Ancient Fireball", is_legacy=True, is_free=True)
        modern_spell = MockSpell("Fireball", is_legacy=False, is_free=True)

        with patch("gamedata.lookuputils.get_selection") as mock_get_selection:
            mock_get_selection.return_value = modern_spell
            selector = _create_selector(available_ids)

            result = await selector(mock_ctx_pm, [legacy_spell, modern_spell])

            mock_get_selection.assert_called_once()
            assert result == modern_spell

    @pytest.mark.asyncio
    async def test_legacy_preference_ask_defers_to_get_selection(
        self, mock_ctx, available_ids, legacy_monster, modern_monster
    ):
        with patch("gamedata.lookuputils.get_selection") as mock_get_selection:
            mock_get_selection.return_value = modern_monster
            with patch("gamedata.lookuputils.can_access", return_value=True):
                selector = _create_selector(available_ids)

                result = await selector(mock_ctx, [legacy_monster, modern_monster])

                mock_get_selection.assert_called_once()
                assert result == modern_monster

    @pytest.mark.asyncio
    async def test_legacy_preference_latest_returns_latest(
        self, mock_ctx, available_ids, legacy_monster, modern_monster
    ):
        setup_mock_settings(mock_ctx, legacy_pref=LegacyPreference.LATEST)

        with patch("gamedata.lookuputils.can_access", return_value=True):
            selector = _create_selector(available_ids)

            result = await selector(mock_ctx, [legacy_monster, modern_monster])

            assert result == modern_monster

    @pytest.mark.asyncio
    async def test_legacy_preference_legacy_returns_legacy(
        self, mock_ctx, available_ids, legacy_monster, modern_monster
    ):
        setup_mock_settings(mock_ctx, legacy_pref=LegacyPreference.LEGACY)

        with patch("gamedata.lookuputils.can_access", return_value=True):
            selector = _create_selector(available_ids)

            result = await selector(mock_ctx, [legacy_monster, modern_monster])

            assert result == legacy_monster


class TestCreateMonsterSelector:
    """Test the selector routing behavior (selector now just forwards to get_selection)"""

    @pytest.mark.asyncio
    async def test_single_monster_channel_defers_to_get_selection(self, mock_ctx, available_ids, modern_monster):
        setup_mock_settings(mock_ctx, enable_buttons=True)

        with patch("gamedata.lookuputils.get_selection") as mock_get_selection:
            mock_get_selection.return_value = modern_monster
            selector = _create_selector(available_ids)

            result = await selector(mock_ctx, [modern_monster], pm=False)

            mock_get_selection.assert_called_once()
            assert result == modern_monster

    @pytest.mark.asyncio
    async def test_guild_context_pm_menu_defers_to_get_selection(
        self, mock_ctx, available_ids, legacy_monster, modern_monster
    ):
        setup_mock_settings(mock_ctx, enable_buttons=True)

        with patch("gamedata.lookuputils.get_selection") as mock_get_selection:
            mock_get_selection.return_value = modern_monster
            selector = _create_selector(available_ids)

            result = await selector(mock_ctx, [legacy_monster, modern_monster], pm=True)

            mock_get_selection.assert_called_once()
            assert result == modern_monster

    @pytest.mark.asyncio
    async def test_single_monster_pm_uses_get_selection(self, mock_ctx_pm, available_ids, modern_monster):
        with patch("gamedata.lookuputils.get_selection") as mock_get_selection:
            mock_get_selection.return_value = modern_monster
            selector = _create_selector(available_ids)

            result = await selector(mock_ctx_pm, [modern_monster], pm=True)

            mock_get_selection.assert_called_once()
            assert result == modern_monster

    @pytest.mark.asyncio
    async def test_legacy_preference_ask_defers_to_get_selection(
        self, mock_ctx, available_ids, legacy_monster, modern_monster
    ):
        setup_mock_settings(mock_ctx, enable_buttons=True)

        with patch("gamedata.lookuputils.get_selection") as mock_get_selection:
            mock_get_selection.return_value = modern_monster
            selector = _create_selector(available_ids)

            result = await selector(mock_ctx, [legacy_monster, modern_monster], pm=False)

            mock_get_selection.assert_called_once()
            assert result == modern_monster

    @pytest.mark.asyncio
    async def test_legacy_preference_ask_pm_defers_to_get_selection(
        self, mock_ctx_pm, available_ids, legacy_monster, modern_monster
    ):
        with patch("gamedata.lookuputils.get_selection") as mock_get_selection:
            mock_get_selection.return_value = modern_monster
            selector = _create_selector(available_ids)

            result = await selector(mock_ctx_pm, [legacy_monster, modern_monster], pm=True)

            mock_get_selection.assert_called_once()
            assert result == modern_monster

    @pytest.mark.asyncio
    async def test_legacy_preference_latest_returns_latest(
        self, mock_ctx, available_ids, legacy_monster, modern_monster
    ):
        setup_mock_settings(mock_ctx, legacy_pref=LegacyPreference.LATEST)

        with patch("gamedata.lookuputils.can_access", return_value=True):
            selector = _create_selector(available_ids)

            result = await selector(mock_ctx, [legacy_monster, modern_monster], pm=False)

            assert result == modern_monster


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
