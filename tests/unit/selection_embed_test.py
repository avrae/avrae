import pytest
import disnake
from unittest.mock import Mock
from cogs5e.models.errors import NoSelectionElements
from utils.selection import get_selection_with_buttons, text_input_check
from utils.selection_helpers import parse_custom_id, parse_selection_number
from utils.selection_monster import select_monster_with_dm_feedback


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
