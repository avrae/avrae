import asyncio
import contextlib
from typing import Mapping, Optional, Type

import disnake


class MenuBase(disnake.ui.View):
    __menu_copy_attrs__ = ()

    def __init__(self, owner: disnake.User, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.owner = owner
        self.message = None  # type: Optional[disnake.Message]

    @classmethod
    def from_menu(cls, other: "MenuBase"):
        inst = cls(owner=other.owner)
        inst.message = other.message
        for attr in cls.__menu_copy_attrs__:
            # copy the instance attr to the new instance if available, or fall back to the class default
            sentinel = object()
            value = getattr(other, attr, sentinel)
            if value is sentinel:
                value = getattr(cls, attr, None)
            setattr(inst, attr, value)
        return inst

    # ==== d.py overrides ====
    async def interaction_check(self, interaction: disnake.Interaction) -> bool:
        if interaction.user.id == self.owner.id:
            return True
        await interaction.response.send_message("You are not the owner of this menu.", ephemeral=True)
        return False

    async def on_timeout(self):
        if self.message is None:
            return
        try:
            await self.message.edit(view=None)
        except disnake.HTTPException:
            pass

    # ==== content ====
    async def get_content(self) -> Mapping:
        """Return a mapping of kwargs to send when sending the view."""
        return {}

    async def _before_send(self):
        """
        Called exactly once, immediately before a menu is sent or deferred to for the first time.
        Use this method to remove any Items that should not be sent or make any attribute adjustments.

        Note that disnake.ui.view#L170 sets each callback's name to its respective Item instance, which will have been
        resolved by the time this method is reached. You may have to let the type checker know about this.
        """
        pass

    # ==== helpers ====
    async def send_to(self, destination: disnake.abc.Messageable, *args, **kwargs):
        """Sends this menu to a given destination."""
        await self._before_send()
        content_kwargs = await self.get_content()
        message = await destination.send(*args, view=self, **content_kwargs, **kwargs)
        self.message = message
        return message

    async def defer_to(self, view_type: Type["MenuBase"], interaction: disnake.Interaction, stop=True):
        """Defers control to another menu item."""
        view = view_type.from_menu(self)
        if stop:
            self.stop()
        await view._before_send()
        await view.refresh_content(interaction)

    async def refresh_content(self, interaction: disnake.Interaction, **kwargs):
        """Refresh the interaction's message with the current state of the menu."""
        content_kwargs = await self.get_content()
        if interaction.response.is_done():
            # using interaction feels cleaner, but we could probably do self.message.edit too
            await interaction.edit_original_message(view=self, **content_kwargs, **kwargs)
        else:
            await interaction.response.edit_message(view=self, **content_kwargs, **kwargs)

    @contextlib.asynccontextmanager
    async def disable_component(
        self, interaction: disnake.Interaction, component: disnake.ui.Button | disnake.ui.Select
    ):
        """
        Updates the view such that the passed component is disabled while this context manager is active.
        Refreshes the view content after the context exits.
        """
        component.disabled = True
        await self.refresh_content(interaction)
        try:
            yield
        finally:
            component.disabled = False
            await self.refresh_content(interaction)

    @staticmethod
    async def prompt_message(
        interaction: disnake.Interaction, prompt: str, ephemeral: bool = True, timeout: int = 60
    ) -> str | None:
        """
        Send the user a prompt in the channel and return a value from their reply.
        Returns None if the user did not reply before the timeout.
        """
        await interaction.send(prompt, ephemeral=ephemeral)
        try:
            input_msg: disnake.Message = await interaction.bot.wait_for(
                "message",
                timeout=timeout,
                check=lambda msg: msg.author == interaction.author and msg.channel.id == interaction.channel_id,
            )
            with contextlib.suppress(disnake.HTTPException):
                await input_msg.delete()
            return input_msg.content
        except asyncio.TimeoutError:
            return None
