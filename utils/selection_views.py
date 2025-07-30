"""
Discord UI components for the selection system.
"""

import random
from typing import List, Callable, Optional, Any

import disnake
from utils.pagination import get_page_choices, get_total_pages


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
        - Rows 1-2: Selection buttons 1-10 (5 per row)
        - Row 3: Previous/Next navigation (if >10 choices)
        - Row 3: Cancel button
    """

    def __init__(self, choices: List[Any], current_page: int, query: str, user_id: int, expired: bool = False):
        super().__init__(timeout=60.0)
        self.expired = expired
        self.user_id = user_id
        self.setup_buttons(choices, current_page, query)

    def _create_selection_buttons(
        self, start_idx: int, end_idx: int, current_choices: List[Any], current_page: int, prefix: str
    ) -> None:
        """Create selection buttons for a given range."""
        for i in range(start_idx, end_idx):
            if i < len(current_choices):
                global_index = i + 1 + current_page * 10
                button = disnake.ui.Button(
                    label=str(global_index),
                    style=disnake.ButtonStyle.secondary,
                    disabled=self.expired,
                    custom_id=f"{prefix}select_{global_index}",
                )
            else:
                button = disnake.ui.Button(
                    label=str(i + 1 + current_page * 10),
                    style=disnake.ButtonStyle.secondary,
                    disabled=True,
                    custom_id=f"{prefix}placeholder_{i}",
                )
            self.add_item(button)

    async def interaction_check(self, interaction: disnake.Interaction) -> bool:
        """Ensure only the authorized user can interact with this view."""
        if interaction.user.id == self.user_id:
            return True
        await interaction.response.send_message(
            "This menu belongs to someone else. Please start your own command to make a selection.", ephemeral=True
        )
        return False

    def setup_buttons(self, choices: List[Any], current_page: int, query: str) -> None:
        """Setup buttons based on current state parameters with optimized layout and unique custom_ids."""
        total_pages = get_total_pages(choices, 10)
        current_choices = get_page_choices(choices, current_page, 10) if current_page < total_pages else []
        prefix = f"{self.user_id}_"

        # Rows 1-2: Selection buttons 1-10
        self._create_selection_buttons(0, 5, current_choices, current_page, prefix)
        self._create_selection_buttons(5, 10, current_choices, current_page, prefix)

        # Row 3: Navigation buttons (only show if more than 10 total results)
        if len(choices) > 10:
            # Previous button
            prev_button = disnake.ui.Button(
                label="◀ Previous",
                style=disnake.ButtonStyle.secondary,
                disabled=self.expired,
                custom_id=f"{prefix}prev",
            )
            self.add_item(prev_button)

            # Next button
            next_button = disnake.ui.Button(
                label="Next ▶",
                style=disnake.ButtonStyle.secondary,
                disabled=self.expired,
                custom_id=f"{prefix}next",
            )
            self.add_item(next_button)

        # Cancel button - clean styling
        cancel_button = disnake.ui.Button(
            label="Cancel", style=disnake.ButtonStyle.danger, disabled=self.expired, custom_id=f"{prefix}cancel"
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
    total_pages = get_total_pages(choices, 10)
    current_choices = get_page_choices(choices, page, 10) if page < total_pages else []

    description_parts = []

    # Query display
    if query:
        description_parts.append(f"Your input was: `{query}`")

    # Base instructions
    description_parts.append("Which one were you looking for? (Type the number or `c` to cancel)")

    # Navigation hint for multi-page
    if total_pages > 1:
        description_parts.append("`n` to go to the next page, or `p` for previous")

    description_parts.append("")  # Empty line before choices

    # Choice list with consistent formatting
    for i, choice in enumerate(current_choices):
        global_index = i + 1 + page * 10
        description_parts.append(f"[{global_index}] - {key(choice)}")

    # Interaction instructions
    description_parts.append("\n**Instructions**")
    if pm and ctx:
        # Handle DM channel mention issue - ctx.channel.mention can be None in DMs
        channel_ref = original_channel_mention or "the original channel"
        description_parts.append(
            f"Use buttons below OR Type your choice in {channel_ref}. "
            "This message was PMed to you to hide the monster name."
        )
    else:
        description_parts.append("Use buttons below OR Type your choice in this channel.")

    # Additional message if provided
    if message:
        description_parts.append(f"\n**Note**\n{message}")

    embed = disnake.Embed(
        title="Multiple Matches Found", description="\n".join(description_parts), colour=random.randint(0, 0xFFFFFF)
    )

    # Page footer for multi-page results
    if total_pages > 1:
        embed.set_footer(text=f"Page {page + 1}/{total_pages}")

    return embed
