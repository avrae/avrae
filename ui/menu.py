from typing import Mapping, Optional, Type

import disnake


class MenuBase(disnake.ui.View):
    __menu_copy_attrs__ = ()

    def __init__(self, owner: disnake.User, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.owner = owner
        self.message = None  # type: Optional[disnake.Message]

    @classmethod
    def from_menu(cls, other: 'MenuBase'):
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
        await self.message.edit(view=None)

    # ==== content ====
    def get_content(self) -> Mapping:
        """Return a mapping of kwargs to send when sending the view."""
        return {}

    # ==== helpers ====
    async def send_to(self, destination: disnake.abc.Messageable, *args, **kwargs):
        """Sends this menu to a given destination."""
        message = await destination.send(*args, view=self, **self.get_content(), **kwargs)
        self.message = message
        return message

    async def defer_to(self, view_type: Type['MenuBase'], interaction: disnake.Interaction, stop=True):
        """Defers control to another menu item."""
        view = view_type.from_menu(self)
        if stop:
            self.stop()
        await interaction.response.edit_message(view=view, **view.get_content())

    async def refresh_content(self, interaction: disnake.Interaction):
        """Refresh the interaction's message with the current state of the menu."""
        await interaction.response.edit_message(view=self, **self.get_content())
