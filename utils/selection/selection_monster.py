"""
Monster-specific selection logic with DM feedback.

This module contains the specialized monster selection function that provides
enhanced UX for combat encounters, including DM feedback and ephemeral messages.
"""

import asyncio
import logging
import time
from typing import List, Callable, Optional, Any

import disnake
from cogs5e.models.errors import NoSelectionElements, SelectionCancelled
from utils.pagination import get_total_pages
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

# Constants
SELECTION_TIMEOUT = 60.0
DM_NOTIFICATION_TIMEOUT = 15
MAX_EVENTS = 100


async def _send_dm_notification(ctx, select_msg) -> None:
    """Send notification to original channel about DM selection menu."""
    delete_time = int(time.time()) + DM_NOTIFICATION_TIMEOUT
    await ctx.send(
        f"> Monster selection menu sent to your DMs: {select_msg.jump_url}\n"
        f"> This message will disappear <t:{delete_time}:R>",
        delete_after=DM_NOTIFICATION_TIMEOUT,
    )


async def select_monster_with_dm_feedback(
    ctx,
    choices: List[Any],
    key: Callable[[Any], str] = lambda x: str(x),
    query: Optional[str] = None,
    madd_callback: Optional[Callable] = None,
    args: str = "",
    timeout: float = SELECTION_TIMEOUT,
) -> Any:
    """
    Optimized monster selection with ephemeral DM feedback.

    This function is specifically designed for btn madd to provide:
    1. Efficient button-based selection using existing stateless framework
    2. Ephemeral DM message with combat channel link upon selection
    3. Uses standard StatelessSelectionView with 2 rows of 5 buttons each
    4. Hidden nav for ≤10 results

    Args:
        ctx: Discord context
        choices: List of monster choices
        key: Function to get display string from choice
        query: Query that led to this selection
        madd_callback: Async function to call with selected monster
        args: Arguments to pass to madd_callback
        timeout: Timeout in seconds

    Returns:
        Selected choice (or None if handled via callback)

    Raises:
        NoSelectionElements: If no choices provided
        SelectionCancelled: If user cancels or times out
    """

    if len(choices) == 0:
        raise NoSelectionElements()
    elif len(choices) == 1:
        if madd_callback:
            await madd_callback(ctx, choices[0], args)
            return None
        return choices[0]

    original_channel_mention = ctx.channel.mention if ctx.channel else None

    # Use optimized helper functions for consistent monster selection behavior
    def create_embed(page: int) -> disnake.Embed:
        return create_selection_embed(
            choices=choices,
            page=page,
            key=key,
            query=query,
            pm=True,
            ctx=ctx,
            original_channel_mention=original_channel_mention,
        )

    # Send selection message to DM
    page = 0
    total_pages = get_total_pages(choices, 10)
    embed = create_embed(page)

    # Create view with user ID for uniqueness - eliminates race condition window
    view = StatelessSelectionView(choices, page, query or "", ctx.author.id)
    select_msg = await ctx.author.send(embed=embed, view=view)
    await _send_dm_notification(ctx, select_msg)

    # Dual input handling - buttons OR text
    updating_page = False  # Atomic flag to prevent rapid click race conditions

    event_count = 0
    while event_count < MAX_EVENTS:  # Prevent runaway loops, typical use should be <5 events
        try:
            # Wait for either interaction or text message
            done, pending = await asyncio.wait(
                [
                    asyncio.create_task(
                        ctx.bot.wait_for(
                            "interaction",
                            check=lambda i: i.message and i.message.id == select_msg.id,
                        )
                    ),
                    asyncio.create_task(
                        ctx.bot.wait_for("message", check=lambda msg: text_input_check(msg, ctx, choices))
                    ),
                ],
                return_when=asyncio.FIRST_COMPLETED,
                timeout=timeout,
            )

            # Cancel pending tasks and wait for completion
            for task in pending:
                task.cancel()
                try:
                    await task  # Ensure cancellation completes
                except asyncio.CancelledError:
                    pass  # Expected when task is cancelled

            if not done:  # Timeout
                break

            event_count += 1
            result = done.pop().result()

            if isinstance(result, disnake.Interaction):
                if not hasattr(result, "data") or not result.data or not hasattr(result.data, "custom_id"):
                    log.warning("Monster interaction missing required data fields")
                    continue

                action = parse_custom_id(result.data.custom_id)

                if action == "cancel":
                    await result.response.send_message("Monster selection cancelled.", ephemeral=True)
                    break
                elif action in ("next", "prev"):
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

                    target_page = page + 1 if action == "next" else page - 1
                    try:
                        page = target_page
                        await update_selection_view(select_msg, choices, page, query or "", create_embed, ctx.author.id)
                    finally:
                        updating_page = False
                    continue
                elif action.startswith("select_"):
                    selection_num = parse_selection_number(action)
                    if selection_num is None:
                        log.warning(f"Invalid monster selection action format: {action}")
                        await result.response.send_message("Invalid selection format.", ephemeral=True)
                        continue

                    choice_idx = selection_num - 1
                    if 0 <= choice_idx < len(choices):
                        selected_monster = choices[choice_idx]

                        combat_channel = ctx.channel.mention
                        await result.response.send_message(
                            f"✅ Adding **{key(selected_monster)}** to combat in {combat_channel}!", ephemeral=True
                        )

                        await set_expired_view(select_msg, choices, page, query or "", ctx.author.id)

                        if madd_callback:
                            await madd_callback(ctx, selected_monster, args)
                            return None

                        return selected_monster
                    else:
                        log.warning(f"Monster selection number {selection_num} out of range (1-{len(choices)})")
                        await result.response.send_message("Selection out of range.", ephemeral=True)
                        continue

            else:
                content = result.content.lower().strip()

                if content == "c":
                    break
                elif content in ("n", "p"):
                    new_page = await _handle_navigation_txt_input(ctx, content, page, total_pages)
                    if new_page == page:
                        continue
                    page = new_page
                else:
                    try:
                        choice_idx = int(content) - 1
                        if 0 <= choice_idx < len(choices):
                            selected_monster = choices[choice_idx]

                            await set_expired_view(select_msg, choices, page, query or "", ctx.author.id)

                            if madd_callback:
                                await madd_callback(ctx, selected_monster, args)
                                return None
                            return selected_monster
                    except ValueError:
                        continue

                if content in ("n", "p"):
                    updating_page = True
                    try:
                        await update_selection_view(select_msg, choices, page, query or "", create_embed, ctx.author.id)
                    finally:
                        updating_page = False
                    continue

        except asyncio.TimeoutError:
            break
        except disnake.HTTPException as e:
            log.exception(f"Discord API error in monster selection loop: {e}")
            break
        except Exception as e:
            log.exception(f"Unexpected error in monster selection loop: {e}")
            break

    await set_expired_view(select_msg, choices, page, query or "", ctx.author.id)

    raise SelectionCancelled()
