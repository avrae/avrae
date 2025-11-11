"""
Monster-specific selection logic with DM feedback.

This module contains the specialized monster selection function that provides
enhanced UX for combat encounters, including DM feedback and ephemeral messages.
"""

import logging
import time
from typing import List, Callable, Optional, Any

import disnake
from cogs5e.models.errors import NoSelectionElements
from . import constants
from .selection_helpers import _handle_selection_loop
from .selection_views import (
    StatelessSelectionView,
    create_pm_selection_embed,
)

log = logging.getLogger(__name__)


async def _send_dm_notification(ctx, select_msg) -> None:
    """Send notification to original channel about DM selection menu."""
    delete_time = int(time.time()) + constants.DM_NOTIFICATION_TIMEOUT
    await ctx.send(
        f"> Monster selection menu sent to your DMs: {select_msg.jump_url}\n"
        f"> This message will disappear <t:{delete_time}:R>",
        delete_after=constants.DM_NOTIFICATION_TIMEOUT,
    )


async def select_monster_with_dm_feedback(
    ctx,
    choices: List[Any],
    key: Callable[[Any], str] = lambda x: str(x),
    query: Optional[str] = None,
    madd_callback: Optional[Callable] = None,
    args: str = "",
    timeout: float = constants.SELECTION_TIMEOUT,
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

    def create_embed(page: int) -> disnake.Embed:
        return create_pm_selection_embed(
            choices=choices,
            page=page,
            key=key,
            query=query,
            original_channel_mention=original_channel_mention,
        )

    page = 0
    embed = create_embed(page)
    view = StatelessSelectionView(choices, page, query or "", ctx.author.id)
    select_msg = await ctx.author.send(embed=embed, view=view)
    await _send_dm_notification(ctx, select_msg)

    choice, interaction = await _handle_selection_loop(
        ctx,
        select_msg,
        choices,
        query or "",
        create_embed,
        timeout,
        delete_on_select=False,
        pm=True,
    )

    if interaction is not None:
        try:
            combat_channel = ctx.channel.mention
            await interaction.followup.send(f"✅ Adding **{key(choice)}** to combat in {combat_channel}!")
        except disnake.HTTPException:
            pass

    if madd_callback:
        await madd_callback(ctx, choice, args)
        return None
    return choice
