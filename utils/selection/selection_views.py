"""
Discord UI components for the selection system.
"""

import random
from typing import List, Callable, Optional, Any

import disnake
from utils.pagination import get_page_choices, get_total_pages
from . import constants


class StatelessSelectionView(disnake.ui.View):
    """
    Completely stateless selection view that creates buttons based on current state.

    This view generates pagination and selection buttons dynamically without storing
    state between interactions. Each button uses the user ID as a custom_id prefix
    to prevent cross-user interference in shared channels.

    Attributes:
        expired: Whether the view has expired (disables all buttons)
        user_id: ID of the user who can interact with this view

    Button Layout:
        - Row 0: Selection buttons 1-MAX_BUTTONS_PER_ROW
        - Row 1: Selection buttons (MAX_BUTTONS_PER_ROW+1)-(MAX_BUTTONS_PER_ROW*2)
        - Row 2: Previous/Next navigation (if >CHOICES_PER_PAGE choices) + Cancel button
    """

    def __init__(self, choices: List[Any], current_page: int, query: str, user_id: int, expired: bool = False):
        super().__init__(timeout=constants.SELECTION_TIMEOUT)
        self.expired = expired
        self.user_id = user_id
        self.setup_buttons(choices, current_page, query)

    def _create_selection_buttons(
        self, start_idx: int, end_idx: int, current_choices: List[Any], current_page: int, prefix: str, row: int
    ) -> None:
        """Create selection buttons for a given range, only for actual choices."""
        for i in range(start_idx, min(end_idx, len(current_choices))):
            global_index = i + 1 + current_page * constants.CHOICES_PER_PAGE
            button = disnake.ui.Button(
                label=str(global_index),
                style=disnake.ButtonStyle.secondary,
                disabled=self.expired,
                custom_id=f"{prefix}{constants.ACTION_SELECT_PREFIX}{global_index}",
                row=row,
            )
            self.add_item(button)

    async def interaction_check(self, interaction: disnake.Interaction) -> bool:
        """Ensure only the authorized user can interact with this view."""
        if interaction.user.id == self.user_id:
            return True
        await interaction.response.send_message(constants.ERROR_UNAUTHORIZED_USER, ephemeral=True)
        return False

    def setup_buttons(self, choices: List[Any], current_page: int, query: str) -> None:
        """Setup buttons based on current state parameters with optimized layout and unique custom_ids."""
        total_pages = get_total_pages(choices, constants.CHOICES_PER_PAGE)
        current_choices = (
            get_page_choices(choices, current_page, constants.CHOICES_PER_PAGE) if current_page < total_pages else []
        )
        prefix = f"{self.user_id}_"

        # Row 0: Selection buttons 1-MAX_BUTTONS_PER_ROW
        self._create_selection_buttons(
            0, constants.MAX_BUTTONS_PER_ROW, current_choices, current_page, prefix, constants.SELECTION_ROW_1
        )
        # Row 1: Selection buttons (MAX_BUTTONS_PER_ROW+1)-(MAX_BUTTONS_PER_ROW*2)
        self._create_selection_buttons(
            constants.MAX_BUTTONS_PER_ROW,
            constants.MAX_BUTTONS_PER_ROW * 2,
            current_choices,
            current_page,
            prefix,
            constants.SELECTION_ROW_2,
        )

        # Row 2: Navigation and Cancel buttons
        if len(choices) > constants.CHOICES_PER_PAGE:
            # Previous button
            prev_button = disnake.ui.Button(
                label=constants.BUTTON_LABEL_PREVIOUS,
                style=disnake.ButtonStyle.secondary,
                disabled=self.expired,
                custom_id=f"{prefix}{constants.ACTION_PREV}",
                row=constants.NAVIGATION_ROW,
            )
            self.add_item(prev_button)

            # Next button
            next_button = disnake.ui.Button(
                label=constants.BUTTON_LABEL_NEXT,
                style=disnake.ButtonStyle.secondary,
                disabled=self.expired,
                custom_id=f"{prefix}{constants.ACTION_NEXT}",
                row=constants.NAVIGATION_ROW,
            )
            self.add_item(next_button)

        # Cancel button - always in row 2
        cancel_button = disnake.ui.Button(
            label=constants.BUTTON_LABEL_CANCEL,
            style=disnake.ButtonStyle.danger,
            disabled=self.expired,
            custom_id=f"{prefix}{constants.ACTION_CANCEL}",
            row=constants.NAVIGATION_ROW,
        )
        self.add_item(cancel_button)


def create_selection_embed(
    choices: List[Any],
    page: int,
    key: Callable[[Any], str],
    query: Optional[str] = None,
    message: Optional[str] = None,
    pm: bool = False,
    ctx=None,
    original_channel_mention: Optional[str] = None,
) -> disnake.Embed:
    """
    Create a standardized selection embed for any choice list.

    Args:
        choices: Full list of choices available for selection
        page: Current page number (0-indexed)
        key: Function to convert choice to display string
        query: Original query that led to this selection
        message: Optional additional message to display
        pm: Whether this is being sent as a private message
        ctx: Discord context (required if pm=True)
        original_channel_mention: Channel mention for DM instruction text

    Returns:
        Formatted embed ready for display
    """
    total_pages = get_total_pages(choices, constants.CHOICES_PER_PAGE)
    current_choices = get_page_choices(choices, page, constants.CHOICES_PER_PAGE) if page < total_pages else []

    description_parts = []

    # Query display
    if query:
        description_parts.append(f"Your input was: `{query}`")

    # Base instructions
    description_parts.append(constants.EMBED_INSTRUCTION_BASE)

    # Navigation hint for multi-page
    if total_pages > 1:
        description_parts.append(constants.EMBED_INSTRUCTION_NAVIGATION)

    description_parts.append("")  # Empty line before choices

    # Choice list with consistent formatting
    for i, choice in enumerate(current_choices):
        global_index = i + 1 + page * constants.CHOICES_PER_PAGE
        description_parts.append(f"[{global_index}] - {key(choice)}")

    # Interaction instructions
    description_parts.append("\n**Instructions**")
    if pm and ctx:
        # Handle DM channel mention issue - ctx.channel.mention can be None in DMs
        channel_ref = original_channel_mention or "the original channel"
        description_parts.append(
            f"Use buttons below OR Type your choice in {channel_ref}. " + constants.MSG_PM_EXPLANATION
        )
    else:
        description_parts.append("Use buttons below OR Type your choice in this channel.")

    # Add selection menu ownership indicator (only for non-PM embeds)
    if ctx and not pm:
        command_name = getattr(ctx, "invoked_with", None) or "command"
        prefix = getattr(ctx, "prefix", "!")
        full_command = f"{prefix}{command_name}"
        description_parts.append(f"This `{full_command}` selection menu works only for <@{ctx.author.id}>")

    # Additional message if provided
    if message:
        description_parts.append(f"\n**Note**\n{message}")

    embed = disnake.Embed(
        title=constants.EMBED_TITLE_MULTIPLE_MATCHES,
        description="\n".join(description_parts),
        colour=random.randint(0, 0xFFFFFF),
    )

    # Page footer for multi-page results
    if total_pages > 1:
        embed.set_footer(text=f"Page {page + 1}/{total_pages}")

    return embed


async def update_selection_view(
    select_msg, choices: list, page: int, query: str, create_embed_func, user_id: int
) -> None:
    """Helper to update selection message with new page and view."""
    embed = create_embed_func(page)
    view = StatelessSelectionView(choices, page, query, user_id)
    await select_msg.edit(embed=embed, view=view)


async def set_expired_view(select_msg, choices: list, page: int, query: str, user_id: int) -> None:
    """Helper to set expired view on selection message."""
    import logging

    log = logging.getLogger(__name__)

    try:
        expired_view = StatelessSelectionView(choices, page, query, user_id, expired=True)
        await select_msg.edit(view=expired_view)
    except Exception as e:  # Using Exception to avoid importing disnake.HTTPException
        # Expected - message might already be deleted or edited
        log.debug(f"Exception when setting expired view: {e}")
