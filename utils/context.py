from discord.ext.commands import Context

from cogs5e.models.character import Character
from cogs5e.models.initiative import Combat

_sentinel = object()


class AvraeContext(Context):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._character = _sentinel
        self._combat = _sentinel

    async def get_character(self, ignore_guild: bool = False):
        """
        Gets the character active in this context.

        :param bool ignore_guild: Whether to ignore any guild-active character and return the global active character.
        :raises NoCharacter: If the context has no character (author has none active).
        :rtype: Character
        """
        if not ignore_guild and self._character is not _sentinel:
            return self._character
        character = await Character.from_ctx(self, ignore_guild=ignore_guild)
        if not ignore_guild:
            self._character = character
        return character

    async def get_combat(self):
        """
        Gets the combat active in this context.

        :raises CombatNotFound: If the context has no combat (author has none active).
        :rtype: Combat
        """
        if self._combat is not _sentinel:
            return self._combat
        combat = await Combat.from_ctx(self)
        self._combat = combat
        return combat
