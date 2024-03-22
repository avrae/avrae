import logging
import time
from typing import Optional, TYPE_CHECKING

import disnake
from disnake.ext.commands import Context

from cogs5e.initiative import Combat
from cogs5e.models.character import Character
from utils.settings import ServerSettings

if TYPE_CHECKING:
    from cogs5e.initiative.upenn_nlp import NLPRecorder
    import cogs5e

_sentinel = object()

log = logging.getLogger(__name__)


class AvraeContext(Context):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._character = _sentinel
        self._combat = _sentinel
        self._server_settings = _sentinel
        self._last_typing_start = 0
        # NLP metadata
        self.nlp_is_alias = False  # set in aliasing.helpers
        self.nlp_character = None  # set just below
        self.nlp_caster = None  # set in targetutils to provide caster or character info to NLP
        self.nlp_targets = None

    async def get_character(self, use_global: bool = True, use_guild: bool = True, use_channel: bool = True):
        """
        Gets the character active in this context.

        :param bool use_guild: Whether to use any guild-active character or return the global active character if False.
        :raises NoCharacter: If the context has no character (author has none active).
        :rtype: Character
        """
        if use_guild and self._character is not _sentinel:
            return self._character
        character = await Character.from_ctx(self, use_global=use_global, use_guild=use_guild, use_channel=use_channel)
        if use_guild or use_channel:
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

    def get_nlp_recorder(self) -> Optional["NLPRecorder"]:
        """Returns the NLP recorder singleton."""
        combat_cog = self.bot.get_cog("InitTracker")  # type: Optional[cogs5e.initiative.InitTracker]
        if combat_cog is None:
            return None
        return combat_cog.nlp

    # ==== overrides ====
    async def trigger_typing(self):
        # only trigger once every 10 seconds to prevent API spam if multiple methods want to type
        now = time.time()
        if now - self._last_typing_start < 10:
            return
        self._last_typing_start = now
        try:
            await super().trigger_typing()
        except disnake.HTTPException as e:
            log.warning(f"Could not trigger typing: {e}")
