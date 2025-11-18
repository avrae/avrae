import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime
from contextlib import asynccontextmanager

from gamedata.lookuputils import madd_monster_converter
from gamedata.shared import Sourced
from utils.settings.guild import LegacyPreference


class MockSourced(Sourced):
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
    entity_type = "monster"

    def __init__(self, name, is_legacy=False, is_free=True):
        super().__init__(name, is_legacy, is_free, "monster")


@pytest.fixture
def mock_inter():
    inter = Mock()
    inter.guild = Mock()
    inter.guild.id = 123456789
    inter.author = Mock()
    inter.author.id = 12345
    inter.bot = Mock()
    inter.bot.mdb = Mock()
    inter.bot.ddb = Mock()
    inter.bot.ddb.get_accessible_entities = AsyncMock(return_value={1})

    mock_lookup_cog = Mock()

    async def _get_entities_side_effect(ctx, entity_type, fn):
        return await fn(ctx)

    mock_lookup_cog._get_entities = AsyncMock(side_effect=_get_entities_side_effect)
    inter.bot.get_cog = Mock(return_value=mock_lookup_cog)

    return inter


@pytest.fixture
def mock_inter_dm():
    inter = Mock()
    inter.guild = None
    inter.author = Mock()
    inter.author.id = 12345
    inter.bot = Mock()
    inter.bot.ddb = Mock()
    inter.bot.ddb.get_accessible_entities = AsyncMock(return_value={1})

    mock_lookup_cog = Mock()

    async def _get_entities_side_effect(ctx, entity_type, fn):
        return await fn(ctx)

    mock_lookup_cog._get_entities = AsyncMock(side_effect=_get_entities_side_effect)
    inter.bot.get_cog = Mock(return_value=mock_lookup_cog)

    return inter


@pytest.fixture
def mock_ctx():
    ctx = Mock()
    ctx.author = Mock()
    ctx.author.id = 12345
    ctx.author.send = AsyncMock()
    ctx.bot = Mock()
    ctx.bot.mdb = Mock()
    ctx.bot.mdb.analytics_monster_usage = Mock()
    ctx.bot.mdb.analytics_monster_usage.update_one = AsyncMock()
    ctx.send = AsyncMock()
    return ctx


@pytest.fixture
def mock_monster():
    monster = Mock()
    monster.name = "Goblin"
    monster.entity_id = 1
    monster.hitdice = "2d6"
    monster.skills = Mock()
    monster.skills.initiative = Mock()
    monster.skills.initiative.d20 = Mock(return_value="1d20+2")
    monster.skills.initiative.value = 2
    return monster


@pytest.fixture
def mock_monster_homebrew():
    monster = Mock()
    monster.name = "Custom Dragon"
    monster.entity_id = None
    monster.hitdice = "10d12"
    monster.skills = Mock()
    monster.skills.initiative = Mock()
    monster.skills.initiative.d20 = Mock(return_value="1d20+0")
    monster.skills.initiative.value = 0
    return monster


@asynccontextmanager
async def mock_monster_lookup(choices, search_result, is_strict=False, settings_preference=None):
    """Mock monster lookup with optional server settings.
    Requires mock_inter/mock_inter_dm fixture for bot.get_cog() setup."""
    with patch("gamedata.lookuputils.get_monster_choices", new_callable=AsyncMock) as mock_choices:
        mock_choices.return_value = choices
        with patch("gamedata.lookuputils.search") as mock_search:
            mock_search.return_value = (search_result, is_strict)

            if settings_preference is not None:
                with patch("gamedata.lookuputils.ServerSettings.for_guild", new_callable=AsyncMock) as mock_settings:
                    settings = Mock()
                    settings.legacy_preference = settings_preference
                    mock_settings.return_value = settings
                    yield
            else:
                yield


@asynccontextmanager
async def mock_cog_lookup(choices, search_result=None, is_strict=False, favorites=None):
    """Mock cog autocomplete lookup.
    Requires mock_cog fixture for bot.get_cog() setup."""
    with patch("cogs5e.initiative.cog.get_monster_choices", new_callable=AsyncMock) as mock_choices:
        mock_choices.return_value = choices
        with patch("cogs5e.initiative.cog.get_user_favorite_monsters", new_callable=AsyncMock) as mock_fav:
            mock_fav.return_value = favorites or []

            if search_result is not None:
                with patch("cogs5e.initiative.cog.search") as mock_search:
                    mock_search.return_value = (search_result, is_strict)
                    yield choices
            else:
                yield choices


@asynccontextmanager
async def mock_combat_add(mock_ctx):
    """Mock combat operations for _madd_impl tests."""
    with patch("cogs5e.initiative.cog.Combat") as MockCombat:
        mock_combat = Mock()
        mock_combat.add_combatant = Mock()
        mock_combat.get_combatant = Mock(return_value=None)
        mock_combat.final = AsyncMock()
        MockCombat.from_ctx = AsyncMock(return_value=mock_combat)

        with patch("cogs5e.initiative.cog.MonsterCombatant") as MockMonsterCombatant:
            mock_combatant = Mock()
            mock_combatant.name = "Goblin 1"
            mock_combatant.init = 15
            MockMonsterCombatant.from_monster = Mock(return_value=mock_combatant)

            with patch("cogs5e.initiative.cog.roll") as mock_roll:
                mock_roll.return_value = Mock(total=15, result="15")
                yield mock_combat, mock_combatant


class TestMaddMonsterConverter:
    @pytest.mark.asyncio
    async def test_no_results_raises_error(self, mock_inter):
        async with mock_monster_lookup([], []):
            with pytest.raises(ValueError, match="doesn't exist"):
                await madd_monster_converter(mock_inter, "nonexistent")

    @pytest.mark.asyncio
    async def test_exact_match_returns_directly(self, mock_inter):
        cached_goblin = MockMonster("Goblin", is_legacy=False)
        full_goblin = Mock(name="Full Goblin")

        with patch("gamedata.lookuputils._fetch_single_monster", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = full_goblin
            async with mock_monster_lookup([cached_goblin], cached_goblin, is_strict=True):
                result = await madd_monster_converter(mock_inter, "Goblin")

                assert result == full_goblin
                assert result != cached_goblin
                mock_fetch.assert_called_once()
                assert mock_fetch.call_args[0][1] == cached_goblin

    @pytest.mark.asyncio
    async def test_single_fuzzy_match_returns_first(self, mock_inter):
        cached_goblin = MockMonster("Goblin", is_legacy=False)
        full_goblin = Mock(name="Full Goblin")

        with patch("gamedata.lookuputils._fetch_single_monster", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = full_goblin
            async with mock_monster_lookup([cached_goblin], [cached_goblin]):
                result = await madd_monster_converter(mock_inter, "gob")

                assert result == full_goblin
                assert result != cached_goblin
                mock_fetch.assert_called_once()
                assert mock_fetch.call_args[0][1] == cached_goblin

    @pytest.mark.asyncio
    async def test_three_results_returns_first(self, mock_inter):
        cached_goblins = [
            MockMonster("Goblin", is_legacy=False),
            MockMonster("Goblin Boss", is_legacy=False),
            MockMonster("Goblin Shaman", is_legacy=False),
        ]
        full_goblin = Mock(name="Full Goblin")

        with patch("gamedata.lookuputils._fetch_single_monster", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = full_goblin
            with patch("gamedata.lookuputils._handle_legacy_preference_slash", new_callable=AsyncMock) as mock_pref:
                mock_pref.return_value = None
                async with mock_monster_lookup(cached_goblins, cached_goblins):
                    result = await madd_monster_converter(mock_inter, "goblin")

                    assert result == full_goblin
                    assert result != cached_goblins[0]
                    mock_pref.assert_called_once()
                    mock_fetch.assert_called_once()
                    assert mock_fetch.call_args[0][1] == cached_goblins[0]

    @pytest.mark.asyncio
    async def test_dm_context_returns_first(self, mock_inter_dm):
        cached_legacy = MockMonster("Goblin", is_legacy=True)
        cached_modern = MockMonster("Goblin", is_legacy=False)
        full_goblin = Mock(name="Full Goblin")

        with patch("gamedata.lookuputils._fetch_single_monster", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = full_goblin
            with patch("gamedata.lookuputils._handle_legacy_preference_slash", new_callable=AsyncMock) as mock_pref:
                mock_pref.return_value = None
                async with mock_monster_lookup([cached_legacy, cached_modern], [cached_legacy, cached_modern]):
                    result = await madd_monster_converter(mock_inter_dm, "goblin")

                    assert result == full_goblin
                    assert result != cached_legacy
                    mock_pref.assert_called_once()
                    mock_fetch.assert_called_once()
                    assert mock_fetch.call_args[0][1] == cached_legacy

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "preference,expected_idx",
        [
            (LegacyPreference.ASK, 0),
            (LegacyPreference.LATEST, 1),
            (LegacyPreference.LEGACY, 0),
        ],
    )
    async def test_legacy_pair_preferences(self, mock_inter, preference, expected_idx):
        cached_legacy = MockMonster("Goblin", is_legacy=True)
        cached_modern = MockMonster("Goblin", is_legacy=False)
        cached_expected = [cached_legacy, cached_modern][expected_idx]
        full_goblin = Mock(name="Full Goblin")

        mock_inter.bot.ddb.get_accessible_entities = AsyncMock(return_value={1})
        with patch("gamedata.lookuputils._fetch_single_monster", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = full_goblin
            async with mock_monster_lookup(
                [cached_legacy, cached_modern], [cached_legacy, cached_modern], settings_preference=preference
            ):
                result = await madd_monster_converter(mock_inter, "goblin")

                assert result == full_goblin
                assert result != cached_expected
                mock_fetch.assert_called_once()
                assert mock_fetch.call_args[0][1] == cached_expected

    @pytest.mark.asyncio
    async def test_legacy_pair_no_access_raises_license_error(self, mock_inter):
        from cogs5e.models.errors import RequiresLicense

        legacy = MockMonster("Goblin", is_legacy=True, is_free=False)
        modern = MockMonster("Goblin", is_legacy=False, is_free=False)
        mock_inter.bot.ddb.get_accessible_entities = AsyncMock(return_value=set())

        with patch("gamedata.lookuputils._fetch_single_monster", new_callable=AsyncMock) as mock_fetch:
            async with mock_monster_lookup(
                [legacy, modern], [legacy, modern], settings_preference=LegacyPreference.LATEST
            ):
                with pytest.raises(RequiresLicense):
                    await madd_monster_converter(mock_inter, "goblin")
                mock_fetch.assert_not_called()


class TestGetUserFavoriteMonsters:
    @pytest.mark.asyncio
    async def test_mfu_ordering_with_recency(self, mock_ctx):
        from gamedata.lookuputils import get_user_favorite_monsters, USER_MONSTER_FAVORITES_CACHE

        USER_MONSTER_FAVORITES_CACHE.clear()

        mock_cursor = Mock()
        mock_cursor.limit.return_value = mock_cursor
        mock_cursor.to_list = AsyncMock(
            return_value=[
                {"monster_name": "Goblin", "monster_id": 1, "count": 5, "last_used": datetime(2024, 1, 15)},
                {"monster_name": "Orc", "monster_id": 2, "count": 3, "last_used": datetime(2024, 1, 14)},
                {"monster_name": "Kobold", "monster_id": 3, "count": 3, "last_used": datetime(2024, 1, 10)},
            ]
        )
        mock_ctx.bot.mdb.analytics_monster_usage.find.return_value.sort.return_value = mock_cursor

        result = await get_user_favorite_monsters(mock_ctx, 12345, limit=25)

        assert result == [("Goblin", 1), ("Orc", 2), ("Kobold", 3)]
        mock_ctx.bot.mdb.analytics_monster_usage.find.return_value.sort.assert_called_once_with(
            [("count", -1), ("last_used", -1)]
        )

    @pytest.mark.asyncio
    async def test_cache_hit_no_db_query(self, mock_ctx):
        from gamedata.lookuputils import get_user_favorite_monsters, USER_MONSTER_FAVORITES_CACHE

        USER_MONSTER_FAVORITES_CACHE[12345] = [("Goblin", 1), ("Orc", 2)]

        result = await get_user_favorite_monsters(mock_ctx, 12345, limit=25)

        assert result == [("Goblin", 1), ("Orc", 2)]
        mock_ctx.bot.mdb.analytics_monster_usage.find.assert_not_called()


class TestSlashMaddAutocomplete:
    @pytest.fixture
    def mock_inter(self):
        inter = Mock()
        inter.author = Mock()
        inter.author.id = 12345
        inter.bot = Mock()
        inter.bot.ddb = Mock()
        inter.bot.ddb.get_accessible_entities = AsyncMock(return_value={1, 2, 3})
        return inter

    @pytest.fixture
    def mock_cog(self):
        from cogs5e.initiative.cog import InitTracker

        mock_bot = Mock()
        mock_bot.ddb = Mock()
        mock_bot.ddb.get_accessible_entities = AsyncMock(return_value={1, 2, 3})

        mock_lookup_cog = Mock()

        async def _get_entities_side_effect(ctx, entity_type, fn):
            return await fn(ctx)

        mock_lookup_cog._get_entities = AsyncMock(side_effect=_get_entities_side_effect)
        mock_bot.get_cog = Mock(return_value=mock_lookup_cog)

        cog = InitTracker(mock_bot)
        return cog

    @pytest.mark.asyncio
    async def test_empty_input_with_favorites_and_srd_backfill(self, mock_inter, mock_cog):
        goblin = MockMonster("Goblin", is_free=False)
        goblin.entity_id = 1
        orc = MockMonster("Orc", is_free=False)
        orc.entity_id = 2
        kobold = MockMonster("Kobold", is_free=True)
        kobold.entity_id = 3

        async with mock_cog_lookup([goblin, orc, kobold], favorites=[("Goblin", 1), ("Orc", 2)]):
            result = await mock_cog.slash_madd_auto(mock_inter, "")
            assert len(result) == 3
            assert "Goblin" in result[0]
            assert "Orc" in result[1]
            assert "Kobold" in result[2]

            result_names = [r.split("(")[0].strip() for r in result]
            assert len(result_names) == len(set(result_names))

    @pytest.mark.asyncio
    async def test_empty_input_no_favorites_returns_srd(self, mock_inter, mock_cog):
        goblin = MockMonster("Goblin", is_free=True)
        goblin.entity_id = 1
        kobold = MockMonster("Kobold", is_free=True)
        kobold.entity_id = 2

        async with mock_cog_lookup([goblin, kobold], favorites=[]):
            result = await mock_cog.slash_madd_auto(mock_inter, "")
            assert len(result) == 2
            assert "Goblin" in result[0]
            assert "Kobold" in result[1]

    @pytest.mark.asyncio
    async def test_empty_input_id_priority_matching(self, mock_inter, mock_cog):
        goblin_legacy = MockMonster("Goblin", is_free=False)
        goblin_legacy.entity_id = 1
        goblin_modern = MockMonster("Goblin", is_free=False)
        goblin_modern.entity_id = 999

        async with mock_cog_lookup([goblin_legacy, goblin_modern], favorites=[("Goblin", 1)]):
            result = await mock_cog.slash_madd_auto(mock_inter, "")
            assert len(result) >= 1
            assert "Goblin" in result[0]
            assert "(TEST)" in result[0] or "1" in result[0]

    @pytest.mark.asyncio
    async def test_empty_input_name_fallback_homebrew(self, mock_inter, mock_cog):
        homebrew_dragon = MockMonster("Custom Dragon", is_free=True)
        homebrew_dragon.homebrew = True
        homebrew_dragon.entity_id = None

        async with mock_cog_lookup([homebrew_dragon], favorites=[("Custom Dragon", None)]):
            result = await mock_cog.slash_madd_auto(mock_inter, "")
            assert len(result) >= 1
            assert "Custom Dragon" in result[0]

    @pytest.mark.asyncio
    async def test_search_query_favorites_boosted(self, mock_inter, mock_cog):
        goblin = MockMonster("Goblin", is_free=True)
        goblin.entity_id = 1
        goblin_boss = MockMonster("Goblin Boss", is_free=True)
        goblin_boss.entity_id = 2
        goblin_shaman = MockMonster("Goblin Shaman", is_free=True)
        goblin_shaman.entity_id = 3

        async with mock_cog_lookup(
            [goblin, goblin_boss, goblin_shaman], [goblin, goblin_boss, goblin_shaman], favorites=[("Goblin Shaman", 3)]
        ):
            result = await mock_cog.slash_madd_auto(mock_inter, "gob")
            assert "Goblin Shaman" in result[0]

    @pytest.mark.asyncio
    async def test_search_strict_match_returns_immediately(self, mock_inter, mock_cog):
        goblin = MockMonster("Goblin", is_free=True)
        goblin.entity_id = 1

        async with mock_cog_lookup([goblin], goblin, is_strict=True, favorites=[]):
            result = await mock_cog.slash_madd_auto(mock_inter, "Goblin")
            assert len(result) == 1
            assert "Goblin" in result[0]


class TestMonsterUsageTracking:
    @pytest.fixture
    def tracking_cog(self, mock_ctx):
        from cogs5e.initiative.cog import InitTracker
        from gamedata.lookuputils import USER_MONSTER_FAVORITES_CACHE

        USER_MONSTER_FAVORITES_CACHE.clear()
        return InitTracker(mock_ctx.bot)

    @pytest.mark.asyncio
    async def test_tracking_single_monster(self, mock_ctx, mock_monster, tracking_cog):
        cog = tracking_cog

        async with mock_combat_add(mock_ctx):
            await cog._madd_impl(mock_ctx, mock_monster, "")
            mock_ctx.bot.mdb.analytics_monster_usage.update_one.assert_called_once_with(
                {"user_id": 12345, "monster_name": "Goblin", "monster_id": 1},
                {"$inc": {"count": 1}, "$currentDate": {"last_used": True}},
                upsert=True,
            )

    @pytest.mark.asyncio
    async def test_tracking_multiple_monsters_n_arg(self, mock_ctx, mock_monster, tracking_cog):
        cog = tracking_cog

        async with mock_combat_add(mock_ctx):
            await cog._madd_impl(mock_ctx, mock_monster, "-n 5")
            mock_ctx.bot.mdb.analytics_monster_usage.update_one.assert_called_once_with(
                {"user_id": 12345, "monster_name": "Goblin", "monster_id": 1},
                {"$inc": {"count": 1}, "$currentDate": {"last_used": True}},
                upsert=True,
            )

    @pytest.mark.asyncio
    async def test_tracking_homebrew_monster_no_entity_id(self, mock_ctx, mock_monster_homebrew, tracking_cog):
        cog = tracking_cog

        async with mock_combat_add(mock_ctx):
            await cog._madd_impl(mock_ctx, mock_monster_homebrew, "")
            mock_ctx.bot.mdb.analytics_monster_usage.update_one.assert_called_once_with(
                {"user_id": 12345, "monster_name": "Custom Dragon", "monster_id": None},
                {"$inc": {"count": 1}, "$currentDate": {"last_used": True}},
                upsert=True,
            )

    @pytest.mark.asyncio
    async def test_cache_invalidation_after_tracking(self, mock_ctx, mock_monster, tracking_cog):
        """Cache is invalidated once after loop completes."""
        from gamedata.lookuputils import USER_MONSTER_FAVORITES_CACHE

        USER_MONSTER_FAVORITES_CACHE[12345] = [("Old Monster", 99)]
        cog = tracking_cog

        async with mock_combat_add(mock_ctx):
            await cog._madd_impl(mock_ctx, mock_monster, "-n 3")
            assert 12345 not in USER_MONSTER_FAVORITES_CACHE

    @pytest.mark.asyncio
    async def test_tracking_failure_does_not_break_combat(self, mock_ctx, mock_monster, tracking_cog):
        """Analytics DB failure logs error but doesn't break combat."""
        mock_ctx.bot.mdb.analytics_monster_usage.update_one = AsyncMock(side_effect=Exception("DB connection lost"))
        cog = tracking_cog

        async with mock_combat_add(mock_ctx) as (mock_combat, _):
            await cog._madd_impl(mock_ctx, mock_monster, "")
            mock_combat.add_combatant.assert_called_once()
            mock_combat.final.assert_called_once()
            mock_ctx.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_tracking_with_custom_controller(self, mock_ctx, mock_monster, tracking_cog):
        cog = tracking_cog

        mock_member = Mock()
        mock_member.id = 99999
        mock_member.bot = False

        with patch("cogs5e.initiative.cog.commands.MemberConverter") as MockConverter:
            mock_converter = AsyncMock()
            mock_converter.convert = AsyncMock(return_value=mock_member)
            MockConverter.return_value = mock_converter

            async with mock_combat_add(mock_ctx):
                await cog._madd_impl(mock_ctx, mock_monster, "-controller @OtherUser")
                mock_ctx.bot.mdb.analytics_monster_usage.update_one.assert_called_once_with(
                    {"user_id": 12345, "monster_name": "Goblin", "monster_id": 1},
                    {"$inc": {"count": 1}, "$currentDate": {"last_used": True}},
                    upsert=True,
                )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
