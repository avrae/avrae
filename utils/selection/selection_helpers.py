"""
Helper utilities for the selection system.
"""

import logging
from typing import List, Optional, Any

from . import constants

log = logging.getLogger(__name__)


def parse_custom_id(custom_id: str) -> str:
    """
    Extract the action from a prefixed custom_id.

    Args:
        custom_id: The full custom_id (e.g., "1234567890_select_1")

    Returns:
        The action part (e.g., "select_1")
    """
    if not isinstance(custom_id, str):
        log.debug(f"Invalid custom_id type received: expected str, got {type(custom_id).__name__}")
        return ""

    parts = custom_id.split("_", 1)
    return parts[1] if len(parts) > 1 else custom_id


def parse_selection_number(action: str) -> Optional[int]:
    """
    Safely extract selection number from action string.

    Args:
        action: Action string (e.g., "select_1", "select_10")

    Returns:
        Selection number (1-based) or None if invalid
    """
    if not isinstance(action, str) or not action.startswith(constants.ACTION_SELECT_PREFIX):
        return None

    parts = action.split("_")
    if len(parts) != 2:
        return None

    try:
        selection_num = int(parts[1])
        return selection_num if selection_num > 0 else None
    except ValueError:
        return None


def _check_navigation_boundary(action: str, page: int, total_pages: int) -> tuple[bool, str]:
    """Check if navigation would hit boundary and return appropriate emoji message."""
    if action in (constants.ACTION_NEXT, constants.TEXT_CMD_NEXT) and page >= total_pages - 1:
        return True, constants.MSG_ALREADY_LAST_PAGE
    if action in (constants.ACTION_PREV, constants.TEXT_CMD_PREV) and page == 0:
        return True, constants.MSG_ALREADY_FIRST_PAGE
    return False, ""


def text_input_check(msg, ctx, choices: List[Any]) -> bool:
    """
    Standardized message check function for text input handling.

    Args:
        msg: The message to check
        ctx: Discord context for author and channel validation
        choices: Full list of choices to validate selection against

    Returns:
        True if message is a valid input, False otherwise
    """
    # Fast early rejection for different authors/channels
    if msg.author != ctx.author or msg.channel != ctx.channel:
        return False

    content = msg.content.lower().strip()

    # Navigation and cancel commands
    if content in (constants.TEXT_CMD_CANCEL, constants.TEXT_CMD_NEXT, constants.TEXT_CMD_PREV):
        return True

    # Numeric selection validation
    try:
        choice_num = int(content)
        return 1 <= choice_num <= len(choices)
    except ValueError:
        return False


async def _handle_navigation_txt_input(ctx, content: str, page: int, total_pages: int) -> int:
    """Handle navigation text input (n/p) with boundary checks and error messages."""
    boundary, msg = _check_navigation_boundary(content, page, total_pages)
    if boundary:
        await ctx.send(msg, delete_after=5)
        return page  # No change

    if content == constants.TEXT_CMD_NEXT:
        return page + 1
    elif content == constants.TEXT_CMD_PREV:
        return page - 1
    return page  # Unknown command, no change
