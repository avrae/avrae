"""
Helper utilities for the selection system.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import List, Optional, Any, Callable

import disnake
from cogs5e.models.errors import SelectionCancelled
from utils.pagination import get_total_pages
from .selection_views import update_selection_view, set_expired_view
from . import constants

log = logging.getLogger(__name__)


@dataclass
class SelectionAction:
    """Result of handling user input."""

    type: str  # "select", "cancel", "navigate", "ignore"
    choice: Any = None
    page: int = 0
    message: Optional[Any] = None  # Text message to delete
    interaction: Optional[Any] = None  # Interaction for button selections


def _check_navigation_boundary(action: str, page: int, total_pages: int) -> tuple[bool, str]:
    """Check if navigation would hit boundary and return appropriate emoji message."""
    if action in ("next", "n") and page >= total_pages - 1:
        return True, "⏭ You're already on the **last** page."
    if action in ("prev", "p") and page == 0:
        return True, "⏮ You're already on the **first** page."
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
    if msg.author != ctx.author or msg.channel != ctx.channel:
        return False

    content = msg.content.lower().strip()

    if content in ("c", "n", "p"):
        return True

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
        return page

    if content == "n":
        return page + 1
    elif content == "p":
        return page - 1
    return page


async def _safe_delete(*messages) -> None:
    """Safely delete message(s), ignoring HTTPException if they occur."""
    for msg in messages:
        try:
            await msg.delete()
        except disnake.HTTPException:
            pass


async def _wait_for_input(ctx, select_msg, choices, timeout):
    """Wait for either button interaction or text message."""
    done, pending = await asyncio.wait(
        [
            asyncio.create_task(
                ctx.bot.wait_for(
                    "interaction",
                    check=lambda i: (i.message and i.message.id == select_msg.id and i.user.id == ctx.author.id),
                )
            ),
            asyncio.create_task(ctx.bot.wait_for("message", check=lambda msg: text_input_check(msg, ctx, choices))),
        ],
        return_when=asyncio.FIRST_COMPLETED,
        timeout=timeout,
    )

    for task in pending:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    if done:
        task = done.pop()
        try:
            return task.result()
        except asyncio.TimeoutError:
            return None
    return None


async def _handle_button_navigation(interaction, action, page, total_pages):
    """Handle next/prev button navigation."""
    boundary, msg = _check_navigation_boundary(action, page, total_pages)
    if boundary:
        try:
            await interaction.response.send_message(msg, ephemeral=True)
        except disnake.HTTPException:
            pass
        return SelectionAction(type="ignore")

    try:
        await interaction.response.defer()
    except disnake.HTTPException:
        pass

    new_page = page + 1 if action == "next" else page - 1
    return SelectionAction(type="navigate", page=new_page)


async def _handle_button_selection(interaction, action, choices, pm):
    """Handle button selection."""
    if not isinstance(action, str) or not action.startswith("select_"):
        return SelectionAction(type="ignore")

    parts = action.split("_")
    if len(parts) != 2:
        return SelectionAction(type="ignore")

    try:
        selection_num = int(parts[1])
        if selection_num <= 0:
            return SelectionAction(type="ignore")
    except ValueError:
        return SelectionAction(type="ignore")

    choice_idx = selection_num - 1
    if not 0 <= choice_idx < len(choices):
        return SelectionAction(type="ignore")

    selected_choice = choices[choice_idx]

    # Defer interaction to prevent timeout, use ephemeral for PM to allow ephemeral followup
    try:
        await interaction.response.defer(ephemeral=pm)
    except disnake.HTTPException:
        pass

    return SelectionAction(type="select", choice=selected_choice, interaction=interaction)


async def _handle_button_interaction(interaction, page, total_pages, choices, pm):
    """
    Handle button interaction and return action to take.

    Returns: SelectionAction(type="select"|"cancel"|"navigate", choice=..., page=...)
    """
    try:
        custom_id = interaction.data.custom_id
        if not isinstance(custom_id, str):
            return SelectionAction(type="ignore")
        parts = custom_id.split("_", 1)
        action = parts[1] if len(parts) > 1 else custom_id
    except (AttributeError, TypeError):
        return SelectionAction(type="ignore")

    if action == "cancel":
        await interaction.response.defer()
        return SelectionAction(type="cancel")

    if action in ("next", "prev"):
        return await _handle_button_navigation(interaction, action, page, total_pages)

    if action.startswith("select_"):
        return await _handle_button_selection(interaction, action, choices, pm)

    return SelectionAction(type="ignore")


async def _handle_text_input(ctx, message, page, total_pages, choices):
    """
    Handle text message input and return action to take.

    Returns: SelectionAction(type="select"|"cancel"|"navigate", choice=..., page=...)
    """
    content = message.content.lower().strip()

    if content == "c":
        return SelectionAction(type="cancel", message=message)

    if content in ("n", "p"):
        new_page = await _handle_navigation_txt_input(ctx, content, page, total_pages)
        if new_page == page:
            return SelectionAction(type="ignore")
        return SelectionAction(type="navigate", page=new_page, message=message)

    try:
        choice_idx = int(content) - 1
        if 0 <= choice_idx < len(choices):
            selected_choice = choices[choice_idx]
            return SelectionAction(type="select", choice=selected_choice, message=message)
    except ValueError:
        pass

    return SelectionAction(type="ignore")


async def _finalize_selection(select_msg, action, page, choices, query, user_id, delete_on_select, pm):
    """Clean up UI and return selected choice and interaction (if button was used)."""
    if not delete_on_select or pm:
        await set_expired_view(select_msg, choices, page, query, user_id)

    if delete_on_select and not pm:
        messages_to_delete = [select_msg]
        if action.message:
            messages_to_delete.append(action.message)
        await _safe_delete(*messages_to_delete)

    return action.choice, action.interaction


async def _handle_selection_loop(
    ctx,
    select_msg,
    choices: List[Any],
    query: str,
    create_embed_func: Callable,
    timeout: float,
    *,
    delete_on_select: bool = True,
    pm: bool = False,
) -> Any:
    """
    Core selection event loop with dual input support.

    Args:
        ctx: Discord context
        select_msg: The message containing the selection embed/view
        choices: List of choices to select from
        query: Query string for the selection
        create_embed_func: Function(page) -> Embed to create embed for each page
        timeout: Timeout in seconds
        delete_on_select: Whether to delete messages on selection
        pm: Whether this is a PM selection

    Returns:
        Tuple of (selected choice, interaction or None)
        - interaction is the button interaction if selection was via button
        - interaction is None if selection was via text

    Raises:
        SelectionCancelled: If user cancels or times out
    """
    page = 0
    total_pages = get_total_pages(choices, constants.CHOICES_PER_PAGE)
    event_count = 0

    while event_count < constants.MAX_EVENTS:
        try:
            result = await _wait_for_input(ctx, select_msg, choices, timeout)
            if result is None:
                break

            event_count += 1

            if isinstance(result, disnake.Interaction):
                action = await _handle_button_interaction(result, page, total_pages, choices, pm)
            else:
                action = await _handle_text_input(ctx, result, page, total_pages, choices)

            if action.type == "cancel":
                break
            elif action.type == "select":
                return await _finalize_selection(
                    select_msg, action, page, choices, query, ctx.author.id, delete_on_select, pm
                )
            elif action.type == "navigate":
                page = action.page
                await update_selection_view(select_msg, choices, page, query, create_embed_func, ctx.author.id)
                if delete_on_select and not pm and action.message:
                    await _safe_delete(action.message)

        except disnake.HTTPException as e:
            log.debug(f"Discord API error in selection loop: {e}")
            break

    if not delete_on_select or pm:
        await set_expired_view(select_msg, choices, page, query, ctx.author.id)
    if delete_on_select and not pm:
        await _safe_delete(select_msg)

    raise SelectionCancelled()
