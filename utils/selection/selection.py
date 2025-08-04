"""
Main selection functions for stateless button-based selection system.

This module provides the core selection logic that supports both
button interactions and text input, with complete statelessness for production use.
"""

import asyncio
import logging
from typing import List, Callable, Optional, Any

import disnake
from cogs5e.models.errors import NoSelectionElements, SelectionCancelled
from utils.pagination import get_total_pages
from . import constants
from .selection_helpers import (
    parse_custom_id,
    parse_selection_number,
    _check_navigation_boundary,
    text_input_check,
    _handle_navigation_txt_input,
)
from .selection_views import (
    StatelessSelectionView,
    create_selection_embed,
    update_selection_view,
    set_expired_view,
)

log = logging.getLogger(__name__)


# ==== main selection functions ====
async def get_selection_with_buttons(
    ctx,
    choices: List[Any],
    key: Callable[[Any], str] = lambda x: str(x),
    delete: bool = True,
    pm: bool = False,
    message: Optional[str] = None,
    force_select: bool = False,
    query: Optional[str] = None,
    timeout: float = constants.SELECTION_TIMEOUT,
) -> Any:
    """
    Stateless button selection: pure function replacement for get_selection.
    Supports both button interactions and text input simultaneously.

    Args:
        ctx: Discord context
        choices: List of choices to select from
        key: Function to get display string from choice
        delete: Whether to delete selection message after completion
        pm: Whether to send selection as private message
        message: Optional message to display in embed
        force_select: Force selection even with single choice
        query: Query that led to this selection
        timeout: Timeout in seconds

    Returns:
        Selected choice

    Raises:
        NoSelectionElements: If no choices provided
        SelectionCancelled: If user cancels or times out
    """

    if len(choices) == 0:
        raise NoSelectionElements()
    elif len(choices) == 1 and not force_select:
        return choices[0]

    # Store original channel mention before potential PM sending
    original_channel_mention = ctx.channel.mention if ctx.channel else None

    # Use optimized helper functions for consistent behavior
    def create_embed(page: int) -> disnake.Embed:
        return create_selection_embed(
            choices=choices,
            page=page,
            key=key,
            query=query,
            message=message,
            pm=pm,
            ctx=ctx,
            original_channel_mention=original_channel_mention,
        )

    page = 0
    total_pages = get_total_pages(choices, constants.CHOICES_PER_PAGE)
    embed = create_embed(page)
    view = StatelessSelectionView(choices, page, query or "", ctx.author.id)

    if pm:
        select_msg = await ctx.author.send(embed=embed, view=view)
    else:
        select_msg = await ctx.send(embed=embed, view=view)

    # Dual input handling loop
    updating_page = False

    event_count = 0
    while event_count < constants.MAX_EVENTS:
        try:
            done, pending = await asyncio.wait(
                [
                    asyncio.create_task(
                        ctx.bot.wait_for(
                            "interaction",
                            check=lambda i: i.message and i.message.id == select_msg.id and i.user.id == ctx.author.id,
                        )
                    ),
                    asyncio.create_task(
                        ctx.bot.wait_for("message", check=lambda msg: text_input_check(msg, ctx, choices))
                    ),
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

            if not done:
                break

            event_count += 1
            result = done.pop().result()

            if isinstance(result, disnake.Interaction):
                if not hasattr(result, "data"):
                    log.warning("Interaction missing 'data' attribute")
                    continue
                elif not result.data:
                    log.warning("Interaction has null/empty data")
                    continue
                elif not hasattr(result.data, "custom_id"):
                    log.warning("Interaction data missing 'custom_id' attribute")
                    continue

                action = parse_custom_id(result.data.custom_id)

                if action == constants.ACTION_CANCEL:
                    await result.response.defer()
                    break
                elif action in (constants.ACTION_NEXT, constants.ACTION_PREV):
                    if updating_page:
                        continue

                    updating_page = True

                    try:
                        boundary, msg = _check_navigation_boundary(action, page, total_pages)
                        if boundary:
                            await result.response.send_message(msg, ephemeral=True)
                            updating_page = False
                            continue

                        await result.response.defer()
                    except disnake.HTTPException as e:
                        updating_page = False
                        log.exception(f"Discord API error during navigation: {e}")
                        continue
                    except Exception as e:
                        updating_page = False
                        log.exception(f"Unexpected error during navigation: {e}")
                        raise

                    target_page = page + 1 if action == constants.ACTION_NEXT else page - 1
                    try:
                        page = target_page
                        await update_selection_view(select_msg, choices, page, query or "", create_embed, ctx.author.id)
                    finally:
                        updating_page = False
                    continue
                elif action.startswith(constants.ACTION_SELECT_PREFIX):
                    selection_num = parse_selection_number(action)
                    if selection_num is None:
                        log.debug(f"Invalid selection action format: '{action}'")
                        continue

                    choice_idx = selection_num - 1
                    if 0 <= choice_idx < len(choices):
                        selected_choice = choices[choice_idx]

                        if not delete or pm:
                            await set_expired_view(select_msg, choices, page, query or "", ctx.author.id)

                        if delete and not pm:
                            try:
                                await select_msg.delete()
                            except disnake.HTTPException as e:
                                log.debug(f"Expected HTTPException during selection message deletion: {e}")
                        return selected_choice
                    else:
                        continue

            else:
                content = result.content.lower().strip()

                if content == constants.TEXT_CMD_CANCEL:
                    if delete and not pm:
                        try:
                            await result.delete()
                        except disnake.HTTPException as e:
                            log.debug(f"Expected HTTPException during text message deletion: {e}")
                    break
                elif content in (constants.TEXT_CMD_NEXT, constants.TEXT_CMD_PREV):
                    new_page = await _handle_navigation_txt_input(ctx, content, page, total_pages)
                    if new_page == page:
                        continue
                    page = new_page
                else:
                    try:
                        choice_idx = int(content) - 1
                        if 0 <= choice_idx < len(choices):
                            selected_choice = choices[choice_idx]

                            if delete and not pm:
                                try:
                                    await select_msg.delete()
                                    await result.delete()
                                except disnake.HTTPException as e:
                                    log.debug(f"Expected HTTPException during cleanup deletion: {e}")
                            return selected_choice
                    except ValueError:
                        continue

                if content in (constants.TEXT_CMD_NEXT, constants.TEXT_CMD_PREV):
                    updating_page = True
                    try:
                        await update_selection_view(select_msg, choices, page, query or "", create_embed, ctx.author.id)
                        if delete and not pm:
                            try:
                                await result.delete()
                            except disnake.HTTPException as e:
                                log.debug(f"Expected HTTPException during navigation cleanup: {e}")
                    finally:
                        updating_page = False
                    continue

        except asyncio.TimeoutError:
            break
        except disnake.HTTPException as e:
            log.exception(f"Discord API error in selection loop: {e}")
            break
        except Exception as e:
            log.exception(f"Unexpected error in selection loop: {e}")
            break

    if not delete or pm:
        await set_expired_view(select_msg, choices, page, query or "", ctx.author.id)

    if delete and not pm:
        try:
            await select_msg.delete()
        except disnake.HTTPException as e:
            log.debug(f"HTTPException when deleting selection message: {e}")

    raise SelectionCancelled()
