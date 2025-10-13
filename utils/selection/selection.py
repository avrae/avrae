"""Main selection functions for stateless button-based selection system."""

import logging
from typing import List, Callable, Optional, Any

import disnake
from cogs5e.models.errors import NoSelectionElements
from . import constants
from .selection_helpers import _handle_selection_loop
from .selection_views import (
    StatelessSelectionView,
    create_selection_embed,
    create_pm_selection_embed,
)

log = logging.getLogger(__name__)


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

    original_channel_mention = getattr(ctx.channel, "mention", None) if ctx.channel else None

    def create_embed(page: int) -> disnake.Embed:
        if pm:
            return create_pm_selection_embed(
                choices=choices,
                page=page,
                key=key,
                query=query,
                original_channel_mention=original_channel_mention,
            )
        else:
            return create_selection_embed(
                choices=choices,
                page=page,
                key=key,
                query=query,
                message=message,
                ctx=ctx,
            )

    page = 0
    embed = create_embed(page)
    view = StatelessSelectionView(choices, page, query or "", ctx.author.id)

    if pm:
        select_msg = await ctx.author.send(embed=embed, view=view)
    else:
        select_msg = await ctx.send(embed=embed, view=view)

    choice, _interaction = await _handle_selection_loop(
        ctx,
        select_msg,
        choices,
        query or "",
        create_embed,
        timeout,
        delete_on_select=delete and not pm,
        pm=pm,
    )
    return choice
