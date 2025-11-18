import pytest
import asyncio
import json
import disnake
from unittest.mock import Mock, AsyncMock
from cogs5e.models.errors import NoSelectionElements, SelectionCancelled
from gamedata.lookuputils import create_selectkey
from utils.selection import (
    get_selection_with_buttons,
    text_input_check,
    select_monster_with_dm_feedback,
    create_selection_embed,
    create_pm_selection_embed,
    StatelessSelectionView,
)
from utils.selection.selection_helpers import (
    _RedisInteraction,
    _wait_for_input,
    _handle_button_selection,
    _handle_button_navigation,
)


def test_embed_description_formatting():
    choices = ["Goblin", "Goblin Archer", "Goblin King"]
    embed = create_selection_embed(
        choices=choices, page=0, key=lambda x: x, query="goblin", message="Test note message"
    )

    assert embed.title == "Multiple Matches Found"
    assert "Your input was: `goblin`" in embed.description
    assert "[1] - Goblin" in embed.description
    assert "[2] - Goblin Archer" in embed.description
    assert "[3] - Goblin King" in embed.description
    assert "**Instructions**" in embed.description
    assert "Use buttons below OR Type your choice in this channel." in embed.description
    assert "**Note**\nTest note message" in embed.description


def test_embed_description_without_query():
    choices = ["Choice 1", "Choice 2"]
    embed = create_selection_embed(choices=choices, page=0, key=lambda x: x, query=None)

    assert "Your input was:" not in embed.description
    assert "Which one were you looking for?" in embed.description


def test_embed_description_single_page():
    choices = ["Single Choice"]  # Only 1 choice = 1 page
    embed = create_selection_embed(choices=choices, page=0, key=lambda x: x)

    assert "next page" not in embed.description
    assert "previous" not in embed.description
    assert embed.footer.text is None  # No footer for single page


def test_embed_pm_vs_channel():
    choices = ["Choice 1", "Choice 2"]
    mock_ctx = Mock()
    mock_ctx.author = Mock()
    mock_ctx.author.id = 123456

    # Channel message
    embed_channel = create_selection_embed(choices=choices, page=0, key=lambda x: x, ctx=mock_ctx)

    assert "this channel" in embed_channel.description
    assert "PMed to you" not in embed_channel.description
    assert "selection menu works only for <@123456>" in embed_channel.description

    # PM message
    embed_pm = create_pm_selection_embed(
        choices=choices, page=0, key=lambda x: x, original_channel_mention="#combat-channel"
    )

    assert "#combat-channel" in embed_pm.description
    assert "PMed to you" in embed_pm.description
    assert "selection menu works only for" not in embed_pm.description  # No ownership text in PM


def test_embed_footer_pagination():
    # Multi-page scenario (15 choices = 2 pages at 10 per page)
    choices = [f"Choice {i + 1}" for i in range(15)]
    embed_multi = create_selection_embed(choices=choices, page=1, key=lambda x: x)  # Second page (0-indexed)

    assert embed_multi.footer.text == "Page 2/2"

    # Single page has no footer
    single_choices = ["Single Choice"]
    embed_single = create_selection_embed(choices=single_choices, page=0, key=lambda x: x)

    assert embed_single.footer.text is None


def test_choice_formatting():
    # Create 13 total choices so page 1 will have choices 11-13
    all_choices = [f"Item {chr(65 + i)}" for i in range(13)]  # Item A through Item M
    embed = create_selection_embed(choices=all_choices, page=1, key=lambda x: x)  # Second page (0-indexed)

    # On page 1, we should see choices 11-13 (global indices)
    assert "[11] - Item K" in embed.description
    assert "[12] - Item L" in embed.description
    assert "[13] - Item M" in embed.description
    # Should not see first page items
    assert "[1] - Item A" not in embed.description


def test_complete_embed_creation():
    choices = ["Ancient Red Dragon", "Ancient Blue Dragon"]
    embed = create_selection_embed(choices=choices, page=0, key=lambda x: x, query="ancient dragon")

    assert embed.title == "Multiple Matches Found"
    assert "Your input was: `ancient dragon`" in embed.description
    assert "[1] - Ancient Red Dragon" in embed.description
    assert "[2] - Ancient Blue Dragon" in embed.description
    assert "Which one were you looking for?" in embed.description
    assert "Use buttons below OR Type your choice in this channel." in embed.description
    assert embed.footer.text is None  # Single page, no footer
    assert embed.colour is not None  # Should have a random color


def test_text_input_check_valid_inputs():
    # Setup mocks
    mock_ctx = Mock()
    mock_ctx.author = Mock()
    mock_ctx.channel = Mock()

    mock_msg = Mock()
    mock_msg.author = mock_ctx.author
    mock_msg.channel = mock_ctx.channel

    choices = ["choice1", "choice2", "choice3"]

    # Valid navigation commands
    mock_msg.content = "c"
    assert text_input_check(mock_msg, mock_ctx, choices) is True

    mock_msg.content = "n"
    assert text_input_check(mock_msg, mock_ctx, choices) is True

    mock_msg.content = "p"
    assert text_input_check(mock_msg, mock_ctx, choices) is True

    # Valid selections
    mock_msg.content = "1"
    assert text_input_check(mock_msg, mock_ctx, choices) is True

    mock_msg.content = "3"
    assert text_input_check(mock_msg, mock_ctx, choices) is True


def test_text_input_check_invalid_inputs():
    # Setup mocks
    mock_ctx = Mock()
    mock_ctx.author = Mock()
    mock_ctx.channel = Mock()

    mock_msg = Mock()
    mock_msg.author = mock_ctx.author
    mock_msg.channel = mock_ctx.channel

    choices = ["choice1", "choice2"]

    # Invalid selection numbers
    mock_msg.content = "0"
    assert text_input_check(mock_msg, mock_ctx, choices) is False

    mock_msg.content = "3"
    assert text_input_check(mock_msg, mock_ctx, choices) is False

    mock_msg.content = "abc"
    assert text_input_check(mock_msg, mock_ctx, choices) is False

    # Wrong author
    mock_msg.author = Mock()
    mock_msg.content = "1"
    assert text_input_check(mock_msg, mock_ctx, choices) is False

    # Wrong channel
    mock_msg.author = mock_ctx.author
    mock_msg.channel = Mock()
    assert text_input_check(mock_msg, mock_ctx, choices) is False


def test_text_input_check_case_insensitive():
    # Setup mocks
    mock_ctx = Mock()
    mock_ctx.author = Mock()
    mock_ctx.channel = Mock()

    mock_msg = Mock()
    mock_msg.author = mock_ctx.author
    mock_msg.channel = mock_ctx.channel

    choices = ["choice1"]

    # Case insensitive commands
    mock_msg.content = "C"
    assert text_input_check(mock_msg, mock_ctx, choices) is True

    mock_msg.content = "N"
    assert text_input_check(mock_msg, mock_ctx, choices) is True

    mock_msg.content = "P"
    assert text_input_check(mock_msg, mock_ctx, choices) is True


# === Basic Behavioral Tests ===


@pytest.fixture
def mock_ctx():
    """Create a mock Discord context"""
    ctx = Mock()
    ctx.author = Mock()
    ctx.author.id = 123456789
    ctx.channel = Mock()
    ctx.channel.mention = "#test-channel"
    return ctx


@pytest.mark.asyncio
async def test_empty_choices_behavior(mock_ctx):
    """Verify both functions raise NoSelectionElements for empty choices"""
    with pytest.raises(NoSelectionElements):
        await get_selection_with_buttons(mock_ctx, [])

    with pytest.raises(NoSelectionElements):
        await select_monster_with_dm_feedback(mock_ctx, [])


@pytest.mark.asyncio
async def test_single_choice_behavior(mock_ctx):
    """Verify single choice behavior for both functions"""
    single_choice = ["Only Choice"]

    # get_selection_with_buttons should return the choice directly
    result = await get_selection_with_buttons(mock_ctx, single_choice)
    assert result == "Only Choice"

    # select_monster_with_dm_feedback should also return the choice when no callback
    result = await select_monster_with_dm_feedback(mock_ctx, single_choice)
    assert result == "Only Choice"


def test_monster_specific_instruction_text():
    """Test that monster selection shows monster-specific instruction text"""
    choices = ["Choice 1", "Choice 2"]
    query = "test query"

    # Test PM with monster-specific message
    embed = create_pm_selection_embed(
        choices=choices,
        page=0,
        key=lambda x: x,
        query=query,
        original_channel_mention="#combat-channel",
    )

    description = embed.description

    # Should contain monster-specific instruction text in PM
    assert "This message was PMed to you to hide the monster name." in description
    assert "#combat-channel" in description

    # Test non-PM (channel) message - should not contain monster-specific text
    embed_channel = create_selection_embed(choices=choices, page=0, key=lambda x: x, query=query)

    description_channel = embed_channel.description

    # Should not contain monster-specific instruction text in channel
    assert "This message was PMed to you to hide the monster name." not in description_channel
    assert "Use buttons below OR Type your choice in this channel." in description_channel


def test_legacy_entity_marking():
    """Test that legacy entities are properly marked with *legacy* in the embed"""
    # Mock legacy entity
    legacy_monster = Mock()
    legacy_monster.name = "Ancient Goblin"
    legacy_monster.is_legacy = True
    legacy_monster.homebrew = False
    legacy_monster.source = "PHB"
    legacy_monster.entity_id = 1
    legacy_monster.limited_use_only = False
    legacy_monster.entitlement_entity_type = "monster"

    # Mock non-legacy entity
    modern_monster = Mock()
    modern_monster.name = "Goblin"
    modern_monster.is_legacy = False
    modern_monster.homebrew = False
    modern_monster.source = "PHB"
    modern_monster.entity_id = 2
    modern_monster.limited_use_only = False
    modern_monster.entitlement_entity_type = "monster"

    # Create selectkey function
    available_ids = {"monster": {1, 2}}
    selectkey_func = create_selectkey(available_ids)

    # Test legacy marking
    legacy_display = selectkey_func(legacy_monster, slash=False)
    modern_display = selectkey_func(modern_monster, slash=False)

    assert "*legacy*" in legacy_display
    assert "*legacy*" not in modern_display
    assert "Ancient Goblin" in legacy_display
    assert "Goblin" in modern_display


@pytest.mark.asyncio
async def test_monster_dm_feedback_embed_behavior(mock_ctx):
    """Test embed creation when using DM feedback for monsters"""
    choices = ["Goblin", "Goblin Archer"]

    # Mock the author.send method
    mock_ctx.author.send = AsyncMock()
    mock_sent_message = Mock()
    mock_sent_message.id = 12345
    mock_sent_message.edit = AsyncMock()  # Add async edit method
    mock_ctx.author.send.return_value = mock_sent_message

    # Mock ctx.send as AsyncMock
    mock_ctx.send = AsyncMock()

    # Mock ctx.bot.wait_for to properly return coroutines
    mock_ctx.bot = Mock()
    mock_ctx.bot.wait_for = AsyncMock(side_effect=asyncio.TimeoutError())

    # Test that the function attempts to send DM and handles timeout properly
    with pytest.raises(SelectionCancelled):
        await select_monster_with_dm_feedback(
            ctx=mock_ctx,
            choices=choices,
            key=lambda x: x,
            query="goblin",
            timeout=0.1,  # Very short timeout for test
        )

    # Verify DM was sent with proper embed
    mock_ctx.author.send.assert_called_once()
    call_args = mock_ctx.author.send.call_args

    # Verify embed was created (first positional argument should be embed)
    assert "embed" in call_args[1]
    embed = call_args[1]["embed"]
    assert embed.title == "Multiple Matches Found"
    assert "goblin" in embed.description.lower()

    # Verify view was included
    assert "view" in call_args[1]


# === Button Layout Tests ===


@pytest.mark.asyncio
async def test_button_layout_4_choices():
    """Test button layout with 4 choices - should only use row 0 and row 2"""
    choices = ["Choice 1", "Choice 2", "Choice 3", "Choice 4"]
    view = StatelessSelectionView(choices, current_page=0, query="test", user_id=123456789)

    # Get all buttons and group by row
    row_0_buttons = [item for item in view.children if hasattr(item, "row") and item.row == 0]
    row_1_buttons = [item for item in view.children if hasattr(item, "row") and item.row == 1]
    row_2_buttons = [item for item in view.children if hasattr(item, "row") and item.row == 2]

    # Should have 4 selection buttons in row 0
    assert len(row_0_buttons) == 4
    assert all(btn.custom_id.endswith(f"select_{i + 1}") for i, btn in enumerate(row_0_buttons))

    # Should have no buttons in row 1
    assert len(row_1_buttons) == 0

    # Should have only cancel button in row 2 (no navigation needed)
    assert len(row_2_buttons) == 1
    assert row_2_buttons[0].custom_id.endswith("cancel")
    assert row_2_buttons[0].label == "Cancel"


@pytest.mark.asyncio
async def test_button_layout_7_choices():
    """Test button layout with 7 choices - should use row 0, row 1, and row 2"""
    choices = ["Choice 1", "Choice 2", "Choice 3", "Choice 4", "Choice 5", "Choice 6", "Choice 7"]
    view = StatelessSelectionView(choices, current_page=0, query="test", user_id=123456789)

    # Get all buttons and group by row
    row_0_buttons = [item for item in view.children if hasattr(item, "row") and item.row == 0]
    row_1_buttons = [item for item in view.children if hasattr(item, "row") and item.row == 1]
    row_2_buttons = [item for item in view.children if hasattr(item, "row") and item.row == 2]

    # Should have 5 selection buttons in row 0 (1-5)
    assert len(row_0_buttons) == 5
    assert all(btn.custom_id.endswith(f"select_{i + 1}") for i, btn in enumerate(row_0_buttons))

    # Should have 2 selection buttons in row 1 (6-7)
    assert len(row_1_buttons) == 2
    assert row_1_buttons[0].custom_id.endswith("select_6")
    assert row_1_buttons[1].custom_id.endswith("select_7")

    # Should have only cancel button in row 2 (no navigation needed)
    assert len(row_2_buttons) == 1
    assert row_2_buttons[0].custom_id.endswith("cancel")


@pytest.mark.asyncio
async def test_button_layout_10_choices():
    """Test button layout with exactly 10 choices - should fill rows 0 and 1"""
    choices = [f"Choice {i + 1}" for i in range(10)]
    view = StatelessSelectionView(choices, current_page=0, query="test", user_id=123456789)

    # Get all buttons and group by row
    row_0_buttons = [item for item in view.children if hasattr(item, "row") and item.row == 0]
    row_1_buttons = [item for item in view.children if hasattr(item, "row") and item.row == 1]
    row_2_buttons = [item for item in view.children if hasattr(item, "row") and item.row == 2]

    # Should have 5 selection buttons in row 0 (1-5)
    assert len(row_0_buttons) == 5
    assert all(btn.custom_id.endswith(f"select_{i + 1}") for i, btn in enumerate(row_0_buttons))

    # Should have 5 selection buttons in row 1 (6-10)
    assert len(row_1_buttons) == 5
    assert all(btn.custom_id.endswith(f"select_{i + 6}") for i, btn in enumerate(row_1_buttons))

    # Should have only cancel button in row 2 (no navigation needed)
    assert len(row_2_buttons) == 1
    assert row_2_buttons[0].custom_id.endswith("cancel")


@pytest.mark.asyncio
async def test_button_layout_14_choices_page_0():
    """Test button layout with 14 choices on page 0 - should have navigation"""
    choices = [f"Choice {i + 1}" for i in range(14)]
    view = StatelessSelectionView(choices, current_page=0, query="test", user_id=123456789)

    # Get all buttons and group by row
    row_0_buttons = [item for item in view.children if hasattr(item, "row") and item.row == 0]
    row_1_buttons = [item for item in view.children if hasattr(item, "row") and item.row == 1]
    row_2_buttons = [item for item in view.children if hasattr(item, "row") and item.row == 2]

    # Should have 5 selection buttons in row 0 (1-5)
    assert len(row_0_buttons) == 5
    assert all(btn.custom_id.endswith(f"select_{i + 1}") for i, btn in enumerate(row_0_buttons))

    # Should have 5 selection buttons in row 1 (6-10)
    assert len(row_1_buttons) == 5
    assert all(btn.custom_id.endswith(f"select_{i + 6}") for i, btn in enumerate(row_1_buttons))

    # Should have navigation + cancel buttons in row 2
    assert len(row_2_buttons) == 3  # prev, next, cancel
    nav_buttons = {btn.custom_id.split("_")[-1]: btn for btn in row_2_buttons}
    assert "prev" in nav_buttons
    assert "next" in nav_buttons
    assert "cancel" in nav_buttons


@pytest.mark.asyncio
async def test_button_layout_14_choices_page_1():
    """Test button layout with 14 choices on page 1 - should show remaining 4 choices"""
    choices = [f"Choice {i + 1}" for i in range(14)]
    view = StatelessSelectionView(choices, current_page=1, query="test", user_id=123456789)

    # Get all buttons and group by row
    row_0_buttons = [item for item in view.children if hasattr(item, "row") and item.row == 0]
    row_1_buttons = [item for item in view.children if hasattr(item, "row") and item.row == 1]
    row_2_buttons = [item for item in view.children if hasattr(item, "row") and item.row == 2]

    # Should have 4 selection buttons in row 0 (11-14)
    assert len(row_0_buttons) == 4
    assert all(btn.custom_id.endswith(f"select_{i + 11}") for i, btn in enumerate(row_0_buttons))

    # Should have no buttons in row 1 (page 1 only has 4 items)
    assert len(row_1_buttons) == 0

    # Should have navigation + cancel buttons in row 2
    assert len(row_2_buttons) == 3  # prev, next, cancel
    nav_buttons = {btn.custom_id.split("_")[-1]: btn for btn in row_2_buttons}
    assert "prev" in nav_buttons
    assert "next" in nav_buttons
    assert "cancel" in nav_buttons


@pytest.mark.asyncio
async def test_no_placeholder_buttons():
    """Test that no disabled placeholder buttons are created"""
    choices = ["Choice 1", "Choice 2", "Choice 3"]
    view = StatelessSelectionView(choices, current_page=0, query="test", user_id=123456789)

    # Get all buttons
    all_buttons = [item for item in view.children if hasattr(item, "custom_id")]

    # Should have exactly 4 buttons: 3 selections + 1 cancel (no placeholders)
    assert len(all_buttons) == 4

    # No button should be disabled except for expired state
    enabled_buttons = [btn for btn in all_buttons if not btn.disabled]
    assert len(enabled_buttons) == 4  # All should be enabled when not expired

    # No button should have placeholder in custom_id
    placeholder_buttons = [btn for btn in all_buttons if "placeholder" in btn.custom_id]
    assert len(placeholder_buttons) == 0


@pytest.mark.asyncio
async def test_expired_view_disables_buttons():
    """Test that expired view properly disables all buttons"""
    choices = ["Choice 1", "Choice 2", "Choice 3"]
    view = StatelessSelectionView(choices, current_page=0, query="test", user_id=123456789, expired=True)

    # Get all buttons
    all_buttons = [item for item in view.children if hasattr(item, "disabled")]

    # All buttons should be disabled when expired
    assert all(btn.disabled for btn in all_buttons)


@pytest.mark.asyncio
async def test_button_custom_id_format():
    """Test that button custom_ids follow the expected format"""
    choices = ["Choice 1", "Choice 2"]
    user_id = 987654321
    view = StatelessSelectionView(choices, current_page=0, query="test", user_id=user_id)

    # Get all buttons
    all_buttons = [item for item in view.children if hasattr(item, "custom_id")]

    # All custom_ids should start with user_id prefix
    for button in all_buttons:
        assert button.custom_id.startswith(f"{user_id}_")

    # Find selection buttons and verify format
    selection_buttons = [btn for btn in all_buttons if "select_" in btn.custom_id]
    assert len(selection_buttons) == 2
    assert selection_buttons[0].custom_id == f"{user_id}_select_1"
    assert selection_buttons[1].custom_id == f"{user_id}_select_2"

    # Find cancel button
    cancel_buttons = [btn for btn in all_buttons if btn.custom_id.endswith("_cancel")]
    assert len(cancel_buttons) == 1
    assert cancel_buttons[0].custom_id == f"{user_id}_cancel"


# === Cross-Shard DM Interaction Tests ===


@pytest.mark.asyncio
async def test_redis_interaction_construction():
    """_RedisInteraction builds from cache data, defer is no-op, followup works"""
    mock_bot = Mock()
    mock_channel = Mock()
    mock_channel.send = AsyncMock(return_value=Mock())
    mock_bot.get_channel = Mock(return_value=mock_channel)

    data = {"custom_id": "123_select_1", "message_id": "789", "user_id": "456", "channel_id": "999"}
    interaction = _RedisInteraction(data, mock_bot)

    assert interaction.data.custom_id == "123_select_1"
    assert interaction.message.id == 789
    assert interaction.user.id == 456
    assert interaction._from_redis is True
    await interaction.response.defer()

    await interaction.followup.send("test")
    mock_channel.send.assert_called_once()
    assert mock_channel.send.call_args[1]["reference"].message_id == 789


@pytest.mark.asyncio
async def test_wait_for_input_cache_paths():
    """Cache hit skips subscribe, cache miss uses pubsub, both delete cache"""

    # Create a wait_for that never completes (to let pubsub path win)
    async def never_completes(*args, **kwargs):
        await asyncio.sleep(10)

    def setup_ctx():
        ctx = Mock()
        ctx.bot = Mock(shard_id=0, wait_for=AsyncMock(side_effect=never_completes))
        ctx.author = Mock(id=123)
        return ctx

    ctx1 = setup_ctx()
    cached = json.dumps({"message_id": "789", "user_id": "123", "custom_id": "x", "channel_id": "999"})
    ctx1.bot.rdb = Mock(getdel=AsyncMock(return_value=cached), subscribe=AsyncMock())

    result1 = await _wait_for_input(ctx1, Mock(id=789), ["c1"], 30)
    assert result1._from_redis is True
    ctx1.bot.rdb.subscribe.assert_not_called()
    ctx1.bot.rdb.getdel.assert_called_once()

    # Cache miss -> pubsub path
    ctx2 = setup_ctx()

    async def mock_get_message(ignore_subscribe_messages=False, timeout=None):
        await asyncio.sleep(0.01)
        return {"type": "message"}

    pubsub = Mock(get_message=AsyncMock(side_effect=mock_get_message), unsubscribe=AsyncMock(), close=AsyncMock())
    ctx2.bot.rdb = Mock(
        getdel=AsyncMock(side_effect=[None, cached]),  # First None (pre-check), then cached (after pubsub message)
        subscribe=AsyncMock(return_value=pubsub),
    )

    result2 = await _wait_for_input(ctx2, Mock(id=789), ["c1"], 30)
    assert result2._from_redis is True
    ctx2.bot.rdb.subscribe.assert_called_once()
    pubsub.unsubscribe.assert_called_once()
    assert ctx2.bot.rdb.getdel.call_count == 2  # Pre-check + pubsub path


@pytest.mark.asyncio
async def test_defer_skipped_for_redis_interactions():
    """Redis interactions skip defer in button selection and navigation"""
    local = Mock(response=Mock(defer=AsyncMock(), send_message=AsyncMock()))
    local._from_redis = False
    local.data = Mock(custom_id="123_select_1")
    await _handle_button_selection(local, "select_1", ["c1"], False)
    local.response.defer.assert_called_once()

    redis = Mock(_from_redis=True, response=Mock(defer=AsyncMock()), followup=Mock(send=AsyncMock()))
    redis.data = Mock(custom_id="456_select_1")
    await _handle_button_selection(redis, "select_1", ["c1"], False)
    redis.response.defer.assert_not_called()

    local2 = Mock(response=Mock(send_message=AsyncMock()))
    local2._from_redis = False
    local2.data = Mock(custom_id="789_prev")
    await _handle_button_navigation(local2, "prev", 0, 5)
    assert local2.response.send_message.call_args[1]["ephemeral"] is True

    redis2 = Mock(_from_redis=True, followup=Mock(send=AsyncMock()))
    redis2.data = Mock(custom_id="999_next")
    await _handle_button_navigation(redis2, "next", 4, 5)
    redis2.followup.send.assert_called_once()


@pytest.mark.asyncio
async def test_redis_errors_graceful():
    """Redis failures don't crash, on_interaction filter logic"""

    async def never_completes(*args, **kwargs):
        await asyncio.sleep(10)

    ctx = Mock(bot=Mock(shard_id=0, wait_for=AsyncMock(side_effect=never_completes)), author=Mock(id=123))
    ctx.bot.rdb = Mock(get=AsyncMock(side_effect=Exception("fail")), subscribe=AsyncMock(side_effect=Exception("fail")))

    result = await _wait_for_input(ctx, Mock(id=789), ["c1"], 0.1)
    assert result is None

    def should_process_interaction(interaction):
        """Simulate dbot.py on_interaction filter"""
        if (
            interaction.guild_id is not None
            or interaction.type != disnake.InteractionType.component
            or not interaction.message
            or not interaction.user
        ):
            return False
        return True

    def make_interaction(guild_id, interaction_type, has_message, has_user):
        i = Mock()
        i.guild_id = guild_id
        i.type = interaction_type
        i.message = Mock() if has_message else None
        i.user = Mock() if has_user else None
        return i

    assert should_process_interaction(make_interaction(123, disnake.InteractionType.component, True, True)) is False
    assert (
        should_process_interaction(make_interaction(None, disnake.InteractionType.application_command, True, True))
        is False
    )
    assert should_process_interaction(make_interaction(None, disnake.InteractionType.component, False, True)) is False
    assert should_process_interaction(make_interaction(None, disnake.InteractionType.component, True, False)) is False
    assert should_process_interaction(make_interaction(None, disnake.InteractionType.component, True, True)) is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
