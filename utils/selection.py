"""
Stateless button-based selection system.

This module provides a drop-in replacement for get_selection that supports both
button interactions and text input, with complete statelessness for production use.
"""

import asyncio
from typing import List, Callable, Optional, Any

import disnake
from utils.functions import paginate
from cogs5e.models.errors import NoSelectionElements, SelectionCancelled


class StatelessSelectionView(disnake.ui.View):
    """
    Completely stateless selection view that creates buttons based on current state.
    """

    def __init__(self, choices: List[Any], current_page: int, selectkey: Callable, query: str, expired: bool = False):
        super().__init__(timeout=60.0)
        self.expired = expired
        self.setup_buttons(choices, current_page, selectkey, query)

    def setup_buttons(self, choices: List[Any], current_page: int, selectkey: Callable, query: str):
        """Setup buttons based on current state parameters with optimized layout."""
        pages = paginate(choices, 10)
        current_choices = pages[current_page] if current_page < len(pages) else []
        total_pages = len(pages)

        # Row 1: Selection buttons 1-5 (fill with placeholders if needed)
        for i in range(5):
            if i < len(current_choices):
                global_index = i + 1 + current_page * 10
                button = disnake.ui.Button(
                    label=str(global_index),
                    style=disnake.ButtonStyle.secondary,
                    disabled=self.expired,
                    custom_id=f"select_{global_index}",
                )
            else:
                # Placeholder button when insufficient choices
                button = disnake.ui.Button(
                    label=str(i + 1 + current_page * 10),
                    style=disnake.ButtonStyle.secondary,
                    disabled=True,
                    custom_id=f"placeholder_{i}",
                )
            self.add_item(button)

        # Row 2: Selection buttons 6-10 (fill with placeholders if needed)
        for i in range(5, 10):
            if i < len(current_choices):
                global_index = i + 1 + current_page * 10
                button = disnake.ui.Button(
                    label=str(global_index),
                    style=disnake.ButtonStyle.secondary,
                    disabled=self.expired,
                    custom_id=f"select_{global_index}",
                )
            else:
                # Placeholder button when insufficient choices
                button = disnake.ui.Button(
                    label=str(i + 1 + current_page * 10),
                    style=disnake.ButtonStyle.secondary,
                    disabled=True,
                    custom_id=f"placeholder_{i}",
                )
            self.add_item(button)

        # Row 3: Navigation buttons (only show if more than 10 total results)
        if len(choices) > 10:
            # Previous button
            prev_button = disnake.ui.Button(
                label="◀ Previous",
                style=disnake.ButtonStyle.secondary,
                disabled=(current_page == 0 or self.expired),
                custom_id="prev",
            )
            self.add_item(prev_button)

            # Next button
            next_button = disnake.ui.Button(
                label="Next ▶",
                style=disnake.ButtonStyle.secondary,
                disabled=(current_page >= total_pages - 1 or self.expired),
                custom_id="next",
            )
            self.add_item(next_button)

        # Cancel button - clean styling
        cancel_button = disnake.ui.Button(
            label="Cancel", style=disnake.ButtonStyle.danger, disabled=self.expired, custom_id="cancel"
        )
        self.add_item(cancel_button)

    async def interaction_check(self, interaction: disnake.MessageInteraction) -> bool:
        """Handle interactions on expired views (just in case)"""
        if self.expired:
            await interaction.response.send_message("⏰ This selection menu has expired.", ephemeral=True)
            return False
        return True


async def get_selection_with_buttons(
    ctx,
    choices: List[Any],
    key: Callable[[Any], str] = lambda x: str(x),
    delete: bool = True,
    pm: bool = False,
    message: Optional[str] = None,
    force_select: bool = False,
    query: Optional[str] = None,
    timeout: float = 120.0,
    is_monster: bool = False,
) -> Any:
    """
    Stateless button selection: pure function replacement for get_selection.
    Supports both button interactions and text input simultaneously.

    Provides monster-specific optimizations when is_monster=True:
    - Ephemeral DM feedback with combat channel link
    - 2-row button layout with proper nav states
    - Hidden nav for ≤10 results
    - Expired menu handling

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
        is_monster: Whether this is monster selection (enables special UX)

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

    # Use specialized monster selection if requested
    if is_monster and pm:
        return await select_monster_with_dm_feedback(ctx=ctx, choices=choices, key=key, query=query, timeout=timeout)

    def create_embed(page: int) -> disnake.Embed:
        """Create selection embed for given page."""
        pages = paginate(choices, 10)
        current_choices = pages[page] if page < len(pages) else []

        description = ""
        if query:
            description += f"Your input was: `{query}`\n"
        description += "Which one were you looking for? (Type the number or `c` to cancel)\n"
        if len(pages) > 1:
            description += "`n` to go to the next page, or `p` for previous\n"
        description += "\n"

        for i, choice in enumerate(current_choices):
            global_index = i + 1 + page * 10
            description += f"[{global_index}] - {key(choice)}\n"

        description += "\n**Instructions**\n"
        if not pm:
            description += "Use buttons below OR Type your choice in this channel."
        else:
            description += f"Use buttons below OR Type your choice in {ctx.channel.mention}. This message was PMed to you to hide the monster name."

        if message:
            description += f"\n\n**Note**\n{message}"

        embed = disnake.Embed(title="Multiple Matches Found", description=description, colour=0x36393F)

        if len(pages) > 1:
            embed.set_footer(text=f"Page {page + 1}/{len(pages)}")

        return embed

    def create_text_check():
        """Create message check function for text input."""

        def text_check(msg):
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

        return text_check

    # Send initial message with buttons
    page = 0
    pages = paginate(choices, 10)
    embed = create_embed(page)
    view = StatelessSelectionView(choices, page, key, query or "")

    if pm:
        embed.add_field(name="Instructions", value=f"Click buttons or type in {ctx.channel.mention}", inline=False)
        select_msg = await ctx.author.send(embed=embed, view=view)
    else:
        select_msg = await ctx.send(embed=embed, view=view)

    # Dual input handling loop - buttons OR text
    text_check = create_text_check()
    current_timeout = timeout

    while True:
        try:
            # Wait for either interaction or text message
            done, pending = await asyncio.wait(
                [
                    asyncio.create_task(
                        ctx.bot.wait_for(
                            "interaction",
                            check=lambda i: i.message and i.message.id == select_msg.id and i.user.id == ctx.author.id,
                        )
                    ),
                    asyncio.create_task(ctx.bot.wait_for("message", check=text_check)),
                ],
                return_when=asyncio.FIRST_COMPLETED,
                timeout=current_timeout,
            )

            # Cancel any pending tasks
            for task in pending:
                task.cancel()

            if not done:  # Timeout occurred
                break

            result = done.pop().result()

            if isinstance(result, disnake.Interaction):
                # Handle button interaction
                await result.response.defer()
                action = result.data.custom_id

                if action == "cancel":
                    break
                elif action == "next":
                    page = min(page + 1, len(pages) - 1)
                elif action == "prev":
                    page = max(page - 1, 0)
                elif action.startswith("select_"):
                    # Selection made via button
                    try:
                        choice_idx = int(action.split("_")[1]) - 1
                        if 0 <= choice_idx < len(choices):
                            selected_choice = choices[choice_idx]

                            # Create expired view before deletion/return
                            try:
                                if not delete or pm:
                                    expired_view = StatelessSelectionView(choices, page, key, query or "", expired=True)
                                    await select_msg.edit(view=expired_view)
                            except disnake.HTTPException:
                                pass

                            if delete and not pm:
                                await select_msg.delete()
                            return selected_choice
                    except (ValueError, IndexError):
                        continue  # Invalid selection, continue loop

                # Update view for navigation (next/prev)
                if action in ("next", "prev"):
                    embed = create_embed(page)
                    view = StatelessSelectionView(choices, page, key, query or "")
                    await select_msg.edit(embed=embed, view=view)
                    current_timeout = timeout  # Fresh timeout for new page
                    continue

            else:
                # Handle text message
                content = result.content.lower().strip()

                if content == "c":
                    # Cancel via text
                    if delete and not pm:
                        await result.delete()
                    break
                elif content == "n":
                    # Next page via text
                    if page >= len(pages) - 1:
                        await ctx.send("You are already on the last page.", delete_after=5)
                        continue
                    page = min(page + 1, len(pages) - 1)
                elif content == "p":
                    # Previous page via text
                    if page <= 0:
                        await ctx.send("You are already on the first page.", delete_after=5)
                        continue
                    page = max(page - 1, 0)
                else:
                    # Selection made via text
                    try:
                        choice_idx = int(content) - 1
                        if 0 <= choice_idx < len(choices):
                            selected_choice = choices[choice_idx]

                            if delete and not pm:
                                await select_msg.delete()
                                await result.delete()
                            return selected_choice
                    except ValueError:
                        continue  # Invalid input, continue loop

                # Update view for navigation (n/p commands)
                if content in ("n", "p"):
                    embed = create_embed(page)
                    view = StatelessSelectionView(choices, page, key, query or "")
                    await select_msg.edit(embed=embed, view=view)
                    current_timeout = timeout  # Fresh timeout for new page
                    if delete and not pm:
                        await result.delete()
                    continue

        except asyncio.TimeoutError:
            break
        except Exception:
            # Handle any unexpected errors gracefully
            break

    # Cleanup and raise cancelled - create expired view on timeout
    try:
        if not delete or pm:
            expired_view = StatelessSelectionView(choices, page, key, query or "", expired=True)
            await select_msg.edit(view=expired_view)
    except disnake.HTTPException:
        pass

    if delete and not pm:
        try:
            await select_msg.delete()
        except disnake.HTTPException:
            pass  # Message might already be deleted

    raise SelectionCancelled()


async def select_monster_with_dm_feedback(
    ctx,
    choices: List[Any],
    key: Callable[[Any], str] = lambda x: str(x),
    query: Optional[str] = None,
    madd_callback: Optional[Callable] = None,
    args: str = "",
    timeout: float = 120.0,
) -> Any:
    """
    Optimized monster selection with ephemeral DM feedback.

    This function is specifically designed for btn madd to provide:
    1. Efficient button-based selection using existing stateless framework
    2. Ephemeral DM message with combat channel link upon selection
    3. Proper 2-row button layout with nav arrow states
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
        # Single exact match - process immediately
        if madd_callback:
            await madd_callback(ctx, choices[0], args)
            return None
        return choices[0]

    def create_embed(page: int) -> disnake.Embed:
        """Create formatted selection embed for monster selection."""
        pages = paginate(choices, 10)
        current_choices = pages[page] if page < len(pages) else []

        description = ""
        if query:
            description += f"Your input was: `{query}`\n"
        description += "Which one were you looking for? (Type the number or `c` to cancel)\n"
        if len(pages) > 1:
            description += "`n` to go to the next page, or `p` for previous\n"
        description += "\n"

        for i, choice in enumerate(current_choices):
            global_index = i + 1 + page * 10
            description += f"[{global_index}] - {key(choice)}\n"

        description += f"\n**Instructions**\nUse buttons below OR Type your choice in {ctx.channel.mention}. This message was PMed to you to hide the monster name."

        embed = disnake.Embed(title="Multiple Matches Found", description=description, colour=0x36393F)

        if len(pages) > 1:
            embed.set_footer(text=f"Page {page + 1}/{len(pages)}")

        return embed

    def create_text_check():
        """Create efficient message check function."""

        def text_check(msg):
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

        return text_check

    # Send selection message to DM
    page = 0
    pages = paginate(choices, 10)
    embed = create_embed(page)
    view = StatelessSelectionView(choices, page, key, query or "")

    select_msg = await ctx.author.send(embed=embed, view=view)

    # Dual input handling - buttons OR text
    text_check = create_text_check()
    current_timeout = timeout

    while True:
        try:
            # Wait for either interaction or text message
            done, pending = await asyncio.wait(
                [
                    asyncio.create_task(
                        ctx.bot.wait_for(
                            "interaction",
                            check=lambda i: i.message and i.message.id == select_msg.id and i.user.id == ctx.author.id,
                        )
                    ),
                    asyncio.create_task(ctx.bot.wait_for("message", check=text_check)),
                ],
                return_when=asyncio.FIRST_COMPLETED,
                timeout=current_timeout,
            )

            # Cancel pending tasks
            for task in pending:
                task.cancel()

            if not done:  # Timeout
                break

            result = done.pop().result()

            if isinstance(result, disnake.Interaction):
                # Button interaction
                action = result.data.custom_id

                if action == "cancel":
                    await result.response.send_message("Monster selection cancelled.", ephemeral=True)
                    break
                elif action == "next":
                    page = min(page + 1, len(pages) - 1)
                    await result.response.defer()
                elif action == "prev":
                    page = max(page - 1, 0)
                    await result.response.defer()
                elif action.startswith("select_"):
                    # Selection made via button
                    try:
                        choice_idx = int(action.split("_")[1]) - 1
                        if 0 <= choice_idx < len(choices):
                            selected_monster = choices[choice_idx]

                            # Send ephemeral DM confirmation
                            combat_channel = ctx.channel.mention
                            await result.response.send_message(
                                f"✅ Adding **{key(selected_monster)}** to combat in {combat_channel}!", ephemeral=True
                            )

                            # Create expired view to handle further interactions gracefully
                            try:
                                expired_view = StatelessSelectionView(choices, page, key, query or "", expired=True)
                                await select_msg.edit(view=expired_view)
                            except disnake.HTTPException:
                                pass  # Message might be deleted already

                            if madd_callback:
                                await madd_callback(ctx, selected_monster, args)
                                return None

                            return selected_monster
                    except (ValueError, IndexError):
                        await result.response.send_message("Invalid selection.", ephemeral=True)
                        continue

                # Update view for navigation
                if action in ("next", "prev"):
                    embed = create_embed(page)
                    view = StatelessSelectionView(choices, page, key, query or "")
                    await select_msg.edit(embed=embed, view=view)
                    current_timeout = timeout  # Fresh timeout for new page
                    continue

            else:
                # Text message
                content = result.content.lower().strip()

                if content == "c":
                    await ctx.send("Monster selection cancelled.")
                    break
                elif content == "n":
                    if page >= len(pages) - 1:
                        await ctx.send("You are already on the last page.", delete_after=5)
                        continue
                    page = min(page + 1, len(pages) - 1)
                elif content == "p":
                    if page <= 0:
                        await ctx.send("You are already on the first page.", delete_after=5)
                        continue
                    page = max(page - 1, 0)
                else:
                    # Selection made via text
                    try:
                        choice_idx = int(content) - 1
                        if 0 <= choice_idx < len(choices):
                            selected_monster = choices[choice_idx]

                            # Create expired view after text selection
                            try:
                                expired_view = StatelessSelectionView(choices, page, key, query or "", expired=True)
                                await select_msg.edit(view=expired_view)
                            except disnake.HTTPException:
                                pass

                            if madd_callback:
                                await madd_callback(ctx, selected_monster, args)
                                return None
                            return selected_monster
                    except ValueError:
                        continue

                # Update view for navigation
                if content in ("n", "p"):
                    embed = create_embed(page)
                    view = StatelessSelectionView(choices, page, key, query or "")
                    await select_msg.edit(embed=embed, view=view)
                    current_timeout = timeout  # Fresh timeout for new page
                    continue

        except asyncio.TimeoutError:
            break
        except Exception:
            break

    # Cleanup on timeout/cancel - create expired view
    try:
        expired_view = StatelessSelectionView(choices, page, key, query or "", expired=True)
        await select_msg.edit(view=expired_view)
    except disnake.HTTPException:
        pass

    raise SelectionCancelled()
