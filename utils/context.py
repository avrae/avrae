import logging

import discord
from discord.ext.commands import Context

from cogs5e.initiative import Combat
from cogs5e.models.character import Character
from utils.settings import ServerSettings

_sentinel = object()

log = logging.getLogger(__name__)


class AvraeContext(Context):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._character = _sentinel
        self._combat = _sentinel
        self._server_settings = _sentinel
        # NLP metadata
        self.nlp_is_alias = False  # set in aliasing.helpers
        self.nlp_character = None  # set just below
        self.nlp_caster = None  # set in targetutils to provide caster or character info to NLP
        self.nlp_targets = None

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
        self.nlp_character = character
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

    async def get_server_settings(self):
        """
        Gets the server settings in this context. If the context is not in a guild, returns None.

        :rtype: utils.settings.ServerSettings or None
        """
        if self._server_settings is not _sentinel:
            return self._server_settings
        if self.guild is None:
            self._server_settings = None
            return None
        server_settings = await ServerSettings.for_guild(self.bot.mdb, self.guild.id)
        self._server_settings = server_settings
        return server_settings

    # ==== overrides ====
    async def trigger_typing(self):
        try:
            await super().trigger_typing()
        except discord.HTTPException as e:
            log.warning(f"Could not trigger typing: {e}")
