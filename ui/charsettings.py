import abc
from typing import TYPE_CHECKING, TypeVar

import disnake

from cogs5e.models.character import Character
from utils.settings import CharacterSettings
from .menu import MenuBase

_AvraeT = TypeVar('_AvraeT', bound=disnake.Client)
if TYPE_CHECKING:
    from dbot import Avrae

    _AvraeT = Avrae


class CharacterSettingsMenuBase(MenuBase, abc.ABC):
    __menu_copy_attrs__ = ('bot', 'settings', 'guild')
    bot: _AvraeT
    settings: CharacterSettings
    character: Character  # the character object here may be detached; its settings are kept in sync though

    async def commit_settings(self):
        """
        Commits any changed character settings to the db and the cached character object (if applicable - ours may be
        detached if the interaction has lasted a while).
        This is significantly more efficient than using Character.commit().
        """
        self.character.options = self.settings
        await self.settings.commit(self.bot.mdb, self.character)


class CharacterSettingsUI(CharacterSettingsMenuBase):
    @classmethod
    def new(cls, bot: _AvraeT, owner: disnake.User, character: Character):
        inst = cls(owner=owner)
        inst.bot = bot
        inst.settings = character.options
        inst.character = character
        return inst

    async def get_content(self):
        embed = disnake.Embed(
            title=f"Character Settings for {self.character.name}",
            colour=self.character.get_color()
        )
        return {"embed": embed}
