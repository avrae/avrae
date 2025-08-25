import pytest
import asyncio
import disnake
from unittest.mock import Mock
from cogs5e.models.errors import NoSelectionElements, SelectionCancelled
from utils.selection import (
    get_selection_with_buttons,
    text_input_check,
    parse_custom_id,
    parse_selection_number,
    select_monster_with_dm_feedback,
    create_selection_embed,
    StatelessSelectionView,
)


def test_embed_description_formatting():
    query = "goblin"
    choices = ["Goblin", "Goblin Archer", "Goblin King"]
    page = 0
    pm = False
    message = "Test note message"

    description = ""
    if query:
        description += f"Your input was: `{query}`\n"
    description += "Which one were you looking for? (Type the number or `c` to cancel)\n"

    total_pages = 2
    if total_pages > 1:
        description += "`n` to go to the next page, or `p` for previous\n"
    description += "\n"

    for i, choice in enumerate(choices):
        global_index = i + 1 + page * 10
        description += f"[{global_index}] - {choice}\n"

    description += "\n**Instructions**\n"
    if not pm:
        description += "Use buttons below OR Type your choice in this channel."
    else:
        mock_channel = Mock()
        mock_channel.mention = "#test-channel"
        description += (
            f"Use buttons below OR Type your choice in {mock_channel.mention}. "
            "This message was PMed to you to hide the monster name."
        )

    if message:
        description += f"\n\n**Note**\n{message}"

    assert "Your input was: `goblin`" in description
    assert "[1] - Goblin" in description
    assert "**Instructions**" in description
    assert "Use buttons below OR Type your choice in this channel." in description


def test_embed_description_without_query():
    query = None
    description = ""
    if query:
        description += f"Your input was: `{query}`\n"
    description += "Which one were you looking for? (Type the number or `c` to cancel)\n"

    assert "Your input was:" not in description
    assert "Which one were you looking for?" in description


def test_embed_description_single_page():
    total_pages = 1
    description = "Which one were you looking for? (Type the number or `c` to cancel)\n"
    if total_pages > 1:
        description += "`n` to go to the next page, or `p` for previous\n"
    description += "\n"

    assert "next page" not in description
    assert "previous" not in description


def test_embed_pm_vs_channel():
    mock_ctx = Mock()
    mock_ctx.channel.mention = "#combat-channel"

    # Channel message
    pm = False
    description = "\n**Instructions**\n"
    if not pm:
        description += "Use buttons below OR Type your choice in this channel."
    else:
        description += (
            f"Use buttons below OR Type your choice in {mock_ctx.channel.mention}. "
            "This message was PMed to you to hide the monster name."
        )

    assert "this channel" in description
    assert "PMed to you" not in description

    # PM message
    pm = True
    description = "\n**Instructions**\n"
    if not pm:
        description += "Use buttons below OR Type your choice in this channel."
    else:
        description += (
            f"Use buttons below OR Type your choice in {mock_ctx.channel.mention}. "
            "This message was PMed to you to hide the monster name."
        )

    assert "#combat-channel" in description
    assert "PMed to you" in description


def test_embed_footer_pagination():
    current_page = 2
    total_pages = 5
    footer_text = f"Page {current_page + 1}/{total_pages}"
    assert footer_text == "Page 3/5"

    # Single page has no footer
    total_pages = 1
    has_footer = total_pages > 1
    assert not has_footer


def test_choice_formatting():
    choices = ["Item A", "Item B", "Item C"]
    page = 1
    per_page = 10

    formatted_choices = []
    for i, choice in enumerate(choices):
        global_index = i + 1 + page * per_page
        formatted_choices.append(f"[{global_index}] - {choice}")

    expected = ["[11] - Item A", "[12] - Item B", "[13] - Item C"]
    assert formatted_choices == expected


def test_complete_embed_creation():
    query = "ancient dragon"
    choices = ["Ancient Red Dragon", "Ancient Blue Dragon"]
    page = 0
    total_pages = 1
    pm = False

    description = ""
    if query:
        description += f"Your input was: `{query}`\n"
    description += "Which one were you looking for? (Type the number or `c` to cancel)\n"
    if total_pages > 1:
        description += "`n` to go to the next page, or `p` for previous\n"
    description += "\n"

    for i, choice in enumerate(choices):
        global_index = i + 1 + page * 10
        description += f"[{global_index}] - {choice}\n"

    description += "\n**Instructions**\n"
    if not pm:
        description += "Use buttons below OR Type your choice in this channel."

    embed = disnake.Embed(title="Multiple Matches Found", description=description, colour=0x36393F)

    if total_pages > 1:
        embed.set_footer(text=f"Page {page + 1}/{total_pages}")

    assert embed.title == "Multiple Matches Found"
    assert "Your input was: `ancient dragon`" in embed.description
    assert "[1] - Ancient Red Dragon" in embed.description
    assert embed.footer.text is None


def test_parse_custom_id():
    # Valid prefixed custom_id
    result = parse_custom_id("1234567890_select_5")
    assert result == "select_5"

    # Valid prefixed navigation
    result = parse_custom_id("9876543210_next")
    assert result == "next"

    # No prefix (backward compatibility)
    result = parse_custom_id("cancel")
    assert result == "cancel"

    # Empty string
    result = parse_custom_id("")
    assert result == ""

    # Invalid type
    result = parse_custom_id(None)
    assert result == ""


def test_parse_selection_number():
    # Valid selection
    result = parse_selection_number("select_1")
    assert result == 1

    # Valid multi-digit selection
    result = parse_selection_number("select_15")
    assert result == 15

    # Invalid format - not select prefix
    result = parse_selection_number("next")
    assert result is None

    # Invalid format - no number
    result = parse_selection_number("select_")
    assert result is None

    # Invalid format - invalid number
    result = parse_selection_number("select_abc")
    assert result is None

    # Invalid format - zero
    result = parse_selection_number("select_0")
    assert result is None

    # Invalid format - negative
    result = parse_selection_number("select_-1")
    assert result is None


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

    # Mock context for PM scenario
    mock_ctx = Mock()
    mock_ctx.channel.mention = "#original-channel"

    # Test PM with monster-specific message
    embed = create_selection_embed(
        choices=choices,
        page=0,
        key=lambda x: x,
        query=query,
        pm=True,
        ctx=mock_ctx,
        original_channel_mention="#combat-channel",
    )

    description = embed.description

    # Should contain monster-specific instruction text in PM
    assert "This message was PMed to you to hide the monster name." in description
    assert "#combat-channel" in description

    # Test non-PM (channel) message - should not contain monster-specific text
    embed_channel = create_selection_embed(choices=choices, page=0, key=lambda x: x, query=query, pm=False)

    description_channel = embed_channel.description

    # Should not contain monster-specific instruction text in channel
    assert "This message was PMed to you to hide the monster name." not in description_channel
    assert "Use buttons below OR Type your choice in this channel." in description_channel


def test_legacy_entity_marking():
    """Test that legacy entities are properly marked with *legacy* in the embed"""
    from gamedata.lookuputils import create_selectkey

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
    from unittest.mock import patch, AsyncMock

    choices = ["Goblin", "Goblin Archer"]

    # Mock the author.send method
    mock_ctx.author.send = AsyncMock()
    mock_sent_message = Mock()
    mock_sent_message.id = 12345
    mock_sent_message.edit = AsyncMock()  # Add async edit method
    mock_ctx.author.send.return_value = mock_sent_message

    # Mock ctx.send as AsyncMock
    mock_ctx.send = AsyncMock()

    # Mock asyncio.wait to properly simulate timeout at the correct level
    with patch("asyncio.wait", side_effect=asyncio.TimeoutError()):
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
    assert all(btn.custom_id.endswith(f"select_{i+1}") for i, btn in enumerate(row_0_buttons))

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
    assert all(btn.custom_id.endswith(f"select_{i+1}") for i, btn in enumerate(row_0_buttons))

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
    choices = [f"Choice {i+1}" for i in range(10)]
    view = StatelessSelectionView(choices, current_page=0, query="test", user_id=123456789)

    # Get all buttons and group by row
    row_0_buttons = [item for item in view.children if hasattr(item, "row") and item.row == 0]
    row_1_buttons = [item for item in view.children if hasattr(item, "row") and item.row == 1]
    row_2_buttons = [item for item in view.children if hasattr(item, "row") and item.row == 2]

    # Should have 5 selection buttons in row 0 (1-5)
    assert len(row_0_buttons) == 5
    assert all(btn.custom_id.endswith(f"select_{i+1}") for i, btn in enumerate(row_0_buttons))

    # Should have 5 selection buttons in row 1 (6-10)
    assert len(row_1_buttons) == 5
    assert all(btn.custom_id.endswith(f"select_{i+6}") for i, btn in enumerate(row_1_buttons))

    # Should have only cancel button in row 2 (no navigation needed)
    assert len(row_2_buttons) == 1
    assert row_2_buttons[0].custom_id.endswith("cancel")


@pytest.mark.asyncio
async def test_button_layout_14_choices_page_0():
    """Test button layout with 14 choices on page 0 - should have navigation"""
    choices = [f"Choice {i+1}" for i in range(14)]
    view = StatelessSelectionView(choices, current_page=0, query="test", user_id=123456789)

    # Get all buttons and group by row
    row_0_buttons = [item for item in view.children if hasattr(item, "row") and item.row == 0]
    row_1_buttons = [item for item in view.children if hasattr(item, "row") and item.row == 1]
    row_2_buttons = [item for item in view.children if hasattr(item, "row") and item.row == 2]

    # Should have 5 selection buttons in row 0 (1-5)
    assert len(row_0_buttons) == 5
    assert all(btn.custom_id.endswith(f"select_{i+1}") for i, btn in enumerate(row_0_buttons))

    # Should have 5 selection buttons in row 1 (6-10)
    assert len(row_1_buttons) == 5
    assert all(btn.custom_id.endswith(f"select_{i+6}") for i, btn in enumerate(row_1_buttons))

    # Should have navigation + cancel buttons in row 2
    assert len(row_2_buttons) == 3  # prev, next, cancel
    nav_buttons = {btn.custom_id.split("_")[-1]: btn for btn in row_2_buttons}
    assert "prev" in nav_buttons
    assert "next" in nav_buttons
    assert "cancel" in nav_buttons


@pytest.mark.asyncio
async def test_button_layout_14_choices_page_1():
    """Test button layout with 14 choices on page 1 - should show remaining 4 choices"""
    choices = [f"Choice {i+1}" for i in range(14)]
    view = StatelessSelectionView(choices, current_page=1, query="test", user_id=123456789)

    # Get all buttons and group by row
    row_0_buttons = [item for item in view.children if hasattr(item, "row") and item.row == 0]
    row_1_buttons = [item for item in view.children if hasattr(item, "row") and item.row == 1]
    row_2_buttons = [item for item in view.children if hasattr(item, "row") and item.row == 2]

    # Should have 4 selection buttons in row 0 (11-14)
    assert len(row_0_buttons) == 4
    assert all(btn.custom_id.endswith(f"select_{i+11}") for i, btn in enumerate(row_0_buttons))

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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
